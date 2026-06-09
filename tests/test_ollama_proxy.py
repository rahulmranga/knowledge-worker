import unittest
from unittest.mock import patch

from ollama_proxy import server


class OllamaKeepAliveTest(unittest.TestCase):
    def test_chat_uses_configured_default_keep_alive(self):
        with patch.object(server, "KEEP_ALIVE", "45s"), patch.object(
            server, "_post", return_value={"done": True}
        ) as post:
            server.chat([{"role": "user", "content": "hello"}])

        self.assertEqual(post.call_args.args[0], "/api/chat")
        self.assertEqual(post.call_args.args[1]["keep_alive"], "45s")

    def test_generate_accepts_explicit_keep_alive(self):
        with patch.object(server, "_post", return_value={"done": True}) as post:
            server.generate("hello", keep_alive="5m")

        self.assertEqual(post.call_args.args[0], "/api/generate")
        self.assertEqual(post.call_args.args[1]["keep_alive"], "5m")

    def test_embed_allows_immediate_unload(self):
        with patch.object(server, "_post", return_value={"done": True}) as post:
            server.embed("hello", keep_alive=0)

        self.assertEqual(post.call_args.args[0], "/api/embed")
        self.assertEqual(post.call_args.args[1]["keep_alive"], 0)


if __name__ == "__main__":
    unittest.main()
