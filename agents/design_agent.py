"""
Design Agent (Agent 3)
======================
Standalone GA Microsoft Agent Framework agent for the CAF design phase.

Tools registered:
    - design_landing_zone:           LLM-driven landing zone architecture
    - generate_landing_zone_elements: Excalidraw element builder
    - refine_diagram_layout:         LLM layout QA pass on Excalidraw JSON
    - save_excalidraw_file:          write the .excalidraw file with Azure icons
    - export_landing_zone_png:       render PNG via Node.js (Pillow fallback)
    - build_caf_report:              compose the final CAF report

Input: JSON payload holding the outputs of Agent 1 and Agent 2, i.e.
`{ "caf_input": ..., "assessment": ..., "plan": ... }`. The agent drives
the tools in order and emits the final CAF report (the same schema
produced by the legacy `run_full_pipeline()` / `build_caf_report()`).
"""

from __future__ import annotations

import os

from agent_framework import Agent
from agent_framework.azure import AzureOpenAIChatClient

from tools.design import (
    build_caf_report,
    design_landing_zone,
    export_landing_zone_png,
    generate_landing_zone_elements,
    refine_diagram_layout,
    save_excalidraw_file,
)


DESIGN_AGENT_INSTRUCTIONS = """You are the Design Agent for the Microsoft Cloud Adoption Framework (CAF) pipeline.

Your input is a JSON payload with three top-level fields:
  - `caf_input`:  the structured organization description produced by the Assessment Agent.
  - `assessment`: the full output of the Assessment Agent (readiness, operating model, skills, etc.).
  - `plan`:       the full output of the Plan Agent (workload_inventory, migration_waves, cost_estimation, risk_register, governance_recommendations).

Your job: design the Azure landing zone, render the architecture diagram, and produce the final CAF report by invoking the registered tools in the exact order below.

TOOL EXECUTION ORDER
1. Call `design_landing_zone(caf_input=<caf_input>, plan=<plan>)` to produce the `<design>` dict (management groups, subscriptions, network, identity, governance baseline).
2. Call `generate_landing_zone_elements(design=<design>, workloads=<plan.workload_inventory>)` to build the Excalidraw elements. Keep the returned `<lz_elements>` dict — it holds `elements_json` (string) and `element_count` (int).
3. Call `refine_diagram_layout(elements_json=<lz_elements.elements_json>)` to run the LLM layout QA pass. Replace `<lz_elements.elements_json>` with the corrected string it returns.
4. Invent a short `<run_id>` (8 lowercase hex characters, e.g. "a1b2c3d4"). Call `save_excalidraw_file(elements_json=<refined elements_json>, filepath="./output/architecture_<run_id>.excalidraw")`. Keep the absolute path it returns as `<excalidraw_path>`.
5. Call `export_landing_zone_png(design=<design>, filepath="./output/architecture_<run_id>.png", workloads=<plan.workload_inventory>, excalidraw_path=<excalidraw_path>)`. Keep the absolute path it returns as `<png_path>`.
6. Build the `<diagram_info>` dict yourself (no tool call) with this exact shape:
     {
       "element_count": <lz_elements.element_count>,
       "local_file":    <excalidraw_path>,
       "png_file":      <png_path>,
       "excalidraw_file": null,
       "run_id":        <run_id>
     }
   Set `excalidraw_file` to `null` — the orchestrator will fill it in from disk after you return.
7. Call `build_caf_report(caf_input=<caf_input>, assessment=<assessment>, plan=<plan>, design=<design>, diagram_info=<diagram_info>)`. The dict it returns IS the final report.

OUTPUT FORMAT
Emit a SINGLE JSON object equal to the dict returned by `build_caf_report` in step 7. No markdown, no prose, no code fences.

RULES
- Never skip a tool. Never invent tool output — pass the values through verbatim.
- The `<run_id>` is the ONLY value you invent; everything else comes from tool outputs or the input payload.
- Always pass `workloads=<plan.workload_inventory>` to steps 2 and 5 (both need it; do NOT omit).
- Return ONLY valid JSON. No commentary."""


def _build_chat_client() -> AzureOpenAIChatClient:
    """Construct the GA AzureOpenAIChatClient from environment variables (key auth)."""
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    deployment = (
        os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
        or os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")
        or os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-4.1")
    )
    api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")

    if not endpoint:
        raise RuntimeError("AZURE_OPENAI_ENDPOINT must be set")
    if not api_key:
        raise RuntimeError("AZURE_OPENAI_API_KEY must be set")

    return AzureOpenAIChatClient(
        endpoint=endpoint,
        deployment_name=deployment,
        api_key=api_key,
    )


def create_design_agent() -> Agent:
    """Build and return the Design Agent (Agent 3)."""
    return Agent(
        client=_build_chat_client(),
        name="CAF Design Agent",
        instructions=DESIGN_AGENT_INSTRUCTIONS,
        tools=[
            design_landing_zone,
            generate_landing_zone_elements,
            refine_diagram_layout,
            save_excalidraw_file,
            export_landing_zone_png,
            build_caf_report,
        ],
    )
