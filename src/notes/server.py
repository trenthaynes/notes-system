"""Notes MCP server entry point (skeleton).

Tools will be added in later units.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("notes-mcp")


def main() -> None:
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
