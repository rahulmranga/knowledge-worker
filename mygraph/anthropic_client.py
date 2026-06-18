"""
Anthropic client selection for mygraph LLM-bound commands.

The extractor and optional check probes support multiple Anthropic runtimes. Keep
provider detection in one place so Bedrock and Foundry env vars are treated as
valid Anthropic configuration, not as missing ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_DOTENV_LOADED = False


@dataclass(frozen=True)
class AnthropicClientConfig:
    provider: str
    model: str


def load_repo_env() -> None:
    """Load repo-local .env values without overriding the process environment."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True

    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for env_path in candidates:
        if not env_path.is_file():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            os.environ[key] = _parse_env_value(value)
        return


def _parse_env_value(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    try:
        parsed = shlex.split(value, comments=False, posix=True)
    except ValueError:
        return value.strip("\"'")
    if len(parsed) == 1:
        return parsed[0]
    return value.strip("\"'")


def _configured_provider() -> str:
    explicit = (
        os.environ.get("MYGRAPH_ANTHROPIC_PROVIDER")
        or os.environ.get("ANTHROPIC_PROVIDER")
        or ""
    ).strip().lower()
    aliases = {
        "": "",
        "auto": "",
        "claude": "anthropic",
        "default": "anthropic",
        "native": "anthropic",
        "anthropic": "anthropic",
        "api": "anthropic",
        "foundry": "foundry",
        "azure": "foundry",
        "azure-foundry": "foundry",
        "bedrock": "bedrock",
        "aws-bedrock": "bedrock",
        "vertex": "vertex",
        "google-vertex": "vertex",
    }
    if explicit not in aliases:
        raise RuntimeError(
            "unsupported Anthropic provider "
            f"{explicit!r}; expected anthropic, foundry, bedrock, vertex, or auto"
        )
    provider = aliases[explicit]
    if provider:
        return provider

    foundry_env = (
        "ANTHROPIC_FOUNDRY_API_KEY",
        "ANTHROPIC_FOUNDRY_RESOURCE",
        "ANTHROPIC_FOUNDRY_BASE_URL",
    )
    if any(os.environ.get(name) for name in foundry_env):
        return "foundry"

    bedrock_specific_env = (
        "AWS_BEARER_TOKEN_BEDROCK",
        "ANTHROPIC_BEDROCK_BASE_URL",
    )
    if any(os.environ.get(name) for name in bedrock_specific_env):
        return "bedrock"

    anthropic_env = (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_PROFILE",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_IDENTITY_TOKEN",
        "ANTHROPIC_IDENTITY_TOKEN_FILE",
    )
    if any(os.environ.get(name) for name in anthropic_env):
        return "anthropic"

    vertex_env = (
        "CLOUD_ML_REGION",
        "ANTHROPIC_VERTEX_BASE_URL",
        "GOOGLE_APPLICATION_CREDENTIALS",
    )
    if any(os.environ.get(name) for name in vertex_env):
        return "vertex"

    has_aws_region = bool(os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"))
    has_aws_auth = bool(
        os.environ.get("AWS_PROFILE")
        or (os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"))
    )
    if has_aws_region and has_aws_auth:
        return "bedrock"

    return ""


def _bedrock_kwargs() -> dict[str, str]:
    if os.environ.get("AWS_PROFILE"):
        return {"aws_profile": os.environ["AWS_PROFILE"]}
    if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
        kwargs = {
            "aws_access_key": os.environ["AWS_ACCESS_KEY_ID"],
            "aws_secret_key": os.environ["AWS_SECRET_ACCESS_KEY"],
        }
        if os.environ.get("AWS_SESSION_TOKEN"):
            kwargs["aws_session_token"] = os.environ["AWS_SESSION_TOKEN"]
        return kwargs
    return {}


def anthropic_configured() -> bool:
    load_repo_env()
    return bool(_configured_provider())


def get_anthropic_client() -> tuple[Any, AnthropicClientConfig]:
    """Return a configured Anthropic-compatible client and its resolved config."""
    load_repo_env()
    try:
        import anthropic  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "the `anthropic` package is not installed. Run: pip install anthropic"
        ) from e

    provider = _configured_provider()
    if not provider:
        raise RuntimeError(
            "no Anthropic provider configuration found. Set one of:\n"
            "  - ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN\n"
            "  - ANTHROPIC_FOUNDRY_API_KEY plus ANTHROPIC_FOUNDRY_RESOURCE or ANTHROPIC_FOUNDRY_BASE_URL\n"
            "  - AWS_BEARER_TOKEN_BEDROCK or AWS credentials plus AWS_REGION/AWS_DEFAULT_REGION"
        )

    try:
        if provider == "foundry":
            client = anthropic.AnthropicFoundry()
        elif provider == "bedrock":
            client = anthropic.AnthropicBedrock(**_bedrock_kwargs())
        elif provider == "vertex":
            client = anthropic.AnthropicVertex()
        else:
            client = anthropic.Anthropic()
    except Exception as e:
        raise RuntimeError(
            f"failed to construct Anthropic {provider} client from environment: {e}"
        ) from e

    model = os.environ.get("MYGRAPH_MODEL", "claude-sonnet-4-6")
    return client, AnthropicClientConfig(provider=provider, model=model)
