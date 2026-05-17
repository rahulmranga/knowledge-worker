# Tailscale exposure runbook

Make local Ollama (and the MCP/proxy servers) reachable from your other devices over the tailnet. Auth = tailnet ACL only (per v1.5 design decision). No app-layer secrets.

## Prereqs

- Tailscale installed and signed in on the host machine (the one running Ollama).
- `tailscale status` shows the host as Online.
- Ollama is running on `127.0.0.1:11434` (default).

## Three exposure patterns

Pick based on which client you're serving.

### A. AnythingLLM on another device → raw Ollama

Simplest. Tailscale `serve` exposes a localhost port to the tailnet over HTTPS with auto-TLS.

```bash
# On the Ollama host
tailscale serve --bg --https=11434 localhost:11434
tailscale serve status   # confirm
```

Then on AnythingLLM (on any other tailnet device):
- Settings → LLM Provider → Ollama
- Base URL: `https://<host>.<tailnet-name>.ts.net:11434`

### B. AnythingLLM on another device → proxy.py (with logging)

Use this if you want per-request logs and a stable surface that's separate from raw Ollama.

```bash
# On the Ollama host
python ollama_proxy/proxy.py --host 0.0.0.0 --port 11435
# In a second terminal
tailscale serve --bg --https=11435 localhost:11435
```

AnythingLLM Base URL: `https://<host>.<tailnet-name>.ts.net:11435`. All calls logged to `ollama_proxy/proxy.log.jsonl`.

### C. Remote Claude Code / Cowork → MCP over SSE

The MCP server defaults to stdio (local-only, ideal for Claude Code on the same machine). For a remote client, use SSE:

```bash
# On the Ollama host
python ollama_proxy/server.py --sse --host 0.0.0.0 --port 7421
tailscale serve --bg --https=7421 localhost:7421
```

Remote MCP client config:
```json
{
  "ollama-proxy-remote": {
    "transport": "sse",
    "url": "https://<host>.<tailnet-name>.ts.net:7421/sse"
  }
}
```

## ACL hardening (recommended)

By default every device on your tailnet can reach exposed services. Lock down to specific tags or users via the Tailscale Admin Console → Access Controls.

Example ACL fragment that only lets your laptop and phone reach the Ollama host's exposed ports:

```jsonc
{
  "tagOwners": {
    "tag:ollama-host":   ["autogroup:admin"],
    "tag:ollama-client": ["autogroup:admin"]
  },
  "acls": [
    {
      "action": "accept",
      "src":    ["tag:ollama-client"],
      "dst":    ["tag:ollama-host:11434", "tag:ollama-host:11435", "tag:ollama-host:7421"]
    }
  ]
}
```

Then tag the host in the Admin Console:
- Ollama machine → tag `ollama-host`
- Laptop / phone → tag `ollama-client`

## Funnel (public internet) — DON'T

`tailscale funnel` exposes a service to the public internet. Do **not** use it for any of these endpoints. Auth model is tailnet-only by design (v1.5 §Auth). Public exposure invalidates that.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ollama serve` not responding | daemon not running | `ollama serve` in a terminal, or check `launchctl list \| grep ollama` |
| `tailscale serve` says "no route" | Tailscale not running | `tailscale up` |
| AnythingLLM returns connection refused | wrong port / proxy not bound 0.0.0.0 | proxy.py defaults to 127.0.0.1 — use `--host 0.0.0.0` |
| TLS error in browser | host not signed in to tailnet, or HTTPS cert pending | retry after a minute; `tailscale cert` for manual provision |
| MCP client can't reach SSE endpoint | client doesn't follow tailnet HTTPS redirects | use the full `https://...:port/sse` URL, no trailing slash games |

## Verify end-to-end

```bash
# from a different tailnet device
curl https://<host>.<tailnet-name>.ts.net:11435/healthz
# expected: {"ok": true, "ollama": "...", "models": ["gemma4:e4b", "gemma4:latest"]}
```
