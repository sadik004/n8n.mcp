"""
Model Context Protocol (MCP) Server for n8n.
Supports official FastMCP stdio transport and raw JSON-RPC 2.0 stdio handling.
Engineered for Windows ProactorEventLoop compatibility and cross-platform production deployment.
"""

from __future__ import annotations
import asyncio
import json
import logging
import sys
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from mcp.server.fastmcp import FastMCP
from n8n_mcp.config import N8nConfig
from n8n_mcp.engine.client import N8nClient
from n8n_mcp.tools.registry import ToolRegistry

logger = logging.getLogger("n8n_mcp.server")


def create_mcp_server(
    config: Optional[N8nConfig] = None,
    client: Optional[N8nClient] = None,
) -> FastMCP:
    """Creates and configures an official FastMCP server instance with all 26 n8n tools."""
    cfg = config or N8nConfig()
    mcp = FastMCP(
        name="n8n-mcp",
        instructions="Production-grade MCP server for n8n workflow automation, diff-patching, safe testing, and self-healing.",
    )
    registry = ToolRegistry(client=client, config=cfg)
    registry.register_all_tools(mcp)
    return mcp


class N8nMcpServer:
    """
    Production-grade MCP server wrapper for n8n.
    Combines FastMCP with Windows-hardened stdio transport and raw JSON-RPC 2.0 processing.
    """

    def __init__(
        self,
        config: Optional[N8nConfig] = None,
        client: Optional[N8nClient] = None,
    ):
        self.config = config or N8nConfig()
        self.client = client or N8nClient(config=self.config)
        self.registry = ToolRegistry(client=self.client, config=self.config)
        self.mcp = FastMCP(
            name="n8n-mcp",
            instructions="Production-grade MCP server for n8n workflow automation, diff-patching, safe testing, and self-healing.",
        )
        self.registry.register_all_tools(self.mcp)

    async def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Processes an incoming JSON-RPC 2.0 request (for direct testing and non-FastMCP transports)."""
        method = request.get("method")
        msg_id = request.get("id")
        params = request.get("params", {})

        # Notifications (no response required)
        if method in ("notifications/initialized", "$/cancelRequest"):
            return None

        # 1. Initialize Handshake
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {
                            "listChanged": False
                        }
                    },
                    "serverInfo": {
                        "name": "n8n-mcp",
                        "version": "0.1.0"
                    }
                }
            }

        # 2. Tools Discovery
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": self.registry.get_tools_manifest()
                }
            }

        # 3. Tool Execution
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            try:
                raw_result = await self.registry.dispatch(tool_name, arguments)
                if isinstance(raw_result, BaseModel):
                    output_text = raw_result.model_dump_json(indent=2)
                elif isinstance(raw_result, (dict, list)):
                    output_text = json.dumps(raw_result, indent=2, default=str)
                else:
                    output_text = str(raw_result)

                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": output_text
                            }
                        ]
                    }
                }
            except Exception as exc:
                logger.exception(f"Error executing tool '{tool_name}'")
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error executing tool '{tool_name}': {str(exc)}"
                            }
                        ]
                    }
                }

        # 4. Ping
        elif method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {}
            }

        # Method Not Found
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32601,
                "message": f"Method '{method}' not found"
            }
        }

    async def run_stdio(self) -> None:
        """Runs the MCP server over standard input and output streams with ProactorEventLoop deadlock prevention."""
        loop = asyncio.get_running_loop()

        try:
            while True:
                # Thread-pool executor reading avoids Windows Proactor pipe deadlocks
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:
                    break

                line_str = line.strip()
                if not line_str:
                    continue

                try:
                    request = json.loads(line_str)
                    response = await self.handle_request(request)
                    if response is not None:
                        response_json = json.dumps(response)
                        sys.stdout.write(response_json + "\n")
                        sys.stdout.flush()
                except json.JSONDecodeError as exc:
                    err_resp = {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32700,
                            "message": f"Invalid JSON received: {exc}"
                        }
                    }
                    sys.stdout.write(json.dumps(err_resp) + "\n")
                    sys.stdout.flush()
                except Exception as exc:
                    logger.exception("Unexpected server runtime error")
        finally:
            logger.info("Shutting down n8n MCP server...")
            await self.client.close()

    def run(self, transport: str = "stdio") -> None:
        """
        Runs the server with platform-specific adjustments.
        Ensures Windows ProactorEventLoop and UTF-8 encoding on standard streams.
        """
        # 1. Windows Proactor loop compatibility
        if sys.platform == "win32":
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            except Exception:
                pass

        # 2. Ensure UTF-8 streams for stdio transport
        if hasattr(sys.stdin, "reconfigure"):
            try:
                sys.stdin.reconfigure(encoding="utf-8")
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass

        logger.info(f"Starting n8n MCP Server with transport: {transport}")

        if transport == "fastmcp":
            self.mcp.run(transport="stdio")
        elif transport == "stdio":
            try:
                self.mcp.run(transport="stdio")
            except Exception as e:
                logger.warning(f"FastMCP stdio encountered error, falling back to native stdio: {e}")
                asyncio.run(self.run_stdio())
        elif transport == "native-stdio":
            asyncio.run(self.run_stdio())
        elif transport in ("sse", "streamable-http"):
            self.mcp.run(transport=transport)  # type: ignore
        else:
            raise ValueError(f"Unsupported transport: {transport}. Choose from: stdio, native-stdio, sse, streamable-http, fastmcp")
