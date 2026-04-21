"""
Orchestrator — Linear chain of Agents 1 → 2 → 3
================================================
Single entry point for the CAF Companion pipeline.

    run_pipeline(content: str) -> dict

Creates the three GA agents, runs them sequentially, parses the JSON each
one emits, feeds the output of each into the next, and finally reads the
saved Excalidraw file from disk to populate `diagram.excalidraw_file`
(the Design Agent leaves it `null` by instruction).

The returned dict matches the legacy `run_full_pipeline()` / `build_caf_report()`
schema, so `api.py`, `run_local.py`, and `main.py` can drop it in without
further adaptation.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from agents.assessment_agent import create_assessment_agent
from agents.design_agent import create_design_agent
from agents.plan_agent import create_plan_agent

logger = logging.getLogger("caf-companion")


def _extract_json(text: str) -> dict[str, Any]:
    """Parse an agent's text output as JSON, tolerating markdown fences and prose."""
    if not text:
        raise ValueError("Agent returned empty output")

    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


async def run_pipeline(content: str) -> dict[str, Any]:
    """Run the full CAF pipeline: Assessment → Plan → Design → final report."""
    assessment_agent = create_assessment_agent()
    plan_agent = create_plan_agent()
    design_agent = create_design_agent()

    # ── Agent 1: Assessment ─────────────────────────────────────────────
    logger.debug("[ORCH] Running Assessment Agent")
    a1_response = await assessment_agent.run(content)
    assessment = _extract_json(a1_response.text)
    caf_input = assessment.get("caf_input", {})

    # ── Agent 2: Plan ───────────────────────────────────────────────────
    logger.debug("[ORCH] Running Plan Agent")
    a2_response = await plan_agent.run(json.dumps(assessment))
    plan = _extract_json(a2_response.text)

    # ── Agent 3: Design ─────────────────────────────────────────────────
    logger.debug("[ORCH] Running Design Agent")
    a3_input = json.dumps({
        "caf_input": caf_input,
        "assessment": assessment,
        "plan": plan,
    })
    a3_response = await design_agent.run(a3_input)
    report = _extract_json(a3_response.text)

    # ── Post-process: inject excalidraw file contents ───────────────────
    diagram = report.get("diagram") or {}
    local_file = diagram.get("local_file")
    if local_file:
        try:
            with open(local_file, "r", encoding="utf-8") as f:
                diagram["excalidraw_file"] = json.load(f)
                report["diagram"] = diagram
        except Exception as exc:
            logger.debug("[ORCH] Could not read excalidraw file %s: %s", local_file, exc)

    return report
