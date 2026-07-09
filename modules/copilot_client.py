"""
GitHub Copilot Integration — placeholder.
Actual Copilot calls go through the GitHub API (copilot/v1/engines/copilot-codex/completions).
"""
import logging
import os

log = logging.getLogger("CopilotClient")


class CopilotClient:
    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN", "")

    def is_configured(self) -> bool:
        return bool(self.token)

    async def complete(self, prompt: str, max_tokens: int = 256) -> str:
        if not self.is_configured():
            return ""
        log.info("CopilotClient.complete called (not yet implemented)")
        return ""
