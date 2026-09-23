"""Real MCP client → stdio subprocess → official Kubernetes client → mock HTTP API."""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit

import yaml
from conftest import GROUP
from kubernetes.client.exceptions import ApiException
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_real_stdio_transport_and_kubernetes_http(api, tmp_path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            u = urlsplit(self.path)
            try:
                payload = api.call_api(u.path, "GET", query_params=parse_qsl(u.query))
                status = 200
            except ApiException as e:
                payload, status = {"kind": "Status", "message": "denied"}, e.status
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_PATCH(self):
            u = urlsplit(self.path)
            assert dict(parse_qsl(u.query))["dryRun"] == "All"
            assert self.headers["Content-Type"] == "application/apply-patch+yaml"
            body = self.rfile.read(int(self.headers["Content-Length"]))
            assert json.loads(body)["kind"] == "Database"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    kubeconfig = tmp_path / "config"
    kubeconfig.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "v1",
                "kind": "Config",
                "current-context": "mock",
                "clusters": [
                    {
                        "name": "mock",
                        "cluster": {"server": f"http://127.0.0.1:{server.server_port}"},
                    }
                ],
                "contexts": [{"name": "mock", "context": {"cluster": "mock", "user": "mock"}}],
                "users": [{"name": "mock", "user": {"token": "mock-only"}}],
            }
        )
    )
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "crossplane_compass.server",
            "--enable-server-dry-run",
            "--context",
            "test=mock",
            "--groups",
            GROUP,
            "--namespaces",
            "team-a",
        ],
        env={**os.environ, "KUBECONFIG": str(kubeconfig)},
    )
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.name == "Crossplane Compass"
                assert initialized.serverInfo.version == "0.1.0"
                assert len((await session.list_tools()).tools) == 24
                result = await session.call_tool(
                    "resource_get",
                    {
                        "cluster": "test",
                        "api_version": f"{GROUP}/v1",
                        "kind": "Database",
                        "name": "db",
                        "namespace": "team-a",
                    },
                )
                assert not result.isError, result
                assert "db-uid" in str(result)
                denied = await session.call_tool(
                    "resource_get",
                    {
                        "cluster": "test",
                        "api_version": f"{GROUP}/v1",
                        "kind": "Database",
                        "name": "db",
                        "namespace": "team-b",
                    },
                )
                assert denied.isError
                manifest = yaml.safe_dump(
                    {
                        "apiVersion": f"{GROUP}/v1",
                        "kind": "Database",
                        "metadata": {"name": "db", "namespace": "team-a"},
                        "spec": {"size": 3},
                    }
                )
                validation = await session.call_tool(
                    "manifest_validate",
                    {"cluster": "test", "manifest_yaml": manifest, "server_side": True},
                )
                assert not validation.isError, validation
                assert "kubernetes-server-dry-run" in str(validation)
                assert (await session.list_resources()).resources
                assert (await session.list_prompts()).prompts
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
