from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import httpx


class LLMClientError(RuntimeError):
    pass


class LLMClient:
    def __init__(
        self,
        name: str,
        endpoint: str,
        timeout: float,
    ) -> None:
        self.name = name
        self.endpoint = endpoint
        self.timeout = timeout

    async def complete(
        self,
        prompt: str,
        context: Dict[str, Any],
        tags: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "context": context,
            "client": {"name": self.name},
        }
        if tags:
            payload["tags"] = tags

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.endpoint, json=payload)

        if response.status_code >= 400:
            raise LLMClientError(
                f"{self.name} responded with {response.status_code}: {response.text}"
            )

        data = response.json()
        if "content" not in data:
            raise LLMClientError(f"{self.name} response missing 'content' field")

        metadata = data.get("metadata") or {}
        return str(data["content"]), metadata

