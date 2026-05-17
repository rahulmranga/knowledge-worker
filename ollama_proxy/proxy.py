"""
proxy.py — thin Ollama-API-compatible passthrough with logging (v1.5).

Why this exists alongside server.py (the MCP server):
  - AnythingLLM and most external LLM clients speak Ollama's REST API directly,
    NOT MCP. So the MCP server (server.py) is for Claude Code/Cowork; this
    proxy is for AnythingLLM and other Ollama-compatible clients.
  - Tailscale-expose THIS port (default 11435) instead of raw 11434 so we get:
      * per-call logging (latency, model, prompt size, error)
      * a single chokepoint for future auth/rate-limit if we ever leave the tailnet
  - 100% pass-through: same request/response shape as Ollama. AnythingLLM points
    at this URL and treats it as Ollama.

Usage:
    python proxy.py                      # binds 127.0.0.1:11435 → 127.0.0.1:11434
    python proxy.py --host 0.0.0.0       # listen on all interfaces (tailnet)
    python proxy.py --port 8080
    OLLAMA_BASE_URL=http://127.0.0.1:11434 python proxy.py

Deps: fastapi uvicorn httpx
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import httpx
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, Response, StreamingResponse
    import uvicorn
except ImportError as e:
    print(
        "proxy.py: missing deps. Install with:\n"
        "    pip install fastapi 'uvicorn[standard]' httpx",
        file=sys.stderr,
    )
    raise SystemExit(1) from e


OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
LOG_PATH = Path(os.environ.get(
    "OLLAMA_PROXY_LOG",
    str(Path(__file__).parent / "proxy.log.jsonl"),
))

app = FastAPI(title="ollama-proxy", version="1.5.0")
_client = httpx.AsyncClient(base_url=OLLAMA_BASE_URL, timeout=300.0)


def _log(record: dict) -> None:
    record.setdefault("ts", datetime.now(timezone.utc).isoformat())
    try:
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass  # never let logging break a request


@app.get("/healthz")
async def healthz() -> dict:
    try:
        r = await _client.get("/api/tags")
        r.raise_for_status()
        return {"ok": True, "ollama": OLLAMA_BASE_URL,
                "models": [m["name"] for m in r.json().get("models", [])]}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=502)


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def passthrough(path: str, request: Request):
    """Mirror every request to Ollama. Stream responses if the client asked
    for stream=true; otherwise buffer + log."""
    body = await request.body()
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in {"host", "content-length"}}
    target = f"/{path}"
    qs = request.url.query
    if qs:
        target = f"{target}?{qs}"

    # detect streaming vs buffered
    streaming = False
    if body and request.method == "POST":
        try:
            payload = json.loads(body)
            streaming = bool(payload.get("stream", True if path.startswith("api/") else False))
            model = payload.get("model")
            prompt_len = len(json.dumps(payload.get("messages") or payload.get("prompt") or ""))
        except Exception:
            payload, model, prompt_len = None, None, len(body)
    else:
        payload, model, prompt_len = None, None, 0

    t0 = time.perf_counter()
    if streaming:
        async def stream_iter():
            async with _client.stream(request.method, target, content=body, headers=headers) as r:
                status = r.status_code
                async for chunk in r.aiter_raw():
                    yield chunk
                _log({
                    "kind": "request", "method": request.method, "path": target,
                    "status": status, "model": model, "prompt_len": prompt_len,
                    "duration_ms": int((time.perf_counter() - t0) * 1000),
                    "stream": True,
                })
        return StreamingResponse(stream_iter(), media_type="application/x-ndjson")

    r = await _client.request(request.method, target, content=body, headers=headers)
    _log({
        "kind": "request", "method": request.method, "path": target,
        "status": r.status_code, "model": model, "prompt_len": prompt_len,
        "duration_ms": int((time.perf_counter() - t0) * 1000),
        "stream": False,
    })
    return Response(content=r.content, status_code=r.status_code,
                    media_type=r.headers.get("content-type"))


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Logging passthrough proxy in front of Ollama")
    p.add_argument("--host", default=os.environ.get("PROXY_HOST", "127.0.0.1"),
                   help="Bind host (set 0.0.0.0 to be reachable on the tailnet)")
    p.add_argument("--port", type=int, default=int(os.environ.get("PROXY_PORT", "11435")),
                   help="Bind port (default 11435 — Ollama's 11434 + 1)")
    args = p.parse_args(argv)
    print(f"proxy: forwarding http://{args.host}:{args.port}/* → {OLLAMA_BASE_URL}/*",
          file=sys.stderr)
    print(f"proxy: log → {LOG_PATH}", file=sys.stderr)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
