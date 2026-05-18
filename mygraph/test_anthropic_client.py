from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import anthropic_client


class AnthropicProviderDetectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._env = os.environ.copy()
        os.environ.clear()
        anthropic_client._DOTENV_LOADED = True

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env)
        anthropic_client._DOTENV_LOADED = False

    def test_standard_anthropic_api_key_is_configured(self) -> None:
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

        self.assertTrue(anthropic_client.anthropic_configured())
        self.assertEqual(anthropic_client._configured_provider(), "anthropic")

    def test_foundry_env_is_configured(self) -> None:
        os.environ["ANTHROPIC_FOUNDRY_API_KEY"] = "test-key"
        os.environ["ANTHROPIC_FOUNDRY_RESOURCE"] = "test-resource"

        self.assertTrue(anthropic_client.anthropic_configured())
        self.assertEqual(anthropic_client._configured_provider(), "foundry")

    def test_bedrock_bearer_token_is_configured(self) -> None:
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = "test-token"
        os.environ["AWS_REGION"] = "us-east-1"

        self.assertTrue(anthropic_client.anthropic_configured())
        self.assertEqual(anthropic_client._configured_provider(), "bedrock")

    def test_bedrock_aws_credentials_are_configured_without_standard_key(self) -> None:
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["AWS_ACCESS_KEY_ID"] = "test-access-key"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "test-secret-key"

        self.assertTrue(anthropic_client.anthropic_configured())
        self.assertEqual(anthropic_client._configured_provider(), "bedrock")

    def test_standard_key_wins_over_generic_aws_environment(self) -> None:
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["AWS_ACCESS_KEY_ID"] = "test-access-key"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "test-secret-key"

        self.assertEqual(anthropic_client._configured_provider(), "anthropic")

    def test_no_provider_env_is_not_configured(self) -> None:
        self.assertFalse(anthropic_client.anthropic_configured())
        self.assertEqual(anthropic_client._configured_provider(), "")

    def test_get_client_constructs_foundry_from_env(self) -> None:
        calls = []

        class FoundryClient:
            def __init__(self) -> None:
                calls.append("foundry")

        fake_anthropic = types.SimpleNamespace(
            Anthropic=lambda: None,
            AnthropicFoundry=FoundryClient,
            AnthropicBedrock=lambda **_: None,
            AnthropicVertex=lambda: None,
        )
        os.environ["ANTHROPIC_FOUNDRY_API_KEY"] = "test-key"
        os.environ["ANTHROPIC_FOUNDRY_RESOURCE"] = "test-resource"

        with patch.dict(sys.modules, {"anthropic": fake_anthropic}):
            _, config = anthropic_client.get_anthropic_client()

        self.assertEqual(calls, ["foundry"])
        self.assertEqual(config.provider, "foundry")

    def test_get_client_constructs_bedrock_with_aws_profile(self) -> None:
        calls = []

        class BedrockClient:
            def __init__(self, **kwargs: str) -> None:
                calls.append(kwargs)

        fake_anthropic = types.SimpleNamespace(
            Anthropic=lambda: None,
            AnthropicFoundry=lambda: None,
            AnthropicBedrock=BedrockClient,
            AnthropicVertex=lambda: None,
        )
        os.environ["AWS_REGION"] = "us-east-1"
        os.environ["AWS_PROFILE"] = "test-profile"

        with patch.dict(sys.modules, {"anthropic": fake_anthropic}):
            _, config = anthropic_client.get_anthropic_client()

        self.assertEqual(calls, [{"aws_profile": "test-profile"}])
        self.assertEqual(config.provider, "bedrock")


if __name__ == "__main__":
    unittest.main()
