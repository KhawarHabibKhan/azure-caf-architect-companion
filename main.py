"""
Azure CAF Architect Companion - Hosted Agent Entry Point
=========================================================
Uses Microsoft Agent Framework with Azure OpenAI.
Ready for deployment to Foundry Hosted Agent service.
"""

import asyncio
import json
import os
from typing import Annotated

from dotenv import load_dotenv

load_dotenv(override=True)

from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential

from tools import (
    run_full_pipeline,
    parse_caf_input,
    run_assessment,
    generate_mcp_landing_zone_elements,
    render_via_excalidraw_mcp,
)

PROJECT_ENDPOINT = os.getenv("AZURE_AI_PROJECT_ENDPOINT") or os.getenv("PROJECT_ENDPOINT")
MODEL_DEPLOYMENT_NAME = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME") or os.getenv(
    "MODEL_DEPLOYMENT_NAME", "gpt-4.1"
)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

async def run_cloud_adoption_review(
    content: Annotated[str, "Description of the organization's current IT infrastructure, applications, team, budget, and timeline. Any format: plaintext, structured, bullet points, etc."],
    render_diagram: bool = True,
) -> str:
    """Run a complete Cloud Adoption Framework assessment.

    Pipeline: parse input → readiness assessment → workload classification →
    migration wave planning → cost estimation → risk assessment →
    governance recommendations → landing zone design → diagram generation → report.

    Returns a JSON report with executive summary, workload plan, risk register,
    landing zone architecture, and Excalidraw diagram.
    """
    report = await run_full_pipeline(content)

    if render_diagram and report.get("landing_zone"):
        mcp_elems = generate_mcp_landing_zone_elements(report["landing_zone"])
        mcp_result = render_via_excalidraw_mcp(mcp_elems["elements_json"])
        if report.get("diagram"):
            report["diagram"]["mcp_render"] = mcp_result

    return json.dumps(report, indent=2, default=str)


async def run_assessment_only(
    content: Annotated[str, "Description of the organization's current IT setup. Any format."],
) -> str:
    """Run only the readiness assessment (Agent 1).

    Returns readiness scores, operating model recommendation, and skills gap analysis.
    Useful for a quick check before running the full pipeline.
    """
    caf_input = await parse_caf_input(content)
    assessment = await run_assessment(caf_input)
    return json.dumps({"caf_input": caf_input, "assessment": assessment}, indent=2, default=str)


# ---------------------------------------------------------------------------
# Agent Instructions
# ---------------------------------------------------------------------------

INSTRUCTIONS = """You are the Azure CAF Architect Companion — an AI agent that automates
the pre-deployment phases of Microsoft's Cloud Adoption Framework.

When a user describes their current IT environment (infrastructure, applications,
team, budget, compliance requirements), you run a complete CAF assessment and produce:

1. Readiness assessment with operating model recommendation
2. Workload classification using the 7 R's (retire, retain, rehost, refactor, rearchitect, rebuild, replace)
3. Migration wave plan with sequencing
4. Cost estimation using real Azure pricing
5. Risk register with mitigations
6. Governance and security recommendations
7. Azure landing zone architecture design
8. Architecture diagram (Excalidraw)

Use the `run_cloud_adoption_review` tool for a full assessment.
Use the `run_assessment_only` tool for a quick readiness check.

Always present results in a clear, structured format. Highlight key risks,
costs, and recommendations prominently.
"""


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

async def main():
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(
            project_endpoint=PROJECT_ENDPOINT,
            model_deployment_name=MODEL_DEPLOYMENT_NAME,
            async_credential=credential,
            agent_name="Azure CAF Architect Companion",
        ).as_agent(
            instructions=INSTRUCTIONS,
            tools=[run_cloud_adoption_review, run_assessment_only],
        ) as agent,
    ):
        # For local testing
        print("Azure CAF Architect Companion agent is ready.")
        result = await agent.run("Hello! I'm ready to analyze your infrastructure.")
        print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
