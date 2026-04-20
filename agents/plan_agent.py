"""
Plan Agent (Agent 2)
====================
Standalone GA Microsoft Agent Framework agent for the CAF planning phase.

Tools registered:
    - classify_workloads:     7 R's classification per application
    - plan_migration_waves:   group classified workloads into sequenced waves
    - estimate_costs:         live Azure Retail Prices + fallback estimates
    - assess_risks:           compliance-aware risk register
    - recommend_governance:   policies, tagging, security, cost management

Input: the JSON output from the Assessment Agent (Agent 1). The agent reads
`caf_input` out of that payload, then drives the tools in order and emits a
single JSON object matching the legacy `run_plan()` output schema so the
Design Agent (Agent 3) remains compatible.
"""

from __future__ import annotations

import os

from agent_framework import Agent
from agent_framework.azure import AzureOpenAIChatClient

from tools.planning import (
    assess_risks,
    classify_workloads,
    estimate_costs,
    plan_migration_waves,
    recommend_governance,
)


PLAN_AGENT_INSTRUCTIONS = """You are the Plan Agent for the Microsoft Cloud Adoption Framework (CAF) pipeline.

Your input is the JSON payload produced by the Assessment Agent. It contains a `caf_input` field (the structured organization description) plus readiness, operating-model, and skills results. Use `caf_input` as the source of truth for organization details, and drive the registered tools in the exact order below to produce a cloud adoption plan.

TOOL EXECUTION ORDER
1. Call `classify_workloads(caf_input=<caf_input dict>)` to tag every application with one of the 7 R's (retire, rehost, refactor, rearchitect, replace, rebuild, retain) and target Azure services. Keep the returned list — it is `<classified>`.
2. Call `plan_migration_waves(classified=<classified>, timeline_months=<caf_input.timeline_months or 12>)` to group the workloads into sequenced waves.
3. Call `estimate_costs(classified=<classified>, region="eastus")` to compute monthly line items and total monthly spend. Use the default region unless `caf_input.additional_context` clearly specifies another Azure region.
4. Call `assess_risks(caf_input=<caf_input>, classified=<classified>)` to produce a compliance-aware risk register.
5. Call `recommend_governance(caf_input=<caf_input>)` to produce policies, tagging, security, and cost-management recommendations.

OUTPUT FORMAT
After all five tools have returned, emit a SINGLE JSON object (no markdown, no prose) with this exact schema:

{
  "workload_inventory": <list returned by classify_workloads>,
  "migration_waves": <list returned by plan_migration_waves>,
  "cost_estimation": {
    "line_items": <cost line_items list from estimate_costs>,
    "total_monthly": <total_monthly number from estimate_costs>,
    "migration_budget_estimate": <total_monthly * 6, rounded to 2 decimals>,
    "within_budget": <true if total_monthly <= caf_input.budget_monthly_target (or true when budget_monthly_target is 0/missing), else false>
  },
  "risk_register": <list returned by assess_risks>,
  "governance_recommendations": <dict returned by recommend_governance>
}

RULES
- Never skip a tool. Never invent tool output — copy the values through verbatim.
- Compute `migration_budget_estimate` and `within_budget` yourself from the cost total and the budget in `caf_input`; do not ask a tool for them.
- If a tool returns an empty list or dict, pass the empty value through — do not fabricate substitutes.
- Return ONLY valid JSON. No code fences, no commentary."""


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


def create_plan_agent() -> Agent:
    """Build and return the Plan Agent (Agent 2)."""
    return Agent(
        client=_build_chat_client(),
        name="CAF Plan Agent",
        instructions=PLAN_AGENT_INSTRUCTIONS,
        tools=[
            classify_workloads,
            plan_migration_waves,
            estimate_costs,
            assess_risks,
            recommend_governance,
        ],
    )
