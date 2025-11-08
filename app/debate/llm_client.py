from __future__ import annotations

import asyncio
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
        max_retries: int = 2,
    ) -> None:
        self.name = name
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_retries = max(0, max_retries)

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

        attempt = 0
        last_error: Optional[Exception] = None
        backoff = 0.5
        while attempt <= self.max_retries:
            attempt += 1
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(self.endpoint, json=payload)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt <= self.max_retries:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 2.0)
                    continue
                raise LLMClientError(f"{self.name} request failed: {exc}") from exc

            if response.status_code < 400:
                break

            retriable = response.status_code in {404, 408, 409, 425, 429, 500, 502, 503, 504}
            if retriable and attempt <= self.max_retries:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 2.0)
                continue

            raise LLMClientError(
                f"{self.name} responded with {response.status_code}: {response.text}"
            )

        data = response.json()
        if "content" not in data:
            raise LLMClientError(f"{self.name} response missing 'content' field")

        metadata = data.get("metadata") or {}
        return str(data["content"]), metadata
