"""
Orchestrator — Sequential workflow of Agents 1 → 2 → 3
=======================================================
Built with the GA Microsoft Agent Framework `SequentialBuilder`
(`agent_framework.orchestrations.SequentialBuilder`). Each participant
agent sees the full conversation history, including earlier agents'
JSON responses as prior assistant messages.

Public API:

    create_workflow() -> Workflow
        Construct the 3-agent sequential workflow.

    run_pipeline(content: str) -> dict
        Run the workflow to completion and return the final CAF report
        (Design Agent's JSON output, with `diagram.excalidraw_file` loaded
        from disk).

    stream_pipeline(content: str) -> AsyncIterator[dict]
        Yield per-agent progress events as each participant finishes.
        Event schema:
            {"agent": "assessment|plan|design|complete",
             "status": "running|done|error",
             "data":  <parsed JSON | None>,
             "error": <str | absent>}
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any, cast

from agent_framework import Message
from agent_framework.orchestrations import SequentialBuilder

from agents.assessment_agent import create_assessment_agent
from agents.design_agent import create_design_agent
from agents.plan_agent import create_plan_agent

logger = logging.getLogger("caf-companion")


# Map the agent's `name=` kwarg (as passed to Agent()) to a short key used
# in streamed events. Keep in sync with the three create_*_agent factories.
_AGENT_DISPLAY_TO_KEY: dict[str, str] = {
    "CAF Assessment Agent": "assessment",
    "CAF Plan Agent": "plan",
    "CAF Design Agent": "design",
}

_PARTICIPANT_ORDER: tuple[str, ...] = ("assessment", "plan", "design")


def create_workflow():
    """Construct the 3-agent sequential workflow (Assessment → Plan → Design)."""
    return SequentialBuilder(
        participants=[
            create_assessment_agent(),
            create_plan_agent(),
            create_design_agent(),
        ]
    ).build()


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


def _inject_excalidraw_file(report: dict[str, Any]) -> dict[str, Any]:
    """Read the saved `.excalidraw` file from disk into `report.diagram.excalidraw_file`.

    The Design Agent leaves `excalidraw_file` as `null` by instruction so the
    orchestrator can populate it after the file is flushed.
    """
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


def _last_assistant(conversation: list[Message]) -> Message | None:
    for msg in reversed(conversation):
        if getattr(msg, "role", None) == "assistant":
            return msg
    return None


async def run_pipeline(content: str) -> dict[str, Any]:
    """Run the workflow to completion and return the final CAF report."""
    workflow = create_workflow()

    design_output: dict[str, Any] | None = None
    async for event in workflow.run(content, stream=True):
        if event.type != "output":
            continue
        conversation = cast(list[Message], event.data)
        last = _last_assistant(conversation)
        if last is None:
            continue
        key = _AGENT_DISPLAY_TO_KEY.get(getattr(last, "author_name", "") or "")
        if key == "design":
            design_output = _extract_json(last.text)

    if design_output is None:
        raise RuntimeError("Workflow completed but the Design Agent produced no output")

    return _inject_excalidraw_file(design_output)


async def stream_pipeline(content: str) -> AsyncIterator[dict[str, Any]]:
    """Yield per-agent progress events as each participant finishes."""
    workflow = create_workflow()

    # Announce the first participant as running before we get any events back.
    yield {"agent": _PARTICIPANT_ORDER[0], "status": "running", "data": None}

    seen_done: set[str] = set()
    outputs: dict[str, dict[str, Any]] = {}

    async for event in workflow.run(content, stream=True):
        if event.type != "output":
            continue
        conversation = cast(list[Message], event.data)
        last = _last_assistant(conversation)
        if last is None:
            continue
        key = _AGENT_DISPLAY_TO_KEY.get(getattr(last, "author_name", "") or "")
        if not key or key in seen_done:
            continue

        try:
            parsed = _extract_json(last.text)
        except Exception as exc:
            yield {"agent": key, "status": "error", "data": None, "error": str(exc)}
            return

        seen_done.add(key)
        outputs[key] = parsed
        yield {"agent": key, "status": "done", "data": parsed}

        try:
            next_idx = _PARTICIPANT_ORDER.index(key) + 1
        except ValueError:
            continue
        if next_idx < len(_PARTICIPANT_ORDER):
            yield {
                "agent": _PARTICIPANT_ORDER[next_idx],
                "status": "running",
                "data": None,
            }

    report = outputs.get("design")
    if report is None:
        yield {
            "agent": "complete",
            "status": "error",
            "data": None,
            "error": "Design Agent produced no output",
        }
        return

    yield {"agent": "complete", "status": "done", "data": _inject_excalidraw_file(report)}
