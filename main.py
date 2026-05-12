"""
Azure CAF Architect Companion - Local Dev Entry Point
======================================================
**DEV-ONLY.** Launches the GA Microsoft Agent Framework DevUI
(`agent_framework.devui`) on http://127.0.0.1:8088, hosting:

    - CAF Assessment Agent  (4 tools — parse, readiness, op model, skills)
    - CAF Plan Agent        (5 tools — workloads, waves, costs, risks, governance)
    - CAF Design Agent      (6 tools — design, elements, layout, file, png, report)
    - SequentialBuilder workflow chaining all three

Use the DevUI to invoke any single agent in isolation, drive the full
workflow, watch tool calls fire in real time, and inspect each agent's
response. Auth is provided by `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT`
(read at agent-construction time via `python-dotenv`).

DevUI is a sample app from Microsoft and is **not intended for production
use**. The production entry point for this project is `api.py` (FastAPI +
React frontend), which exposes the same workflow over HTTP.

Usage:
    python main.py
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv(override=True)

from agent_framework.devui import serve

from agents import (
    create_assessment_agent,
    create_design_agent,
    create_plan_agent,
    create_workflow,
)


def main() -> None:
    assessment_agent = create_assessment_agent()
    plan_agent = create_plan_agent()
    design_agent = create_design_agent()
    workflow = create_workflow()

    print("Azure CAF Architect Companion — DevUI starting on http://127.0.0.1:8088")
    print("  - Hosts the 3 CAF agents individually plus the chained workflow.")
    print("  - For production, run `python -m uvicorn api:app` instead.")
    serve(
        entities=[assessment_agent, plan_agent, design_agent, workflow],
        port=8088,
        auto_open=True,
    )


if __name__ == "__main__":
    main()
