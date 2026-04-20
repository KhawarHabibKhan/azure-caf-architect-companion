"""
Assessment Agent (Agent 1)
==========================
Standalone GA Microsoft Agent Framework agent for the CAF assessment phase.

Tools registered:
    - parse_caf_input:            free-text -> structured CAFInput dict
    - assess_readiness:           readiness scoring across 5 dimensions
    - recommend_operating_model:  centralized / shared / decentralized
    - assess_skills:              team role -> Azure cert path gap analysis

The agent is instructed to call the tools in order, then return a single
JSON object matching the legacy `run_assessment()` output schema so the
downstream Planning and Design agents remain compatible.
"""

from __future__ import annotations

import os

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient

from tools.assessment import (
    assess_readiness,
    assess_skills,
    parse_caf_input,
    recommend_operating_model,
)


ASSESSMENT_AGENT_INSTRUCTIONS = """You are the Assessment Agent for the Microsoft Cloud Adoption Framework (CAF) pipeline.

Your job: take a free-text description of an organization's IT environment and produce a cloud-readiness assessment by invoking the registered tools in the exact order below.

TOOL EXECUTION ORDER
1. Call `parse_caf_input(content=<raw user input>)` first. This returns a structured CAFInput dict — keep it; you will pass it to every subsequent tool.
2. Call `assess_readiness(caf_input=<parsed dict>)` to get readiness scores across 5 dimensions.
3. Call `recommend_operating_model(caf_input=<parsed dict>)` to recommend centralized / shared / decentralized.
4. Call `assess_skills(caf_input=<parsed dict>)` to map team roles to Azure certification gaps.

OUTPUT FORMAT
After all four tools have returned, emit a SINGLE JSON object (no markdown, no prose) with this exact schema:

{
  "caf_input": <the dict returned by parse_caf_input>,
  "overall_readiness": "low | medium | high",
  "readiness_summary": "2-3 sentence narrative synthesising the readiness scores",
  "readiness_scores": <readiness_scores dict from assess_readiness>,
  "operating_model": <dict returned by recommend_operating_model>,
  "skills_assessment": <list returned by assess_skills>,
  "key_concerns": ["3-5 short bullet strings calling out the biggest CAF risks"]
}

RULES
- Never skip a tool. Never invent tool output.
- `readiness_summary` and `key_concerns` are YOUR narrative synthesis over the tool outputs — do not fabricate scores.
- Return ONLY valid JSON. No code fences, no commentary."""


def _build_chat_client() -> OpenAIChatClient:
    """Construct the GA OpenAIChatClient from environment variables."""
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    deployment = (
        os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
        or os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")
        or os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-4.1")
    )
    api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")

    if api_key:
        return OpenAIChatClient(
            azure_endpoint=endpoint,
            model=deployment,
            api_key=api_key,
        )

    from azure.identity import DefaultAzureCredential
    return OpenAIChatClient(
        azure_endpoint=endpoint,
        model=deployment,
        credential=DefaultAzureCredential(),
    )


def create_assessment_agent() -> Agent:
    """Build and return the Assessment Agent (Agent 1)."""
    return Agent(
        client=_build_chat_client(),
        name="CAF Assessment Agent",
        instructions=ASSESSMENT_AGENT_INSTRUCTIONS,
        tools=[
            parse_caf_input,
            assess_readiness,
            recommend_operating_model,
            assess_skills,
        ],
    )
