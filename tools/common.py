"""
Shared utilities for the CAF Companion tools.
LLM client helper, input normalization, knowledge loader.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from agent_framework import Message
from agent_framework.azure import AzureOpenAIChatClient

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
    if not api_key:
        logger.debug("[LLM] AZURE_OPENAI_API_KEY not set")
        return {"error": "AZURE_OPENAI_API_KEY not set"}

    client = AzureOpenAIChatClient(
        endpoint=endpoint,
        deployment_name=deployment,
        api_key=api_key,
    )

    response = await client.get_response(
        messages=[
            Message("system", [system_prompt]),
            Message("user", [user_content[:20000]]),
        ],
        temperature=0.1,
    )

    raw = response.messages[0].text if response.messages else "{}"
    # Strip markdown fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)


# ---------------------------------------------------------------------------
#  Input normalization
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
#  Knowledge loader
# ---------------------------------------------------------------------------

def _load_knowledge(filename: str) -> dict[str, Any]:
    """Load a JSON knowledge file from the knowledge/ directory."""
    knowledge_dir = Path(__file__).parent.parent / "knowledge"
    filepath = knowledge_dir / filename
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)
