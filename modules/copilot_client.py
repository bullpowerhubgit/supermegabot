"""
GitHub Copilot Integration.
Routes through ai_complete() (APIHunt chain: OpenClaw → Groq → DeepSeek → …).
GitHub Copilot API requires a paid Copilot subscription and separate OAuth flow;
until those credentials are configured we use our local/free AI stack instead.
"""
import logging
import os

log = logging.getLogger("CopilotClient")


class CopilotClient:
    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN", "")

    def is_configured(self) -> bool:
        return True  # ai_complete() is always available

    async def complete(self, prompt: str, max_tokens: int = 256) -> str:
        try:
            from modules.ai_client import ai_complete
            return await ai_complete(prompt, model_hint="code", max_tokens=max_tokens)
        except Exception as e:
            log.warning("CopilotClient.complete error: %s", e)
            return ""
