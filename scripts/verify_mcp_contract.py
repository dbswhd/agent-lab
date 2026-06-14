#!/usr/bin/env python3
"""Audit agent-lab-research + quant-trading MCP tool surfaces."""

from __future__ import annotations

import asyncio
import json

from agent_lab.mcp_tool_contract import audit_mcp_contracts


def main() -> int:
    report = asyncio.run(audit_mcp_contracts())
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
