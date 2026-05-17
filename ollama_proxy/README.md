# ollama_proxy — v1.5

Local-Gemma access layer for the Rahul Brain knowledge graph.

Three components, one purpose: make `gemma4:e4b` (and future local Ollama models) usable from Claude/Cowork, AnythingLLM, and the mygraph extraction pipeline — over Tailscale.

## Layout

```
ollama_proxy/
├── server.py             MCP server wrapping Ollama. stdio for Claude Code/Cowork; SSE for remote MCP clients.
├── proxy.py              Logging passthrough proxy in front of Ollama. Tailscale-expose this for AnythingLLM.
├── extractor_adapter.py  Drop-in replacement for mygraph/extractor.py — routes extraction to local Gemma.
├── eval_compare.py       Side-by-side Claude vs Gemma extraction A/B; appends to mygraph/eval_record.jsonl.
├── tailscale.md          Network exposure runbook.
├── requirements.txt
└── README.md             ← you are here
```

## Why three components, not one

| Component | Consumer | Transport |
|---|---|---|
| `server.py` | Claude Code, Cowork, anything that speaks MCP | stdio (default) or SSE/HTTP |
| `proxy.py`  | AnythingLLM, raw HTTP clients, anything Ollama-compatible | HTTP (Ollama API shape) |
| `extractor_adapter.py` | `mygraph/ingest.py` (called via `--backend ollama`) | in-process |

`server.py` and `proxy.py` are *not* the same thing. MCP is JSON-RPC for tool-use; Ollama's REST API is what AnythingLLM actually speaks. Two consumers, two surfaces.

## Install

```bash
cd ~/Desktop/ideas/"Midnight idea - Knowledge worker"/ollama_proxy
pip install -r requirements.txt
ollama list   # confirm gemma4:e4b is present
ollama serve  # if not already running
```

## Quick test

```bash
# 1. MCP server (stdio — for Claude Code config)
python server.py

# 2. Proxy (logging passthrough on :11435)
python proxy.py
curl http://127.0.0.1:11435/healthz   # → {"ok": true, "models": [...]}

# 3. Extractor adapter (drop-in for mygraph)
cd ../mygraph
python mygraph.py ingest ../inspiration.md --backend ollama --non-interactive

# 4. A/B comparison
cd ../ollama_proxy
python eval_compare.py ../inspiration.md
```

## Wiring into Claude Code / Cowork

Add to your MCP client config (e.g. `~/.config/claude-code/mcp_servers.json`):

```json
{
  "ollama-proxy": {
    "command": "python",
    "args": ["/Users/rahul/Desktop/ideas/Midnight idea - Knowledge worker/ollama_proxy/server.py"],
    "env": {
      "OLLAMA_DEFAULT_MODEL": "gemma4:e4b"
    }
  }
}
```

Once registered, Claude can call `chat`, `generate`, `list_models`, `embed` against local Gemma without any API spend.

## Wiring into AnythingLLM

Two options:

**Option A — point AnythingLLM at raw Ollama (simplest, no proxy):**
- Settings → LLM Provider → Ollama
- Base URL: `http://127.0.0.1:11434`
- Tailscale-expose: `tailscale serve --bg --https=11434 localhost:11434` (then point AnythingLLM on other devices at the tailnet URL)

**Option B — point at `proxy.py` for logging:**
- Run `python proxy.py --host 0.0.0.0 --port 11435`
- AnythingLLM Base URL: `http://<tailnet-host>:11435`
- All requests are logged to `proxy.log.jsonl` (latency, model, prompt size, errors)

See `tailscale.md` for the full network setup.

## Config (env vars)

| Variable | Default | Used by |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | all |
| `OLLAMA_DEFAULT_MODEL` | `gemma4:e4b` | server, adapter |
| `OLLAMA_TIMEOUT_S` | `300` | server |
| `GEMMA_NUM_CTX` | `8192` | extractor_adapter |
| `MCP_HOST` / `MCP_PORT` | `127.0.0.1` / `7421` | server (--sse mode) |
| `PROXY_HOST` / `PROXY_PORT` | `127.0.0.1` / `11435` | proxy |
| `OLLAMA_PROXY_LOG` | `proxy.log.jsonl` | proxy |

## Scope (v1.5)

In: MCP wrap, logging proxy, extractor adapter, eval comparison, Tailscale exposure runbook.

Out: per-user auth, rate limiting, multi-model routing, fine-tuning, web UI. Add when justified.
