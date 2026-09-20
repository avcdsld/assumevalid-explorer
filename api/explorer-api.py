#!/usr/bin/env python3
"""Read-only JSON API for the assumevalid block explorer.

Exposes a small, whitelisted view of the anchor node over HTTP for the explorer
frontend. Only safe read RPCs are reachable and every input is validated. Bind to
localhost and publish it with Cloudflare Tunnel (see README); do not open a port
for it.

Endpoints:
  GET /api/status                       chain tip summary
  GET /api/blocks?before=<h>&count=<n>  recent blocks, newest first (count <= 50)
  GET /api/block/<height|hash>          one block with its transactions
  GET /api/tx/<txid>?block=<hash>       one transaction (block hash avoids needing txindex)
"""

import argparse
import base64
import http.client
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HEX64 = re.compile(r"^[0-9a-f]{64}$")


class RPC:
    def __init__(self, host, port, cookie_path):
        with open(cookie_path) as f:
            self.auth = base64.b64encode(f.read().strip().encode()).decode()
        self.host, self.port = host, port

    def call(self, method, params=None):
        body = json.dumps({"jsonrpc": "2.0", "id": 0, "method": method, "params": params or []})
        conn = http.client.HTTPConnection(self.host, self.port, timeout=30)
        conn.request("POST", "/", body, {
            "Authorization": "Basic " + self.auth,
            "Content-Type": "application/json",
        })
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        obj = json.loads(data)
        if obj.get("error"):
            raise ValueError(obj["error"])
        return obj["result"]


rpc = None


def status():
    i = rpc.call("getblockchaininfo")
    return {"chain": i["chain"], "blocks": i["blocks"], "headers": i["headers"],
            "bestblockhash": i["bestblockhash"]}


def blocks(before, count):
    tip = rpc.call("getblockcount")
    top = tip if before is None else min(before, tip)
    count = max(1, min(count, 50))
    out = []
    h = top
    while h > top - count and h >= 0:
        b = rpc.call("getblock", [rpc.call("getblockhash", [h]), 1])
        out.append({"height": b["height"], "hash": b["hash"], "time": b["time"],
                    "nTx": b["nTx"], "size": b["size"]})
        h -= 1
    return {"tip": tip, "blocks": out}


def block(key):
    if key.isdigit():
        bh = rpc.call("getblockhash", [int(key)])
    elif HEX64.match(key):
        bh = key
    else:
        raise ValueError("bad block id")
    return rpc.call("getblock", [bh, 2])


def tx(txid, blockhash):
    if not HEX64.match(txid):
        raise ValueError("bad txid")
    params = [txid, True]
    if blockhash and HEX64.match(blockhash):
        params.append(blockhash)
    return rpc.call("getrawtransaction", params)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=5")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        parts = u.path.strip("/").split("/")
        q = parse_qs(u.query)
        try:
            if parts == ["api", "status"]:
                self._send(200, status())
            elif parts == ["api", "blocks"]:
                before = int(q["before"][0]) if "before" in q else None
                count = int(q.get("count", ["25"])[0])
                self._send(200, blocks(before, count))
            elif len(parts) == 3 and parts[:2] == ["api", "block"]:
                self._send(200, block(parts[2]))
            elif len(parts) == 3 and parts[:2] == ["api", "tx"]:
                self._send(200, tx(parts[2], q.get("block", [None])[0]))
            else:
                self._send(404, {"error": "not found"})
        except Exception as e:
            self._send(400, {"error": str(e)})

    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--datadir", default=os.path.expanduser("~/av"))
    ap.add_argument("--rpc", default="127.0.0.1:18443")
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    global rpc
    rh, rp = args.rpc.split(":")
    cookie = os.path.join(args.datadir, "assumevalid", ".cookie")
    if not os.path.exists(cookie):
        sys.exit(f"cookie not found: {cookie} (is the node running?)")
    rpc = RPC(rh, int(rp), cookie)

    srv = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"explorer-api on http://{args.bind}:{args.port}  ->  node {args.rpc}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
