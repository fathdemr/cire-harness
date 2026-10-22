import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from cire_harness.providers.base import ProviderError


async def read_json_events(client: httpx.AsyncClient, request: httpx.Request) -> AsyncIterator[Any]:
    try:
        async with client.stream(
            request.method, request.url, headers=request.headers, content=request.content
        ) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode(errors="replace")
                raise ProviderError(f"HTTP {response.status_code}", response.status_code, body)
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                yield json.loads(data)
    except httpx.HTTPError as exc:
        raise ProviderError(str(exc)) from exc
