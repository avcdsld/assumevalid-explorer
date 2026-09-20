# assumevalid explorer

A small block explorer for the assumevalid network. It foregrounds what the
chain does not check: block hashes that meet no target, coinbases and outputs
over the cap, transactions accepted without verification.

Two parts, one project:

- `public/` — the static frontend, served by Cloudflare Pages at
  **explorer.assumevalid.org**. It calls the API below; the API base is the
  `API` constant at the top of the script in `public/index.html`.
- `api/explorer-api.py` — a read-only JSON API that runs on the anchor node and
  is published, without opening a port, at **api.assumevalid.org** via Cloudflare
  Tunnel. Only whitelisted read RPCs are reachable.

## Frontend (Cloudflare Pages)

Connect this repo in the Cloudflare dashboard: Workers & Pages → Create → Pages
→ Connect to Git → this repo. Framework preset None, no build command, build
output directory `public`. Then add the custom domain `explorer.assumevalid.org`
under the project's Custom domains. Pushing to the repo redeploys.

## API (on the anchor VPS)

The API reads the running node over its local RPC (cookie auth) and is exposed
through a Cloudflare Tunnel, so no inbound port is opened.

```bash
# on the anchor VPS
git clone https://github.com/avcdsld/assumevalid-explorer.git
```

Run the API as a service (reads the node at 127.0.0.1:18443, datadir ~/av):

```bash
sudo tee /etc/systemd/system/assumevalid-explorer-api.service >/dev/null <<'EOF'
[Unit]
Description=assumevalid explorer API
After=network-online.target assumevalid.service
Wants=network-online.target

[Service]
Type=simple
User=debian
ExecStart=/usr/bin/python3 /home/debian/assumevalid-explorer/api/explorer-api.py --datadir /home/debian/av --rpc 127.0.0.1:18443 --port 8080
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now assumevalid-explorer-api
curl -s localhost:8080/api/status    # sanity check
```

Publish it with Cloudflare Tunnel (domain is on Cloudflare, so DNS is automatic):

```bash
# install cloudflared (see Cloudflare docs for the current package), then:
cloudflared tunnel login
cloudflared tunnel create assumevalid-api
cloudflared tunnel route dns assumevalid-api api.assumevalid.org

mkdir -p ~/.cloudflared
cat > ~/.cloudflared/config.yml <<'EOF'
tunnel: assumevalid-api
ingress:
  - hostname: api.assumevalid.org
    service: http://localhost:8080
  - service: http_status:404
EOF

sudo cloudflared service install     # runs the tunnel on boot
# or, to run manually: cloudflared tunnel run assumevalid-api
```

Verify: `https://api.assumevalid.org/api/status` returns the chain tip, and
`https://explorer.assumevalid.org` lists blocks.

## License

Copyleft 🄯 2026 Zeroichi Arakawa. CC BY-SA 4.0.
