"""py -m mcp_server —— 以 stdio 起 MCP server。"""
from mcp_server.server import build_server

if __name__ == "__main__":
    build_server().run()
