from mcp.server.fastmcp import FastMCP

from reaper_mcp.instructions import load_instructions
from reaper_mcp.reaper_client import ReaperClient
from reaper_mcp.tool_registry import register_all_tools

mcp = FastMCP("ReaperMCP", instructions=load_instructions())
client = ReaperClient()

register_all_tools(mcp)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
