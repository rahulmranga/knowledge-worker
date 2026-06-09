"""
server.py — MCP server wrapping local Ollama (v1.5).

Stateless MCP server exposing four tools:
  - chat(model, messages, options?)        Chat completion via /api/chat
  - generate(model, prompt, options?)      Single-shot completion via /api/generate
  - list_models()                          Installed models via /api/tags
  - embed(model, input)                    Embeddings via /api/embed

Transports:
  - stdio  (default)   — for Claude Code, Cowork, local MCP clients
  - sse                — for remote MCP clients over HTTP (optional)

Default model: gemma4:e4b (override with OLLAMA_DEFAULT_MODEL env var).
Ollama base : http://127.0.0.1:11434 (override with OLLAMA_BASE_URL).
Keep-alive : 30s (override with OLLAMA_KEEP_ALIVE; use 0 to unload immediately).

Usage:
    python server.py                  # stdio transport (default)
    python server.py --sse --port 7421
    OLLAMA_DEFAULT_MODEL=gemma4:latest python server.py

Deps: mcp[cli] httpx
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import httpx

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    print(
        "server.py: missing dependency `mcp`. Install with:\n"
        "    pip install 'mcp[cli]' httpx",
        file=sys.stderr,
    )
    raise SystemExit(1) from e


OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("OLLAMA_DEFAULT_MODEL", "gemma4:e4b")
TIMEOUT_S = float(os.environ.get("OLLAMA_TIMEOUT_S", "300"))
KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30s")

mcp = FastMCP("ollama-proxy")
_client = httpx.Client(base_url=OLLAMA_BASE_URL, timeout=TIMEOUT_S)


def _post(path: str, payload: dict) -> dict:
    r = _client.post(path, json=payload)
    r.raise_for_status()
    return r.json()


def _get(path: str) -> dict:
    r = _client.get(path)
    r.raise_for_status()
    return r.json()


@mcp.tool()
def chat(
    messages: list[dict],
    model: str | None = None,
    options: dict | None = None,
    format: str | None = None,
    keep_alive: str | int | None = None,
) -> dict:
    """Chat completion via Ollama /api/chat.

    Args:
        messages: list of {"role": "user|assistant|system", "content": str}
        model:    Ollama model tag. Defaults to OLLAMA_DEFAULT_MODEL (gemma4:e4b).
        options:  Ollama runtime options (temperature, num_ctx, etc.).
        format:   "json" to force JSON-mode output.
        keep_alive: how long Ollama should keep the model loaded after the call.
                    Defaults to OLLAMA_KEEP_ALIVE (30s). Use 0 to unload immediately.

    Returns the raw Ollama response: {message: {role, content}, done, ...}
    """
    payload: dict[str, Any] = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "stream": False,
        "keep_alive": KEEP_ALIVE if keep_alive is None else keep_alive,
    }
    if options:
        payload["options"] = options
    if format:
        payload["format"] = format
    return _post("/api/chat", payload)


@mcp.tool()
def generate(
    prompt: str,
    model: str | None = None,
    options: dict | None = None,
    format: str | None = None,
    system: str | None = None,
    keep_alive: str | int | None = None,
) -> dict:
    """Single-shot completion via Ollama /api/generate.

    Args:
        prompt:   the user prompt
        model:    defaults to OLLAMA_DEFAULT_MODEL
        options:  Ollama runtime options
        format:   "json" to force JSON output
        system:   optional system prompt
        keep_alive: how long Ollama should keep the model loaded after the call.
                    Defaults to OLLAMA_KEEP_ALIVE (30s). Use 0 to unload immediately.
    """
    payload: dict[str, Any] = {
        "model": model or DEFAULT_MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": KEEP_ALIVE if keep_alive is None else keep_alive,
    }
    if options:
        payload["options"] = options
    if format:
        payload["format"] = format
    if system:
        payload["system"] = system
    return _post("/api/generate", payload)


@mcp.tool()
def list_models() -> dict:
    """List models installed in the local Ollama instance."""
    return _get("/api/tags")


@mcp.tool()
def embed(
    input: str | list[str],
    model: str | None = None,
    keep_alive: str | int | None = None,
) -> dict:
    """Get embeddings via Ollama /api/embed.

    Args:
        input: a string or list of strings to embed
        model: embedding-capable model tag (e.g. "nomic-embed-text")
        keep_alive: how long Ollama should keep the model loaded after the call.
                    Defaults to OLLAMA_KEEP_ALIVE (30s). Use 0 to unload immediately.
    """
    payload = {
        "model": model or DEFAULT_MODEL,
        "input": input,
        "keep_alive": KEEP_ALIVE if keep_alive is None else keep_alive,
    }
    return _post("/api/embed", payload)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="MCP server wrapping local Ollama")
    p.add_argument("--sse", action="store_true",
                   help="Use SSE/HTTP transport instead of stdio (for remote MCP clients)")
    p.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "7421")),
                   help="HTTP port for --sse mode (default 7421)")
    p.add_argument("--host", default=os.environ.get("MCP_HOST", "127.0.0.1"),
                   help="Bind host for --sse mode (default 127.0.0.1; set 0.0.0.0 for tailnet)")
    args = p.parse_args(argv)

    # Sanity check: is Ollama reachable?
    try:
        _get("/api/tags")
    except Exception as e:
        print(
            f"server.py: cannot reach Ollama at {OLLAMA_BASE_URL} ({e}).\n"
            "Is the Ollama daemon running? Try: ollama serve",
            file=sys.stderr,
        )
        # Don't exit — let the MCP client see the error per-call. But warn loudly.

    if args.sse:
        # FastMCP's SSE transport binds host/port via settings.
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        print(f"server.py: SSE transport on http://{args.host}:{args.port}/sse",
              file=sys.stderr)
        mcp.run(transport="sse")
    else:
        # Friendly hint when launched interactively — MCP-stdio is for clients,
        # not humans. If stdin is a TTY, the user almost certainly meant to use
        # --sse or register this in an MCP client config.
        if sys.stdin.isatty():
            print(
                "server.py: stdio transport ready. This server is meant to be\n"
                "  spawned by an MCP client (Claude Code, Cowork, Claude Desktop)\n"
                "  via subprocess pipes — running it in a terminal will produce\n"
                "  JSON-RPC parse errors on every keystroke. To test interactively:\n"
                "    npx @modelcontextprotocol/inspector python server.py\n"
                "  Or run with --sse to expose an HTTP/SSE endpoint instead.\n"
                "  Press Ctrl-C to exit.\n",
                file=sys.stderr,
            )
        mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
