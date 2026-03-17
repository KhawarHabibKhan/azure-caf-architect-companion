"""
Azure CAF Architect Companion - Core Engine
=============================================
Automates the pre-deployment phases of Microsoft's Cloud Adoption Framework.
Chains three agent stages: Assessment → Plan & Analyze → Design & Report.

Sections:
  1. Input Parser
  2. Assessment Engine (Agent 1)
  3. Plan & Analyze Engine (Agent 2)
  4. Design Engine (Agent 3)
  5. Excalidraw Landing Zone Renderer
  6. PNG Export
  7. File Save Helpers
  8. Report Builder
  9. Pipeline Orchestrator
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from agent_framework import ChatMessage
from agent_framework.azure import AzureOpenAIChatClient

from knowledge.caf_prompts import PARSE_INPUT_PROMPT

logger = logging.getLogger("caf-companion")


# ---------------------------------------------------------------------------
#  LLM client helper
# ---------------------------------------------------------------------------

async def _llm_call(system_prompt: str, user_content: str) -> dict[str, Any]:
    """Send a system + user message to Azure OpenAI and return parsed JSON."""
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    deployment = (
        os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
        or os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")
        or os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-4.1")
    )

    if not endpoint:
        logger.debug("[LLM] AZURE_OPENAI_ENDPOINT not set")
        return {"error": "AZURE_OPENAI_ENDPOINT not set"}

    api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
    if api_key:
        client = AzureOpenAIChatClient(
            endpoint=endpoint,
            deployment_name=deployment,
            api_key=api_key,
        )
    else:
        from azure.identity import DefaultAzureCredential
        client = AzureOpenAIChatClient(
            endpoint=endpoint,
            deployment_name=deployment,
            credential=DefaultAzureCredential(),
        )

    response = await client.get_response(
        messages=[
            ChatMessage(role="system", text=system_prompt),
            ChatMessage(role="user", text=user_content[:20000]),
        ],
        temperature=0.1,
    )

    raw = response.text or "{}"
    # Strip markdown fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)


# ═══════════════════════════════════════════════════════════════════════════
#  1.  INPUT PARSER
# ═══════════════════════════════════════════════════════════════════════════

_INPUT_DEFAULTS = {
    "company_name": "",
    "industry": "",
    "employee_count": 0,
    "compliance_requirements": [],
    "current_infrastructure": [],
    "applications": [],
    "team": [],
    "budget_migration": 0,
    "budget_monthly_target": 0,
    "timeline_months": 12,
    "additional_context": "",
}


def _normalize_input(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and fill defaults for parsed input."""
    result = {}
    for key, default in _INPUT_DEFAULTS.items():
        value = raw.get(key, default)
        if isinstance(default, int) and not isinstance(value, (int, float)):
            value = default
        if isinstance(default, list) and not isinstance(value, list):
            value = default
        result[key] = value
    return result


async def parse_caf_input(content: str) -> dict[str, Any]:
    """Extract structured CAF input from free-text using LLM.

    Takes any description of an organization's IT environment and returns
    a normalized dict matching the CAFInput schema.
    """
    logger.debug("[PARSER] Parsing input (%d chars)", len(content))

    try:
        raw = await _llm_call(PARSE_INPUT_PROMPT, content)
        if "error" in raw:
            logger.debug("[PARSER] LLM error: %s", raw["error"])
            return _normalize_input({})
    except Exception as exc:
        logger.debug("[PARSER] LLM call failed: %s", exc)
        return _normalize_input({})

    result = _normalize_input(raw)
    logger.debug("[PARSER] Extracted: company=%s, apps=%d, team=%d",
                 result["company_name"],
                 len(result["applications"]),
                 len(result["team"]))
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  2.  ASSESSMENT ENGINE (Agent 1)
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
#  3.  PLAN & ANALYZE ENGINE (Agent 2)
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
#  4.  DESIGN ENGINE (Agent 3)
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
#  5.  EXCALIDRAW LANDING ZONE RENDERER
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
#  6.  PNG EXPORT
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
#  7.  FILE SAVE HELPERS
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
#  8.  REPORT BUILDER
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
#  9.  PIPELINE ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════
