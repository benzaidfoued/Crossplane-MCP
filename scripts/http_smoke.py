"""CI-only test of the container deployed through Helm and forwarded to localhost."""

import asyncio

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main():
    async with httpx.AsyncClient() as probe:
        for _ in range(60):
            try:
                if (await probe.get("http://localhost:8080/readyz", timeout=2)).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        else:
            raise RuntimeError("Deployed service never became ready")
        assert (await probe.get("http://localhost:8080/metrics")).status_code == 401
    headers = {"Authorization": "Bearer ci-only-disposable-token-01234567890123456789"}
    async with httpx.AsyncClient(headers=headers) as client:
        async with streamable_http_client("http://localhost:8080/mcp", http_client=client) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                assert len((await session.list_tools()).tools) == 24
                result = await session.call_tool(
                    "catalog_search", {"cluster": "default", "query": "Widget"}
                )
                assert not result.isError, result
                assert "Widget" in str(result)
    print(
        "Deployed Helm service: HTTP authentication, MCP initialization, discovery and catalog passed"
    )


asyncio.run(main())
