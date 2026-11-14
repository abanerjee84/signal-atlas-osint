"""Run the MCP adapter from any working directory."""

import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    runpy.run_module("backend.mcp_server", run_name="__main__")
