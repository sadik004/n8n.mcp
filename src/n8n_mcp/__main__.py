"""
Command-line interface entry point for n8n MCP Server.
"""

from __future__ import annotations
import argparse
import asyncio
import logging
import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from n8n_mcp.config import N8nConfig
from n8n_mcp.server import N8nMcpServer, create_mcp_server

console = Console(stderr=True)


def parse_args() -> argparse.Namespace:
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="n8n-mcp",
        description="Production-grade Model Context Protocol (MCP) Server for n8n workflow automation.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "native-stdio", "sse", "streamable-http", "fastmcp"],
        default="stdio",
        help="MCP communication transport (default: stdio)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Runs diagnostic health check against n8n instance and local catalog",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="n8n-mcp 0.1.0",
    )
    return parser.parse_args()


async def run_diagnostics_check(config: N8nConfig) -> None:
    """Performs live connectivity check and prints Rich summary."""
    server = N8nMcpServer(config=config)
    console.print(
        Panel.fit(
            f"[bold cyan]n8n MCP Server Diagnostics[/bold cyan]\n"
            f"[dim]Base URL:[/dim] {config.n8n_base_url}\n"
            f"[dim]Snapshots Directory:[/dim] {config.snapshots_dir}\n"
            f"[dim]Stealth Scraper URL:[/dim] {config.behavioral_playwright_url}",
            title="Configuration",
            border_style="cyan",
        )
    )

    # 1. Check tools count
    manifest = server.registry.get_tools_manifest()
    console.print(f"[green]✔ Registered Tools:[/green] {len(manifest)} available in registry")

    # 2. Check local catalog
    catalog_nodes = server.registry.catalog_engine.search_nodes("")
    console.print(f"[green]✔ Node Catalog Engine:[/green] {len(catalog_nodes)} core nodes indexed in memory")

    # 3. Check n8n connectivity
    console.print("[dim]Pinging n8n instance...[/dim]")
    health = await server.registry.client.health_check()
    status_color = "green" if health.get("status") == "ok" else "yellow"
    console.print(f"[{status_color}]✔ n8n Health Check:[/{status_color}] {health}")

    await server.client.close()


def main() -> None:
    """Configures logging and starts the n8n MCP server."""
    # Ensure stdout is exclusively reserved for JSON-RPC messages; logs go to stderr
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    args = parse_args()
    config = N8nConfig()

    if args.check:
        try:
            asyncio.run(run_diagnostics_check(config))
            sys.exit(0)
        except Exception as exc:
            console.print(f"[bold red]Diagnostics Failed:[/bold red] {exc}")
            sys.exit(1)

    server = N8nMcpServer(config=config)

    try:
        server.run(transport=args.transport)
    except (KeyboardInterrupt, SystemExit):
        logging.info("n8n MCP server stopped by user.")


if __name__ == "__main__":
    main()
