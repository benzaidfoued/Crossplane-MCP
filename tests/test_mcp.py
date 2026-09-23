import pytest
from conftest import GROUP
from mcp.server.fastmcp.exceptions import ToolError
from starlette.testclient import TestClient

from crossplane_compass.server import TOOLS, BearerAuth, create_server


async def test_protocol_tools_and_execution(compass):
    mcp = create_server(compass)
    tools = await mcp.list_tools()
    assert {t.name for t in tools} == set(TOOLS)
    assert len(tools) == 24
    tool = next(t for t in tools if t.name == "resource_get")
    assert {"cluster", "api_version", "kind", "name"} <= set(tool.inputSchema["required"])
    result = await mcp.call_tool(
        "resource_get",
        {
            "cluster": "test",
            "api_version": f"{GROUP}/v1",
            "kind": "Database",
            "name": "db",
            "namespace": "team-a",
        },
    )
    assert "db" in str(result)
    with pytest.raises(ToolError):
        await mcp.call_tool(
            "resource_get",
            {
                "cluster": "forbidden",
                "api_version": f"{GROUP}/v1",
                "kind": "Database",
                "name": "db",
            },
        )


def test_http_protocol_auth_rotation_and_health(compass, tmp_path):
    token = tmp_path / "token"
    token.write_text("a" * 40)
    mcp = create_server(compass, ["testserver"])
    with TestClient(BearerAuth(mcp.streamable_http_app(), str(token))) as c:
        assert c.get("/healthz").status_code == 200
        assert c.get("/readyz").status_code == 200
        assert c.get("/metrics").status_code == 401
        headers = {
            "Authorization": "Bearer " + "a" * 40,
            "Accept": "application/json, text/event-stream",
        }
        init = c.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
        assert init.status_code == 200, init.text
        assert "serverInfo" in init.json()["result"]
        r = c.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert len(r.json()["result"]["tools"]) == 24
        r = c.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "clusters_list", "arguments": {}},
            },
        )
        assert not r.json()["result"].get("isError", False)
        assert "compass_tool_calls_total" in c.get("/metrics", headers=headers).text
        token.write_text("b" * 40)
        assert c.get("/metrics", headers=headers).status_code == 401
        headers["Authorization"] = "Bearer " + "b" * 40
        assert c.get("/metrics", headers=headers).status_code == 200
        headers["Host"] = "evil.example"
        assert c.post("/mcp", headers=headers, json={}).status_code == 421


def test_http_fails_closed_missing_secret(compass, tmp_path):
    with TestClient(
        BearerAuth(create_server(compass).streamable_http_app(), str(tmp_path / "missing"))
    ) as c:
        assert c.post("/mcp").status_code == 401
