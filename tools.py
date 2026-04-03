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
  5a. MCP Diagram Renderer (Excalidraw MCP Server Integration)
  6. PNG Export
  7. File Save Helpers
  7a. Diagram QA Agent (LLM-powered layout review & fix)
  8. Report Builder
  9. Pipeline Orchestrator
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from agent_framework import Message
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

_READINESS_WEIGHTS = {
    "infrastructure_complexity": 0.15,
    "application_portfolio": 0.20,
    "team_capability": 0.30,
    "compliance_burden": 0.15,
    "organizational_readiness": 0.20,
}

_SCORE_VALUES = {"low": 1, "medium": 2, "high": 3}


def assess_readiness(caf_input: dict[str, Any]) -> dict[str, Any]:
    """Score cloud readiness based on team, infrastructure, and compliance.

    Returns readiness scores per dimension and an overall readiness level.
    Rule-based heuristics — no LLM needed.
    """
    apps = caf_input.get("applications", [])
    team = caf_input.get("team", [])
    compliance = caf_input.get("compliance_requirements", [])
    budget = caf_input.get("budget_migration", 0)
    timeline = caf_input.get("timeline_months", 12)
    infra = caf_input.get("current_infrastructure", [])

    # --- Infrastructure complexity ---
    dc_count = sum(1 for i in infra if i.get("type") == "data_center")
    if dc_count >= 3 or len(apps) > 15:
        infra_score = "low"
    elif dc_count >= 2 or len(apps) > 8:
        infra_score = "medium"
    else:
        infra_score = "high"

    # --- Application portfolio ---
    legacy_keywords = ["cobol", "as/400", "mainframe", "classic asp", "vb6", "fortran"]
    legacy_count = sum(
        1 for a in apps
        if any(kw in (a.get("technology_stack", "") + " " + a.get("description", "")).lower()
               for kw in legacy_keywords)
    )
    if legacy_count > len(apps) * 0.5:
        app_score = "low"
    elif legacy_count > 0:
        app_score = "medium"
    else:
        app_score = "high"

    # --- Team capability ---
    total_staff = sum(m.get("count", 0) for m in team)
    cloud_experienced = sum(
        m.get("count", 0) for m in team
        if m.get("cloud_experience", "none") in ("intermediate", "advanced")
    )
    if total_staff == 0:
        team_score = "low"
    elif cloud_experienced / max(total_staff, 1) > 0.3:
        team_score = "high"
    elif cloud_experienced > 0:
        team_score = "medium"
    else:
        team_score = "low"

    # --- Compliance burden ---
    strict_frameworks = {"HIPAA", "PCI_DSS", "PCI-DSS", "FedRAMP"}
    strict_count = sum(1 for c in compliance if c.upper().replace("-", "_") in
                       {s.upper().replace("-", "_") for s in strict_frameworks})
    if strict_count >= 2 or len(compliance) >= 3:
        compliance_score = "low"
    elif strict_count >= 1:
        compliance_score = "medium"
    else:
        compliance_score = "high"

    # --- Organizational readiness ---
    cost_per_app = budget / max(len(apps), 1)
    if cost_per_app > 80000 and timeline >= 12:
        org_score = "high"
    elif cost_per_app > 40000 and timeline >= 6:
        org_score = "medium"
    else:
        org_score = "low"

    scores = {
        "infrastructure_complexity": infra_score,
        "application_portfolio": app_score,
        "team_capability": team_score,
        "compliance_burden": compliance_score,
        "organizational_readiness": org_score,
    }

    # Weighted overall
    weighted = sum(
        _SCORE_VALUES[scores[dim]] * weight
        for dim, weight in _READINESS_WEIGHTS.items()
    )
    if weighted >= 2.5:
        overall = "high"
    elif weighted >= 1.8:
        overall = "medium"
    else:
        overall = "low"

    return {
        "overall_readiness": overall,
        "readiness_scores": scores,
    }


def recommend_operating_model(caf_input: dict[str, Any]) -> dict[str, Any]:
    """Recommend centralized, shared, or decentralized operating model.

    Based on CAF guidance: team size, cloud experience, workload count,
    and compliance requirements.
    """
    team = caf_input.get("team", [])
    apps = caf_input.get("applications", [])
    compliance = caf_input.get("compliance_requirements", [])
    employees = caf_input.get("employee_count", 0)

    total_staff = sum(m.get("count", 0) for m in team)
    cloud_experienced = sum(
        m.get("count", 0) for m in team
        if m.get("cloud_experience", "none") in ("intermediate", "advanced")
    )
    workload_count = len(apps)

    # Decision logic based on CAF operating model guidance
    if employees < 50 or (workload_count <= 5 and total_staff <= 5):
        model = "centralized"
        rationale = ("Small organization with few workloads. A single cloud team "
                     "can manage governance, security, and operations without bottlenecks.")
    elif cloud_experienced > total_staff * 0.5 and workload_count > 15 and not compliance:
        model = "decentralized"
        rationale = ("Large, cloud-experienced team with many workloads and no strict "
                     "compliance. Teams can operate independently with high autonomy.")
    else:
        model = "shared"
        rationale = ("Mid-size organization where a platform team should handle landing "
                     "zones and guardrails, while workload teams operate within them. "
                     "Balances governance with team agility.")

    return {
        "recommended": model,
        "rationale": rationale,
    }


# Azure certification paths mapped to common IT roles
_CERT_MAP = {
    "system administrator": {"cert": "AZ-104", "name": "Azure Administrator Associate"},
    "sysadmin": {"cert": "AZ-104", "name": "Azure Administrator Associate"},
    "network engineer": {"cert": "AZ-700", "name": "Azure Network Engineer Associate"},
    "security analyst": {"cert": "AZ-500", "name": "Azure Security Engineer Associate"},
    "security engineer": {"cert": "AZ-500", "name": "Azure Security Engineer Associate"},
    "developer": {"cert": "AZ-204", "name": "Azure Developer Associate"},
    "software engineer": {"cert": "AZ-204", "name": "Azure Developer Associate"},
    "it director": {"cert": "AZ-305", "name": "Azure Solutions Architect Expert"},
    "it manager": {"cert": "AZ-305", "name": "Azure Solutions Architect Expert"},
    "architect": {"cert": "AZ-305", "name": "Azure Solutions Architect Expert"},
    "dba": {"cert": "DP-300", "name": "Azure Database Administrator Associate"},
    "database administrator": {"cert": "DP-300", "name": "Azure Database Administrator Associate"},
    "devops engineer": {"cert": "AZ-400", "name": "Azure DevOps Engineer Expert"},
    "data engineer": {"cert": "DP-203", "name": "Azure Data Engineer Associate"},
}


def assess_skills(caf_input: dict[str, Any]) -> list[dict[str, Any]]:
    """Map current team roles to Azure certification paths and identify gaps.

    Returns a list of skill gap entries with recommended training.
    """
    team = caf_input.get("team", [])
    results = []

    for member in team:
        role = member.get("role", "").lower()
        experience = member.get("cloud_experience", "none")
        current_skills = member.get("current_skills", [])

        # Find best matching cert
        cert_info = None
        for key, info in _CERT_MAP.items():
            if key in role:
                cert_info = info
                break

        if not cert_info:
            cert_info = {"cert": "AZ-900", "name": "Azure Fundamentals"}

        # Determine gap and priority
        if experience in ("advanced",):
            gap = "Minor — may need specific Azure service training"
            priority = "long-term"
        elif experience in ("intermediate",):
            gap = "Moderate — needs Azure-specific certification"
            priority = "short-term"
        else:
            gap = "Significant — no cloud experience, needs foundational + role-specific training"
            priority = "immediate"

        results.append({
            "role": member.get("role", "Unknown"),
            "current_skills": current_skills,
            "gap": gap,
            "recommended_training": f"{cert_info['cert']} - {cert_info['name']}",
            "priority": priority,
        })

    return results


async def run_assessment(caf_input: dict[str, Any]) -> dict[str, Any]:
    """Run full Agent 1 assessment: readiness + operating model + skills.

    Uses rule-based heuristics for readiness and operating model,
    then LLM for a narrative summary.
    """
    readiness = assess_readiness(caf_input)
    operating_model = recommend_operating_model(caf_input)
    skills = assess_skills(caf_input)

    # Generate narrative summary via LLM
    from knowledge.caf_prompts import ASSESSMENT_PROMPT
    summary_input = json.dumps({
        "organization": {
            "company_name": caf_input.get("company_name", ""),
            "industry": caf_input.get("industry", ""),
            "employee_count": caf_input.get("employee_count", 0),
            "compliance": caf_input.get("compliance_requirements", []),
        },
        "applications_count": len(caf_input.get("applications", [])),
        "team_count": sum(m.get("count", 0) for m in caf_input.get("team", [])),
        "budget_migration": caf_input.get("budget_migration", 0),
        "timeline_months": caf_input.get("timeline_months", 12),
        "readiness_scores": readiness["readiness_scores"],
    }, indent=2)

    try:
        llm_result = await _llm_call(ASSESSMENT_PROMPT, summary_input)
        readiness_summary = llm_result.get("readiness_summary", "")
        key_concerns = llm_result.get("key_concerns", [])
        # Use LLM's team structure recommendation if available
        if llm_result.get("operating_model", {}).get("recommended_structure"):
            operating_model["recommended_structure"] = llm_result["operating_model"]["recommended_structure"]
    except Exception:
        readiness_summary = ""
        key_concerns = []

    return {
        "overall_readiness": readiness["overall_readiness"],
        "readiness_summary": readiness_summary,
        "readiness_scores": readiness["readiness_scores"],
        "operating_model": operating_model,
        "skills_assessment": skills,
        "key_concerns": key_concerns,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  3.  PLAN & ANALYZE ENGINE (Agent 2)
# ═══════════════════════════════════════════════════════════════════════════

def _load_knowledge(filename: str) -> dict[str, Any]:
    """Load a JSON knowledge file from the knowledge/ directory."""
    knowledge_dir = Path(__file__).parent / "knowledge"
    filepath = knowledge_dir / filename
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


async def classify_workloads(caf_input: dict[str, Any]) -> list[dict[str, Any]]:
    """Classify each application workload using the 7 R's framework.

    Uses LLM with the Azure services catalog injected into context.
    """
    apps = caf_input.get("applications", [])
    if not apps:
        return []

    azure_catalog = _load_knowledge("azure_services.json")

    from knowledge.caf_prompts import CLASSIFY_WORKLOAD_PROMPT

    user_content = json.dumps({
        "applications": apps,
        "azure_services_catalog": azure_catalog,
    }, indent=2)

    try:
        result = await _llm_call(CLASSIFY_WORKLOAD_PROMPT, user_content)
    except Exception as exc:
        logger.debug("[PLAN] Workload classification failed: %s", exc)
        return []

    # Result should be a list; handle if LLM wraps it in an object
    if isinstance(result, dict):
        result = result.get("workloads", result.get("classifications", []))
    if not isinstance(result, list):
        return []

    return result


async def plan_migration_waves(
    classified: list[dict[str, Any]],
    timeline_months: int = 12,
) -> list[dict[str, Any]]:
    """Group classified workloads into migration waves.

    Uses LLM with wave planning rules from CAF methodology.
    """
    if not classified:
        return []

    from knowledge.caf_prompts import PLAN_PROMPT

    user_content = json.dumps({
        "classified_workloads": classified,
        "timeline_months": timeline_months,
    }, indent=2)

    try:
        result = await _llm_call(PLAN_PROMPT, user_content)
    except Exception as exc:
        logger.debug("[PLAN] Wave planning failed: %s", exc)
        return []

    waves = result.get("migration_waves", [])
    if not isinstance(waves, list):
        return []

    return waves


# ---------------------------------------------------------------------------
#  Azure Retail Prices API
# ---------------------------------------------------------------------------

_AZURE_PRICING_URL = "https://prices.azure.com/api/retail/prices"


async def _fetch_azure_price(
    service_name: str,
    sku_name: str = "",
    region: str = "eastus",
) -> float:
    """Fetch a monthly price from the Azure Retail Prices API.

    Public API, no authentication required. Uses OData filters.
    Returns monthly cost estimate or 0.0 if not found.
    """
    import httpx

    filters = [
        f"serviceName eq '{service_name}'",
        f"armRegionName eq '{region}'",
        "priceType eq 'Consumption'",
    ]
    if sku_name:
        filters.append(f"skuName eq '{sku_name}'")

    params = {"$filter": " and ".join(filters), "$top": "5"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(_AZURE_PRICING_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.debug("[PRICING] API call failed for %s: %s", service_name, exc)
        return 0.0

    items = data.get("Items", [])
    if not items:
        return 0.0

    # Pick the first matching retail price and convert hourly to monthly
    unit_price = items[0].get("retailPrice", 0.0)
    unit = items[0].get("unitOfMeasure", "")

    if "Hour" in unit:
        return round(unit_price * 730, 2)  # ~730 hours/month
    elif "Month" in unit:
        return round(unit_price, 2)
    elif "GB" in unit:
        return round(unit_price, 4)  # per-GB pricing, caller multiplies
    else:
        return round(unit_price, 2)


async def estimate_costs(
    classified: list[dict[str, Any]],
    region: str = "eastus",
) -> dict[str, Any]:
    """Estimate monthly Azure costs for classified workloads.

    Attempts live pricing from Azure Retail Prices API.
    Falls back to catalog-based estimates if API is unavailable.
    """
    line_items = []
    total_monthly = 0.0

    # Static fallback estimates per service type (monthly USD)
    _FALLBACK_COSTS = {
        "Azure Virtual Machines": 140,
        "Azure App Service": 150,
        "Azure SQL Database": 250,
        "Azure SQL Managed Instance": 500,
        "Azure Cosmos DB": 300,
        "Azure Database for PostgreSQL": 200,
        "Azure Database for MySQL": 180,
        "Azure Blob Storage": 50,
        "Azure Files": 80,
        "Azure Kubernetes Service": 350,
        "Azure Container Apps": 200,
        "Azure Functions": 50,
        "Azure Firewall": 900,
        "Azure Bastion": 140,
        "Azure Key Vault": 10,
        "Microsoft Sentinel": 500,
        "Azure ExpressRoute": 200,
        "Azure VPN Gateway": 140,
        "Microsoft Entra ID": 120,
        "Azure Monitor": 100,
    }

    for workload in classified:
        classification = workload.get("classification", "")
        if classification in ("retire", "retain"):
            continue

        services = workload.get("target_azure_services", [])
        for service_name in services:
            # Try live pricing first
            price = await _fetch_azure_price(service_name, region=region)

            # Fall back to static estimate
            if price == 0.0:
                price = _FALLBACK_COSTS.get(service_name, 100)

            line_items.append({
                "category": workload.get("workload_name", "Unknown"),
                "azure_service": service_name,
                "monthly_cost": price,
                "notes": "",
            })
            total_monthly += price

    # Add baseline platform costs
    platform_services = [
        ("Azure Firewall", 900),
        ("Azure Bastion", 140),
        ("Azure Key Vault", 10),
        ("Azure Monitor", 100),
        ("Microsoft Entra ID P2", 120),
    ]
    for svc_name, fallback in platform_services:
        price = await _fetch_azure_price(svc_name, region=region)
        if price == 0.0:
            price = fallback
        line_items.append({
            "category": "Platform",
            "azure_service": svc_name,
            "monthly_cost": price,
            "notes": "Shared platform service",
        })
        total_monthly += price

    return {
        "line_items": line_items,
        "total_monthly": round(total_monthly, 2),
        "region": region,
    }


async def assess_risks(
    caf_input: dict[str, Any],
    classified: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate a risk register for the migration.

    Uses LLM with compliance controls injected into context.
    """
    compliance_reqs = caf_input.get("compliance_requirements", [])
    compliance_map = _load_knowledge("compliance_controls.json")

    # Build relevant compliance context
    relevant_controls = {}
    for req in compliance_reqs:
        key = req.upper().replace("-", "_")
        for ckey, cval in compliance_map.items():
            if ckey.upper().replace("-", "_") == key:
                relevant_controls[ckey] = cval
                break

    from knowledge.caf_prompts import RISK_PROMPT

    user_content = json.dumps({
        "organization": {
            "company_name": caf_input.get("company_name", ""),
            "industry": caf_input.get("industry", ""),
            "employee_count": caf_input.get("employee_count", 0),
            "compliance_requirements": compliance_reqs,
        },
        "classified_workloads": classified,
        "applicable_compliance_controls": relevant_controls,
        "team_summary": caf_input.get("team", []),
        "budget_migration": caf_input.get("budget_migration", 0),
        "timeline_months": caf_input.get("timeline_months", 12),
    }, indent=2)

    try:
        result = await _llm_call(RISK_PROMPT, user_content)
    except Exception as exc:
        logger.debug("[PLAN] Risk assessment failed: %s", exc)
        return []

    if isinstance(result, dict):
        result = result.get("risks", result.get("risk_register", []))
    if not isinstance(result, list):
        return []

    return result


async def recommend_governance(caf_input: dict[str, Any]) -> dict[str, Any]:
    """Generate governance, security, tagging, and cost management recommendations.

    Uses LLM with compliance context.
    """
    from knowledge.caf_prompts import GOVERNANCE_PROMPT

    compliance_reqs = caf_input.get("compliance_requirements", [])
    compliance_map = _load_knowledge("compliance_controls.json")

    relevant_controls = {}
    for req in compliance_reqs:
        key = req.upper().replace("-", "_")
        for ckey, cval in compliance_map.items():
            if ckey.upper().replace("-", "_") == key:
                relevant_controls[ckey] = cval
                break

    user_content = json.dumps({
        "organization": {
            "company_name": caf_input.get("company_name", ""),
            "industry": caf_input.get("industry", ""),
            "compliance_requirements": compliance_reqs,
        },
        "applicable_compliance_controls": relevant_controls,
        "budget_monthly_target": caf_input.get("budget_monthly_target", 0),
    }, indent=2)

    try:
        result = await _llm_call(GOVERNANCE_PROMPT, user_content)
    except Exception as exc:
        logger.debug("[PLAN] Governance recommendation failed: %s", exc)
        return {"policies": [], "tagging_strategy": {}, "security": [], "cost_management": []}

    return result


async def run_plan(
    caf_input: dict[str, Any],
    assessment: dict[str, Any],
) -> dict[str, Any]:
    """Run full Agent 2 pipeline: classify → waves → costs → risks → governance."""
    classified = await classify_workloads(caf_input)
    waves = await plan_migration_waves(classified, caf_input.get("timeline_months", 12))
    costs = await estimate_costs(classified)
    risks = await assess_risks(caf_input, classified)
    governance = await recommend_governance(caf_input)

    budget_migration = caf_input.get("budget_migration", 0)
    budget_monthly = caf_input.get("budget_monthly_target", 0)

    return {
        "workload_inventory": classified,
        "migration_waves": waves,
        "cost_estimation": {
            "line_items": costs["line_items"],
            "total_monthly": costs["total_monthly"],
            "migration_budget_estimate": costs["total_monthly"] * 6,  # rough 6-month estimate
            "within_budget": costs["total_monthly"] <= budget_monthly if budget_monthly else True,
        },
        "risk_register": risks,
        "governance_recommendations": governance,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  4.  DESIGN ENGINE (Agent 3)
# ═══════════════════════════════════════════════════════════════════════════

async def design_landing_zone(
    caf_input: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    """Design Azure landing zone architecture using LLM.

    Generates management group hierarchy, subscription layout,
    hub-spoke network, and identity design based on CAF Ready methodology.
    """
    from knowledge.caf_prompts import DESIGN_PROMPT

    user_content = json.dumps({
        "organization": {
            "company_name": caf_input.get("company_name", ""),
            "industry": caf_input.get("industry", ""),
            "compliance_requirements": caf_input.get("compliance_requirements", []),
        },
        "workload_inventory": plan.get("workload_inventory", []),
        "migration_waves": plan.get("migration_waves", []),
        "infrastructure": caf_input.get("current_infrastructure", []),
    }, indent=2)

    try:
        result = await _llm_call(DESIGN_PROMPT, user_content)
    except Exception as exc:
        logger.debug("[DESIGN] Landing zone design failed: %s", exc)
        return _default_landing_zone(caf_input, plan)

    # Ensure all expected keys exist
    for key in ("management_groups", "subscriptions", "network_design",
                "identity_design", "governance_baseline"):
        if key not in result:
            result[key] = {}

    return result


def _default_landing_zone(
    caf_input: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    """Generate a sensible default landing zone when LLM is unavailable."""
    company = caf_input.get("company_name", "Organization")
    workloads = plan.get("workload_inventory", [])

    # Build spoke VNets from workloads
    spokes = []
    cidr_counter = 1
    for w in workloads:
        classification = w.get("classification", "")
        if classification in ("retire", "retain", "replace"):
            continue
        spokes.append({
            "name": f"{w.get('workload_name', 'workload').lower().replace(' ', '-')}-spoke",
            "cidr": f"10.{cidr_counter}.0.0/16",
            "workload": w.get("workload_name", ""),
            "peering_to_hub": True,
        })
        cidr_counter += 1

    return {
        "management_groups": {
            "root": {
                "name": f"{company} Root",
                "children": [
                    {"name": "Platform", "purpose": "Shared infrastructure", "children": [
                        {"name": "Connectivity", "purpose": "Hub networking, DNS, ExpressRoute", "children": []},
                        {"name": "Identity", "purpose": "Entra ID Connect, domain controllers", "children": []},
                        {"name": "Management", "purpose": "Log Analytics, monitoring, automation", "children": []},
                    ]},
                    {"name": "Workloads", "purpose": "Application workloads", "children": [
                        {"name": "Production", "purpose": "Production subscriptions", "children": []},
                        {"name": "Non-Production", "purpose": "Dev/test/staging", "children": []},
                    ]},
                    {"name": "Decommissioned", "purpose": "Retired workloads", "children": []},
                ],
            }
        },
        "subscriptions": [
            {"name": "Connectivity", "purpose": "Hub networking", "management_group": "Platform", "workloads": []},
            {"name": "Identity", "purpose": "Identity services", "management_group": "Platform", "workloads": []},
            {"name": "Management", "purpose": "Monitoring and management", "management_group": "Platform", "workloads": []},
        ],
        "network_design": {
            "topology": "hub-spoke",
            "hub_vnet": {
                "name": "hub-vnet",
                "cidr": "10.0.0.0/16",
                "components": ["Azure Firewall", "Azure Bastion", "VPN Gateway"],
            },
            "spoke_vnets": spokes,
            "on_prem_connectivity": "VPN",
        },
        "identity_design": {
            "provider": "Microsoft Entra ID",
            "tier": "P2",
            "features": ["Conditional Access", "MFA", "PIM"],
        },
        "governance_baseline": {
            "policy_assignments": [
                "Require encryption at rest",
                "Deny public IP on VMs",
                "Require resource tagging",
            ],
            "monitoring": ["Azure Monitor", "Log Analytics"],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
#  5.  EXCALIDRAW LANDING ZONE RENDERER
# ═══════════════════════════════════════════════════════════════════════════

import math

_AZURE_COLORS: dict[str, dict[str, str]] = {
    "management_group": {"bg": "#e3f2fd", "border": "#1565c0"},
    "subscription":     {"bg": "#e8f5e9", "border": "#2e7d32"},
    "vnet_hub":         {"bg": "#f3e5f5", "border": "#7b1fa2"},
    "vnet_spoke":       {"bg": "#ede7f6", "border": "#512da8"},
    "compute":          {"bg": "#fff3e0", "border": "#e65100"},
    "database":         {"bg": "#fffde7", "border": "#f9a825"},
    "storage":          {"bg": "#e0f7fa", "border": "#00838f"},
    "security":         {"bg": "#fce4ec", "border": "#c62828"},
    "networking":       {"bg": "#f3e5f5", "border": "#6a1b9a"},
    "identity":         {"bg": "#e8eaf6", "border": "#283593"},
    "on_premises":      {"bg": "#eceff1", "border": "#455a64"},
    "monitoring":       {"bg": "#f1f8e9", "border": "#558b2f"},
}
_AZ_DEFAULT_COL = {"bg": "#e7f5ff", "border": "#1c7ed6"}
_BOX_W, _BOX_H = 180, 85
_MG_W, _MG_H = 200, 70


def _az_svg_data_url(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


# Azure service icons keyed by color_key
_AZ_ICON_SVGS: dict[str, str] = {
    "management_group": _az_svg_data_url(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="#1565c0" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="8" y="2" width="8" height="5" rx="1"/>'
        '<rect x="1" y="17" width="6" height="5" rx="1"/>'
        '<rect x="9" y="17" width="6" height="5" rx="1"/>'
        '<rect x="17" y="17" width="6" height="5" rx="1"/>'
        '<line x1="12" y1="7" x2="12" y2="11"/>'
        '<line x1="4" y1="11" x2="20" y2="11"/>'
        '<line x1="4" y1="11" x2="4" y2="17"/>'
        '<line x1="12" y1="11" x2="12" y2="17"/>'
        '<line x1="20" y1="11" x2="20" y2="17"/>'
        "</svg>"
    ),
    "subscription": _az_svg_data_url(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="#2e7d32" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<polyline points="12 2 2 7 12 12 22 7 12 2"/>'
        '<polyline points="2 17 12 22 22 17"/>'
        '<polyline points="2 12 12 17 22 12"/>'
        "</svg>"
    ),
    "vnet_hub": _az_svg_data_url(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="#7b1fa2" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/>'
        '<circle cx="18" cy="19" r="3"/>'
        '<line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>'
        '<line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>'
        "</svg>"
    ),
    "vnet_spoke": _az_svg_data_url(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="#512da8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="6" y1="3" x2="6" y2="15"/>'
        '<circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/>'
        '<path d="M18 9a9 9 0 0 1-9 9"/>'
        "</svg>"
    ),
    "compute": _az_svg_data_url(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="#e65100" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="4" y="4" width="16" height="16" rx="2"/>'
        '<rect x="9" y="9" width="6" height="6"/>'
        '<line x1="9" y1="2" x2="9" y2="4"/><line x1="15" y1="2" x2="15" y2="4"/>'
        '<line x1="9" y1="20" x2="9" y2="22"/><line x1="15" y1="20" x2="15" y2="22"/>'
        '<line x1="20" y1="9" x2="22" y2="9"/><line x1="20" y1="14" x2="22" y2="14"/>'
        '<line x1="2" y1="9" x2="4" y2="9"/><line x1="2" y1="14" x2="4" y2="14"/>'
        "</svg>"
    ),
    "database": _az_svg_data_url(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="#f9a825" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<ellipse cx="12" cy="5" rx="9" ry="3"/>'
        '<path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>'
        '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>'
        "</svg>"
    ),
    "storage": _az_svg_data_url(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="#00838f" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="2" y="2" width="20" height="8" rx="2" ry="2"/>'
        '<rect x="2" y="14" width="20" height="8" rx="2" ry="2"/>'
        '<line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/>'
        "</svg>"
    ),
    "security": _az_svg_data_url(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="#c62828" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>'
        '<path d="M7 11V7a5 5 0 0 1 10 0v4"/>'
        "</svg>"
    ),
    "networking": _az_svg_data_url(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="#6a1b9a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M5 12.55a11 11 0 0 1 14.08 0"/>'
        '<path d="M1.42 9a16 16 0 0 1 21.16 0"/>'
        '<path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>'
        '<circle cx="12" cy="20" r="1"/>'
        "</svg>"
    ),
    "identity": _az_svg_data_url(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="#283593" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>'
        '<circle cx="12" cy="7" r="4"/>'
        "</svg>"
    ),
    "on_premises": _az_svg_data_url(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="#455a64" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="2" y="7" width="20" height="14" rx="2" ry="2"/>'
        '<path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>'
        "</svg>"
    ),
    "monitoring": _az_svg_data_url(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        ' stroke="#558b2f" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<line x1="18" y1="20" x2="18" y2="10"/>'
        '<line x1="12" y1="20" x2="12" y2="4"/>'
        '<line x1="6" y1="20" x2="6" y2="14"/>'
        "</svg>"
    ),
}


def _az_rect(
    elem_id: str, label: str, color_key: str,
    x: int, y: int, w: int = _BOX_W, h: int = _BOX_H,
    dashed: bool = False,
) -> list[dict]:
    """Create an Excalidraw rectangle with an icon and centered label."""
    col = _AZURE_COLORS.get(color_key, _AZ_DEFAULT_COL)
    grp = f"grp_{elem_id}"
    rect: dict = {
        "type": "rectangle", "id": elem_id,
        "x": x, "y": y, "width": w, "height": h,
        "strokeColor": col["border"], "backgroundColor": col["bg"],
        "fillStyle": "solid", "roundness": {"type": 3},
        "groupIds": [grp],
    }
    if dashed:
        rect["strokeStyle"] = "dashed"
    # Icon — show for standard-sized boxes (not oversized hub/spoke containers)
    elems: list[dict] = [rect]
    if h in (_BOX_H, _MG_H) and color_key in _AZ_ICON_SVGS:
        icon_size = 24
        icon_x = x + (w - icon_size) // 2
        elems.append({
            "type": "image", "id": f"{elem_id}_icon",
            "x": icon_x, "y": y + 6, "width": icon_size, "height": icon_size,
            "angle": 0, "strokeColor": "transparent", "backgroundColor": "transparent",
            "fillStyle": "hachure", "strokeWidth": 1, "roughness": 1, "opacity": 100,
            "groupIds": [grp], "fileId": f"az_icon_{color_key}",
            "scale": [1, 1], "status": "saved", "isDeleted": False,
        })
        text_y = y + 34
    else:
        text_y = y + (h // 2) - 10
    elems.append({
        "type": "text", "id": f"{elem_id}_lbl",
        "x": x + 8, "y": text_y,
        "width": w - 16, "height": 20,
        "text": label, "fontSize": 13,
        "textAlign": "center", "strokeColor": "#1e1e1e",
        "groupIds": [grp],
    })
    return elems


def _az_arrow(
    elem_id: str,
    x0: int, y0: int, x1: int, y1: int,
    label: str = "", dashed: bool = False,
) -> list[dict]:
    """Create an Excalidraw arrow between two points."""
    dx, dy = x1 - x0, y1 - y0
    arrow = {
        "type": "arrow", "id": elem_id,
        "x": x0, "y": y0,
        "width": abs(dx), "height": abs(dy),
        "strokeColor": "#495057",
        "points": [[0, 0], [dx, dy]],
        "startArrowhead": None, "endArrowhead": "arrow",
    }
    if dashed:
        arrow["strokeStyle"] = "dashed"
    elems = [arrow]
    if label:
        elems.append({
            "type": "text", "id": f"{elem_id}_lbl",
            "x": x0 + dx // 2 - 50, "y": y0 + dy // 2 - 10,
            "width": 100, "height": 16,
            "text": label, "fontSize": 11,
            "textAlign": "center", "strokeColor": "#868e96",
        })
    return elems


def _render_mgmt_group_tree(
    node: dict, x: int, y: int, depth: int = 0,
) -> tuple[list[dict], int]:
    """Recursively render management group hierarchy. Returns (elements, next_x)."""
    elems: list[dict] = []
    name = node.get("name", "Unknown")
    node_id = f"mg_{name.lower().replace(' ', '_')}_{depth}"
    w = max(_MG_W, len(name) * 10 + 20)

    elems.extend(_az_rect(node_id, name, "management_group", x, y, w, _MG_H))

    children = node.get("children", [])
    if not children:
        return elems, x + w + 30

    child_y = y + _MG_H + 60
    child_x = x
    child_centers = []

    for child in children:
        child_elems, next_x = _render_mgmt_group_tree(child, child_x, child_y, depth + 1)
        elems.extend(child_elems)
        child_center_x = (child_x + next_x - 30) // 2
        child_centers.append(child_center_x)
        child_x = next_x

    # Draw lines from parent to children
    parent_cx = x + w // 2
    parent_bottom = y + _MG_H
    for i, ccx in enumerate(child_centers):
        elems.extend(_az_arrow(
            f"{node_id}_to_child_{i}",
            parent_cx, parent_bottom, ccx, child_y,
        ))

    return elems, child_x


def _section_header(elem_id: str, text: str, x: int, y: int, w: int = 600) -> list[dict]:
    """Create a section header label."""
    return [{
        "type": "text", "id": elem_id,
        "x": x, "y": y, "width": w, "height": 28,
        "text": text, "fontSize": 20, "fontFamily": 1,
        "textAlign": "left", "strokeColor": "#1565c0",
    }]


def _service_color_key(service_name: str) -> str:
    """Map an Azure service name to a color key."""
    s = service_name.lower()
    if any(k in s for k in ("sql", "database", "postgres", "mysql", "cosmos", "redis")):
        return "database"
    if any(k in s for k in ("storage", "blob", "data lake", "file")):
        return "storage"
    if any(k in s for k in ("vm", "virtual machine", "container", "app service", "function")):
        return "compute"
    if any(k in s for k in ("monitor", "log analytics", "insight", "sentinel")):
        return "monitoring"
    if any(k in s for k in ("firewall", "defender", "key vault", "waf")):
        return "security"
    if any(k in s for k in ("vnet", "gateway", "dns", "front door", "load balancer")):
        return "networking"
    if any(k in s for k in ("entra", "identity", "ad ")):
        return "identity"
    return "compute"


def _render_hub_spoke(
    network: dict, x: int, y: int,
    workloads: list[dict] | None = None,
) -> tuple[list[dict], int]:
    """Render hub-spoke network topology with workload details.

    Returns (elements, bottom_y) so the caller knows where the zone ends.
    """
    elems: list[dict] = []
    hub = network.get("hub_vnet", {})
    spokes = network.get("spoke_vnets", [])
    on_prem = network.get("on_prem_connectivity", "VPN")

    # Build workload lookup: workload_name -> target_azure_services
    wl_list = workloads or []
    wl_services: dict[str, list[str]] = {}
    for w in wl_list:
        wl_services[w.get("workload_name", "")] = w.get("target_azure_services", [])

    # ── Hub VNet ─────────────────────────────────────────────────────────
    components = hub.get("components", [])
    cols = min(len(components), 2)
    rows = math.ceil(len(components) / max(cols, 1))
    hub_comp_w, hub_comp_h = 140, 40
    hub_pad = 15
    hub_w = max(320, cols * (hub_comp_w + hub_pad) + hub_pad * 2)
    hub_h = 65 + rows * (hub_comp_h + 10) + hub_pad

    hub_name = hub.get("name", "Hub VNet")
    hub_cidr = hub.get("cidr", "10.0.0.0/16")
    elems.extend(_az_rect("hub_vnet", f"{hub_name}\n{hub_cidr}", "vnet_hub",
                          x, y, hub_w, hub_h, dashed=True))

    # Hub components inside — 2-column grid
    for i, comp_name in enumerate(components):
        col_i = i % cols
        row_i = i // cols
        cx = x + hub_pad + col_i * (hub_comp_w + hub_pad)
        cy = y + 60 + row_i * (hub_comp_h + 10)
        ctype = "security" if any(k in comp_name.lower() for k in ("firewall", "waf", "defender")) else "networking"
        elems.extend(_az_rect(f"hub_comp_{i}", comp_name, ctype,
                              cx, cy, hub_comp_w, hub_comp_h))

    hub_cx = x + hub_w // 2
    hub_cy = y + hub_h // 2

    # ── On-premises ──────────────────────────────────────────────────────
    on_prem_x = x - 250
    on_prem_y = y + hub_h // 2 - _BOX_H // 2
    elems.extend(_az_rect("on_prem", f"On-Premises\nData Center", "on_premises",
                          on_prem_x, on_prem_y))
    elems.extend(_az_arrow("on_prem_to_hub",
                           on_prem_x + _BOX_W, on_prem_y + _BOX_H // 2,
                           x, hub_cy,
                           on_prem, dashed=True))

    # ── Spokes — 2-column grid (prod left, non-prod right) ──────────────
    if not spokes:
        return elems, y + hub_h

    spoke_start_y = y + hub_h + 60
    spoke_col_w = 300
    spoke_gap_x = 40
    spoke_gap_y = 20
    svc_box_w, svc_box_h = 130, 32

    # Place spokes in 2-column grid
    cols_count = min(3, max(1, len(spokes)))
    bottom_y = spoke_start_y

    for i, spoke in enumerate(spokes):
        col_i = i % cols_count
        row_i = i // cols_count
        spoke_id = f"spoke_{i}"

        # Figure out services for this spoke (fuzzy match — spoke name may
        # combine multiple workloads like "App / API (Production)")
        wl_name = spoke.get("workload", "")
        services: list[str] = []
        for plan_name, plan_svcs in wl_services.items():
            if plan_name.lower() in wl_name.lower() or wl_name.lower() in plan_name.lower():
                for s in plan_svcs:
                    if s not in services:
                        services.append(s)
        services = services[:4]  # max 4 services shown

        # Spoke box sizing — taller if it has services
        svc_rows = math.ceil(len(services) / 2) if services else 0
        spoke_h = 55 + svc_rows * (svc_box_h + 8) + (15 if services else 0)
        spoke_w = spoke_col_w

        spoke_x = x - (cols_count * (spoke_col_w + spoke_gap_x)) // 2 + hub_w // 2 + col_i * (spoke_col_w + spoke_gap_x)
        spoke_y = spoke_start_y + row_i * (spoke_h + spoke_gap_y + 10)

        spoke_name = spoke.get("name", f"Spoke {i}")
        spoke_cidr = spoke.get("cidr", "")
        spoke_workload = spoke.get("workload", "")
        spoke_title = spoke_workload if spoke_workload else spoke_name
        spoke_subtitle = spoke_cidr
        spoke_label = f"{spoke_title}\n{spoke_subtitle}" if spoke_subtitle else spoke_title

        elems.extend(_az_rect(spoke_id, spoke_label, "vnet_spoke",
                              spoke_x, spoke_y, spoke_w, spoke_h, dashed=True))

        # Peering arrow from hub bottom to spoke top
        elems.extend(_az_arrow(
            f"hub_to_{spoke_id}",
            hub_cx, y + hub_h,
            spoke_x + spoke_w // 2, spoke_y,
            "peering",
        ))

        # Azure services inside spoke — 2-column mini-grid
        if services:
            for j, svc in enumerate(services):
                svc_col = j % 2
                svc_row = j // 2
                svc_x = spoke_x + 10 + svc_col * (svc_box_w + 10)
                svc_y = spoke_y + 50 + svc_row * (svc_box_h + 8)
                svc_color = _service_color_key(svc)
                # Shorten long names
                svc_short = svc.replace("Azure ", "").replace(" - Flexible Server", "")
                elems.extend(_az_rect(
                    f"{spoke_id}_svc_{j}", svc_short, svc_color,
                    svc_x, svc_y, svc_box_w, svc_box_h,
                ))

        bottom_y = max(bottom_y, spoke_y + spoke_h)

    return elems, bottom_y


def generate_landing_zone_elements(
    design: dict[str, Any],
    workloads: list[dict] | None = None,
) -> dict[str, Any]:
    """Build Excalidraw elements for the full landing zone architecture.

    Layout:
      Zone 1: Title
      Zone 2: Management group hierarchy
      Zone 3: Hub-spoke network with workload details
      Zone 4: Identity & Governance info panels

    Returns {"elements_json": str, "element_count": int}.
    """
    elems: list[dict] = []
    cursor_y = 0

    # ── Zone 1: Title ────────────────────────────────────────────────────
    elems.append({
        "type": "text", "id": "title",
        "x": 0, "y": cursor_y, "width": 600, "height": 32,
        "text": "Azure Landing Zone Architecture", "fontSize": 24, "fontFamily": 1,
        "textAlign": "left", "strokeColor": "#1e1e1e",
    })
    cursor_y += 50

    # ── Zone 2: Management group hierarchy ───────────────────────────────
    mg = design.get("management_groups", {})
    root = mg.get("root", mg)
    if root:
        elems.extend(_section_header("hdr_mg", "Management Group Hierarchy", 0, cursor_y))
        cursor_y += 40
        mg_elems, mg_width = _render_mgmt_group_tree(root, 0, cursor_y)
        elems.extend(mg_elems)
        # Calculate MG tree height (deepest leaf)
        mg_ys = [e.get("y", 0) + e.get("height", 0) for e in mg_elems if e.get("type") == "rectangle"]
        mg_bottom = max(mg_ys) if mg_ys else cursor_y + 200
        cursor_y = mg_bottom + 60

    # ── Zone 3: Hub-spoke network ────────────────────────────────────────
    network = design.get("network_design", {})
    if network:
        elems.extend(_section_header("hdr_network", "Network Topology (Hub & Spoke)", 0, cursor_y))
        cursor_y += 40
        hub_spoke_elems, bottom_y = _render_hub_spoke(network, 200, cursor_y, workloads)
        elems.extend(hub_spoke_elems)
        cursor_y = bottom_y + 60

    # ── Zone 4: Identity & Governance panels ─────────────────────────────
    identity = design.get("identity_design", {})
    governance = design.get("governance_baseline", {})

    if identity or governance:
        elems.extend(_section_header("hdr_infra", "Identity & Governance", 0, cursor_y))
        cursor_y += 40
        panel_x = 0

        if identity:
            provider = identity.get("provider", "Microsoft Entra ID")
            tier = identity.get("tier", "")
            features = identity.get("features", [])[:5]
            id_text = f"{provider}" + (f" ({tier})" if tier else "")
            if features:
                id_text += "\n" + "\n".join(f"• {f}" for f in features)
            id_h = 40 + len(features) * 18
            elems.extend(_az_rect("panel_identity", id_text, "identity",
                                  panel_x, cursor_y, 280, max(id_h, 80)))
            panel_x += 310

        if governance:
            policies = governance.get("policy_assignments", [])[:5]
            gov_text = "Azure Policy"
            if policies:
                gov_text += "\n" + "\n".join(f"• {p}" for p in policies)
            gov_h = 40 + len(policies) * 18
            elems.extend(_az_rect("panel_governance", gov_text, "security",
                                  panel_x, cursor_y, 320, max(gov_h, 80)))

    # ── Camera ───────────────────────────────────────────────────────────
    if elems:
        all_x = [e.get("x", 0) for e in elems if "x" in e]
        all_y = [e.get("y", 0) for e in elems if "y" in e]
        all_r = [e.get("x", 0) + e.get("width", 0) for e in elems if "width" in e]
        all_b = [e.get("y", 0) + e.get("height", 0) for e in elems if "height" in e]
        if all_x and all_y:
            cam_x = min(all_x) - 60
            cam_y = min(all_y) - 40
            cam_w = max(all_r) - cam_x + 60
            cam_h = max(all_b) - cam_y + 60
            elems.insert(0, {
                "type": "cameraUpdate",
                "x": cam_x, "y": cam_y,
                "width": cam_w, "height": cam_h,
            })

    return {"elements_json": json.dumps(elems), "element_count": len(elems)}


# ═══════════════════════════════════════════════════════════════════════════
#  5a.  MCP DIAGRAM RENDERER (Excalidraw MCP Server Integration)
# ═══════════════════════════════════════════════════════════════════════════

EXCALIDRAW_MCP_URL = os.environ.get(
    "EXCALIDRAW_MCP_URL", "https://excalidraw-mcp-app.vercel.app/mcp"
)


def generate_mcp_landing_zone_elements(design: dict[str, Any]) -> dict[str, Any]:
    """Build Excalidraw elements optimised for MCP ``create_view`` streaming.

    Uses **labeled shapes** (one element per node instead of three) and
    **progressive ordering** (shape → arrows from shape → next shape)
    per the MCP server's ``read_me`` best-practices.

    Adapts the landing zone design (management groups + hub-spoke) for MCP.
    """
    elems: list[dict] = []

    # ── Camera (4:3 ratio required) ──────────────────────────────────────
    # Will be set after all elements are generated

    mg = design.get("management_groups", {})
    root = mg.get("root", mg)
    arrows: list[dict] = []

    # ── Management group hierarchy (flat progressive emit) ───────────────
    def _emit_mg(node: dict, x: int, y: int, depth: int = 0, parent_id: str | None = None) -> int:
        name = node.get("name", "Unknown")
        node_id = f"mg_{name.lower().replace(' ', '_')}_{depth}"
        w = max(_MG_W, len(name) * 10 + 20)

        elems.append({
            "type": "rectangle", "id": node_id,
            "x": x, "y": y, "width": w, "height": _MG_H,
            "strokeColor": _AZURE_COLORS["management_group"]["border"],
            "backgroundColor": _AZURE_COLORS["management_group"]["bg"],
            "fillStyle": "solid", "roundness": {"type": 3},
            "label": {"text": name, "fontSize": 14},
        })

        if parent_id:
            arrows.append({
                "type": "arrow", "id": f"{parent_id}_to_{node_id}",
                "x": 0, "y": 0, "width": 1, "height": 1,
                "strokeColor": "#868e96",
                "points": [[0, 0], [0, 0]],
                "startBinding": {"elementId": parent_id},
                "endBinding": {"elementId": node_id},
                "startArrowhead": None, "endArrowhead": "arrow",
            })

        children = node.get("children", [])
        if not children:
            return x + w + 30

        child_y = y + _MG_H + 60
        child_x = x
        for child in children:
            child_x = _emit_mg(child, child_x, child_y, depth + 1, node_id)
        return child_x

    if root:
        _emit_mg(root, 0, 0)

    # ── Hub-spoke network ────────────────────────────────────────────────
    network = design.get("network_design", {})
    if network:
        net_y = 350
        hub = network.get("hub_vnet", {})
        spokes = network.get("spoke_vnets", [])
        on_prem = network.get("on_prem_connectivity", "VPN")

        hub_name = hub.get("name", "Hub VNet")
        hub_cidr = hub.get("cidr", "10.0.0.0/16")
        hub_w, hub_h = 280, 160

        elems.append({
            "type": "rectangle", "id": "hub_vnet",
            "x": 200, "y": net_y, "width": hub_w, "height": hub_h,
            "strokeColor": _AZURE_COLORS["vnet_hub"]["border"],
            "backgroundColor": _AZURE_COLORS["vnet_hub"]["bg"],
            "fillStyle": "solid", "roundness": {"type": 3},
            "label": {"text": f"{hub_name}\n{hub_cidr}", "fontSize": 14},
        })

        # Hub components
        components = hub.get("components", [])
        comp_x = 215
        for i, comp_name in enumerate(components[:3]):
            elems.append({
                "type": "rectangle", "id": f"hub_comp_{i}",
                "x": comp_x, "y": net_y + 80, "width": 120, "height": 35,
                "strokeColor": _AZURE_COLORS.get("security" if "firewall" in comp_name.lower() else "networking", _AZURE_COLORS["networking"])["border"],
                "backgroundColor": _AZURE_COLORS.get("security" if "firewall" in comp_name.lower() else "networking", _AZURE_COLORS["networking"])["bg"],
                "fillStyle": "solid", "roundness": {"type": 3},
                "label": {"text": comp_name, "fontSize": 11},
            })
            comp_x += 130

        # On-premises
        on_prem_x = 200 - 220
        on_prem_y = net_y + hub_h // 2 - 30
        elems.append({
            "type": "rectangle", "id": "on_prem",
            "x": on_prem_x, "y": on_prem_y, "width": _BOX_W, "height": _BOX_H,
            "strokeColor": _AZURE_COLORS["on_premises"]["border"],
            "backgroundColor": _AZURE_COLORS["on_premises"]["bg"],
            "fillStyle": "solid", "roundness": {"type": 3},
            "label": {"text": f"On-Premises\n{on_prem}", "fontSize": 14},
        })
        arrows.append({
            "type": "arrow", "id": "on_prem_to_hub",
            "x": 0, "y": 0, "width": 1, "height": 1,
            "strokeColor": "#868e96", "strokeStyle": "dashed",
            "points": [[0, 0], [0, 0]],
            "startBinding": {"elementId": "on_prem"},
            "endBinding": {"elementId": "hub_vnet"},
            "startArrowhead": None, "endArrowhead": "arrow",
            "label": {"text": on_prem},
        })

        # Spokes
        spoke_x = 200 + hub_w + 80
        spoke_start_y = net_y - 40
        spoke_gap = max(90, hub_h // max(len(spokes), 1))

        for i, spoke in enumerate(spokes):
            spoke_id = f"spoke_{i}"
            spoke_name = spoke.get("name", f"Spoke {i}")
            spoke_cidr = spoke.get("cidr", "")
            spoke_label = f"{spoke_name}\n{spoke_cidr}" if spoke_cidr else spoke_name
            spoke_y = spoke_start_y + i * spoke_gap

            elems.append({
                "type": "rectangle", "id": spoke_id,
                "x": spoke_x, "y": spoke_y, "width": 200, "height": 55,
                "strokeColor": _AZURE_COLORS["vnet_spoke"]["border"],
                "backgroundColor": _AZURE_COLORS["vnet_spoke"]["bg"],
                "fillStyle": "solid", "roundness": {"type": 3},
                "label": {"text": spoke_label, "fontSize": 12},
            })
            arrows.append({
                "type": "arrow", "id": f"hub_to_{spoke_id}",
                "x": 0, "y": 0, "width": 1, "height": 1,
                "strokeColor": "#495057",
                "points": [[0, 0], [0, 0]],
                "startBinding": {"elementId": "hub_vnet"},
                "endBinding": {"elementId": spoke_id},
                "startArrowhead": None, "endArrowhead": "arrow",
                "label": {"text": "peering"},
            })

    # Add arrows after all shapes (progressive ordering)
    elems.extend(arrows)

    # ── Camera ───────────────────────────────────────────────────────────
    if elems:
        all_x = [e.get("x", 0) for e in elems if "x" in e and e.get("type") != "arrow"]
        all_y = [e.get("y", 0) for e in elems if "y" in e and e.get("type") != "arrow"]
        if all_x and all_y:
            cam_x = min(all_x) - 100
            cam_y = min(all_y) - 80
            cam_w = max(all_x) + 400 - cam_x
            cam_h = max(all_y) + 300 - cam_y
            if cam_w / max(cam_h, 1) > 4 / 3:
                cam_h = int(cam_w * 3 / 4)
            else:
                cam_w = int(cam_h * 4 / 3)
            elems.insert(0, {"type": "cameraUpdate", "x": cam_x, "y": cam_y,
                             "width": cam_w, "height": cam_h})

    return {"elements_json": json.dumps(elems), "element_count": len(elems)}


# ── Async MCP client ────────────────────────────────────────────────────


async def _render_mcp_async(
    elements_json: str, mcp_url: str = EXCALIDRAW_MCP_URL,
) -> dict[str, Any]:
    """Connect to Excalidraw MCP server and invoke ``create_view``."""
    try:
        from mcp import ClientSession  # type: ignore[import-untyped]
    except ImportError:
        return {"success": False, "error": "mcp package not installed - run: pip install mcp"}

    def _extract(result: Any) -> str:
        if hasattr(result, "content"):
            parts = []
            for block in result.content:
                parts.append(getattr(block, "text", str(block)))
            return "\n".join(parts)
        return str(result)

    def _make_httpx_client(**kwargs: Any) -> Any:
        """Custom httpx client factory - disables SSL verification when the
        standard CA bundle fails (common behind corporate proxies)."""
        import httpx  # type: ignore[import-untyped]
        if os.environ.get("CAF_NO_SSL_VERIFY", "").lower() in ("1", "true"):
            kwargs["verify"] = False
            logger.debug("[MCP] SSL verify disabled via CAF_NO_SSL_VERIFY")
        elif kwargs.get("verify", True) is not False:
            try:
                with httpx.Client(verify=True) as probe:
                    probe.head(mcp_url, timeout=5)
                logger.debug("[MCP] SSL probe OK - using default verification")
            except Exception as exc:
                kwargs["verify"] = False
                logger.warning("[MCP] SSL probe failed (%s) - disabling verification. "
                               "Set CAF_NO_SSL_VERIFY=1 to suppress this warning.", exc)
        return httpx.AsyncClient(**kwargs)

    errors: list[str] = []

    # 1. Streamable HTTP (preferred)
    try:
        from mcp.client.streamable_http import streamablehttp_client
        async with streamablehttp_client(
            mcp_url, httpx_client_factory=_make_httpx_client,
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("create_view", {"elements": elements_json})
                return {"success": True, "transport": "streamable-http",
                        "result": _extract(res)}
    except Exception as exc:
        errors.append(f"streamable-http: {exc}")

    # 2. SSE fallback
    try:
        from mcp.client.sse import sse_client
        async with sse_client(mcp_url, httpx_client_factory=_make_httpx_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("create_view", {"elements": elements_json})
                return {"success": True, "transport": "sse",
                        "result": _extract(res)}
    except Exception as exc:
        errors.append(f"sse: {exc}")

    return {"success": False, "error": " | ".join(errors)}


def render_via_excalidraw_mcp(
    elements_json: str, mcp_url: str = EXCALIDRAW_MCP_URL,
) -> dict[str, Any]:
    """Render landing zone diagram via Excalidraw MCP server (**sync wrapper**).

    Handles both sync and async caller contexts gracefully.
    """
    import concurrent.futures

    coro = _render_mcp_async(elements_json, mcp_url)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=30)
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════════════════
#  6.  PNG EXPORT
# ═══════════════════════════════════════════════════════════════════════════

def export_landing_zone_png(
    design: dict[str, Any],
    filepath: str = "./output/architecture.png",
    scale: float = 2.0,
    workloads: list[dict] | None = None,
) -> str:
    """Render the landing zone diagram as a PNG using Pillow.

    Uses the same layout as the Excalidraw renderer.
    Returns absolute path to the saved PNG.
    """
    from PIL import Image, ImageDraw, ImageFont

    result = generate_landing_zone_elements(design, workloads)
    raw_elems = json.loads(result["elements_json"])
    # Filter out pseudo-elements
    elems = [e for e in raw_elems if e.get("type") not in ("cameraUpdate",)]

    if not elems:
        img = Image.new("RGB", (400, 200), "#ffffff")
        draw = ImageDraw.Draw(img)
        draw.text((20, 80), "No landing zone to render", fill="#1e1e1e")
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        img.save(filepath, "PNG")
        return os.path.abspath(filepath)

    # Canvas bounds
    all_x = [e.get("x", 0) for e in elems if "x" in e]
    all_y = [e.get("y", 0) for e in elems if "y" in e]
    all_w = [e.get("x", 0) + e.get("width", 0) for e in elems if "width" in e]
    all_h = [e.get("y", 0) + e.get("height", 0) for e in elems if "height" in e]

    pad = 80
    min_x = min(all_x) - pad
    min_y = min(all_y) - pad
    max_x = max(all_w + all_x) + pad
    max_y = max(all_h + all_y) + pad

    cw = int((max_x - min_x) * scale)
    ch = int((max_y - min_y) * scale)
    img = Image.new("RGB", (max(cw, 100), max(ch, 100)), "#ffffff")
    draw = ImageDraw.Draw(img)

    def sx(v: float) -> float:
        return (v - min_x) * scale

    def sy(v: float) -> float:
        return (v - min_y) * scale

    # Load fonts
    try:
        font = ImageFont.truetype("arial.ttf", int(14 * scale))
        font_sm = ImageFont.truetype("arial.ttf", int(11 * scale))
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", int(14 * scale))
            font_sm = ImageFont.truetype("DejaVuSans.ttf", int(11 * scale))
        except (IOError, OSError):
            font = ImageFont.load_default()
            font_sm = font

    # Draw elements
    for elem in elems:
        etype = elem.get("type", "")

        if etype == "rectangle":
            x0 = sx(elem["x"])
            y0 = sy(elem["y"])
            x1 = sx(elem["x"] + elem.get("width", _BOX_W))
            y1 = sy(elem["y"] + elem.get("height", _BOX_H))
            bg = elem.get("backgroundColor", "#e7f5ff")
            border = elem.get("strokeColor", "#1c7ed6")
            draw.rounded_rectangle([x0, y0, x1, y1], radius=8 * scale,
                                   fill=bg, outline=border, width=int(2 * scale))

        elif etype == "text":
            tx = sx(elem["x"])
            ty = sy(elem["y"])
            text = elem.get("text", "")
            color = elem.get("strokeColor", "#1e1e1e")
            f = font_sm if elem.get("fontSize", 14) < 13 else font
            draw.text((tx, ty), text, fill=color, font=f)

        elif etype == "arrow":
            points = elem.get("points", [[0, 0], [0, 0]])
            ax = sx(elem["x"])
            ay = sy(elem["y"])
            for j in range(len(points) - 1):
                px0 = ax + points[j][0] * scale
                py0 = ay + points[j][1] * scale
                px1 = ax + points[j + 1][0] * scale
                py1 = ay + points[j + 1][1] * scale
                draw.line([(px0, py0), (px1, py1)],
                          fill=elem.get("strokeColor", "#495057"),
                          width=int(2 * scale))
                # Arrowhead
                angle = math.atan2(py1 - py0, px1 - px0)
                arrow_len = 10 * scale
                draw.polygon([
                    (px1, py1),
                    (px1 - arrow_len * math.cos(angle - 0.4),
                     py1 - arrow_len * math.sin(angle - 0.4)),
                    (px1 - arrow_len * math.cos(angle + 0.4),
                     py1 - arrow_len * math.sin(angle + 0.4)),
                ], fill=elem.get("strokeColor", "#495057"))

    # Watermark
    draw.text((sx(min_x + pad), sy(max_y - pad + 40)),
              "Azure CAF Architect Companion", fill="#c0c0c0", font=font_sm)

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    img.save(filepath, "PNG")
    return os.path.abspath(filepath)


# ═══════════════════════════════════════════════════════════════════════════
#  7.  FILE SAVE HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def save_excalidraw_file(
    elements_json: str,
    filepath: str = "./output/architecture.excalidraw",
) -> str:
    """Save Excalidraw elements as a .excalidraw file."""
    pseudo = {"cameraUpdate", "delete", "restoreCheckpoint"}
    elements = json.loads(elements_json)
    real = [e for e in elements if e.get("type") not in pseudo]
    # Collect icon files referenced by image elements
    used_file_ids = {e["fileId"] for e in real if e.get("type") == "image" and "fileId" in e}
    files: dict[str, dict] = {}
    for file_id in used_file_ids:
        icon_key = file_id[len("az_icon_"):] if file_id.startswith("az_icon_") else file_id
        if icon_key in _AZ_ICON_SVGS:
            files[file_id] = {
                "mimeType": "image/svg+xml",
                "dataURL": _AZ_ICON_SVGS[icon_key],
                "id": file_id,
                "created": 1700000000000,
            }
    data = {
        "type": "excalidraw",
        "version": 2,
        "source": "caf-companion",
        "elements": real,
        "appState": {"viewBackgroundColor": "#ffffff"},
        "files": files,
    }
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return os.path.abspath(filepath)


# ═══════════════════════════════════════════════════════════════════════════
#  7a.  DIAGRAM QA AGENT (LLM-powered layout review & fix)
# ═══════════════════════════════════════════════════════════════════════════

_DIAGRAM_QA_PROMPT = """You are a diagram layout QA agent. You receive Excalidraw JSON elements
representing an Azure landing zone architecture diagram.

Your job is to review the layout and fix any issues:

1. **Overlapping text** — If a text element overflows its parent rectangle, either:
   - Shorten the text (abbreviate Azure service names, use line breaks)
   - Increase the parent rectangle's width or height
   - Adjust the text's x/y position to center it properly

2. **Overlapping elements** — If two rectangles or groups overlap, adjust positions
   to add proper spacing (minimum 20px gap between elements).

3. **Text sizing** — If text is too long for its container, abbreviate it:
   - "Azure Database for PostgreSQL - Flexible Server" → "PostgreSQL"
   - "Azure App Service" → "App Service"
   - "Azure Cache for Redis" → "Redis Cache"
   - "Azure Data Lake Storage Gen2" → "Data Lake"

4. **Container sizing** — Ensure parent rectangles (spokes, hub) are large enough
   to contain all their child elements with padding.

5. **Arrow clarity** — Ensure arrows don't cross through unrelated elements.
   Adjust start/end points if needed.

6. **Readable spacing** — Ensure at least 30px between section zones (management
   groups, network topology, identity/governance).

RULES:
- Return ONLY the corrected elements array as valid JSON (no markdown fences, no explanation)
- Keep ALL element IDs the same — only modify positions, sizes, and text content
- Do NOT add or remove elements — only fix existing ones
- Do NOT change colors, types, or structural relationships
- Preserve the cameraUpdate element (adjust if the diagram bounds changed)
- Keep the diagram compact but readable
"""


async def refine_diagram_layout(elements_json: str) -> str:
    """Send Excalidraw elements to the LLM for layout QA and fixes.

    Returns corrected elements_json string. Falls back to the original
    if the LLM call fails or returns invalid JSON.
    """
    # Strip pseudo-elements and icon metadata to reduce token count
    elements = json.loads(elements_json)
    camera = None
    compact_elems = []
    for e in elements:
        if e.get("type") == "cameraUpdate":
            camera = e
            continue
        # Strip fields the LLM doesn't need for layout analysis
        slim = {}
        for k in ("type", "id", "x", "y", "width", "height", "text",
                   "fontSize", "textAlign", "strokeColor", "backgroundColor",
                   "points", "strokeStyle", "label", "groupIds"):
            if k in e:
                slim[k] = e[k]
        compact_elems.append(slim)

    compact_json = json.dumps(compact_elems, separators=(",", ":"))
    logger.debug("[DiagramQA] Sending %d elements (%d chars) to LLM",
                 len(compact_elems), len(compact_json))

    try:
        result = await _llm_call(_DIAGRAM_QA_PROMPT, compact_json)
    except Exception as exc:
        logger.warning("[DiagramQA] LLM call failed: %s — using original", exc)
        return elements_json

    # Result should be a list of elements
    if isinstance(result, dict) and "error" in result:
        logger.warning("[DiagramQA] LLM returned error: %s", result["error"])
        return elements_json

    fixed_elems = result if isinstance(result, list) else []
    if not fixed_elems:
        logger.warning("[DiagramQA] LLM returned empty or invalid result")
        return elements_json

    # Merge LLM fixes back into original elements (preserve fields LLM didn't see)
    fixed_by_id = {e.get("id"): e for e in fixed_elems if "id" in e}
    merged = []
    if camera:
        # Check if LLM returned an updated camera
        cam_fix = fixed_by_id.pop("camera", None)
        if cam_fix and cam_fix.get("type") == "cameraUpdate":
            camera.update(cam_fix)
        merged.append(camera)

    for orig in elements:
        if orig.get("type") == "cameraUpdate":
            continue
        eid = orig.get("id")
        fix = fixed_by_id.get(eid)
        if fix:
            # Apply position/size/text fixes while keeping everything else
            for k in ("x", "y", "width", "height", "text", "fontSize",
                       "points", "label"):
                if k in fix:
                    orig[k] = fix[k]
        merged.append(orig)

    logger.debug("[DiagramQA] Merged %d fixed elements", len(merged))
    return json.dumps(merged)


# ═══════════════════════════════════════════════════════════════════════════
#  8.  REPORT BUILDER
# ═══════════════════════════════════════════════════════════════════════════

import uuid


def build_caf_report(
    caf_input: dict[str, Any],
    assessment: dict[str, Any],
    plan: dict[str, Any],
    design: dict[str, Any],
    diagram_info: dict[str, Any],
) -> dict[str, Any]:
    """Compose the final CAF report from all agent outputs."""
    workloads = plan.get("workload_inventory", [])
    costs = plan.get("cost_estimation", {})
    risks = plan.get("risk_register", [])

    # Classification breakdown
    breakdown: dict[str, int] = {}
    for w in workloads:
        c = w.get("classification", "unknown")
        breakdown[c] = breakdown.get(c, 0) + 1

    # Risk level
    risk_priorities = [r.get("priority", "low") for r in risks]
    if "critical" in risk_priorities:
        risk_level = "critical"
    elif "high" in risk_priorities:
        risk_level = "high"
    elif "medium" in risk_priorities:
        risk_level = "moderate"
    else:
        risk_level = "low"

    return {
        "executive_summary": {
            "company_name": caf_input.get("company_name", ""),
            "industry": caf_input.get("industry", ""),
            "total_workloads": len(workloads),
            "classification_breakdown": breakdown,
            "timeline_months": caf_input.get("timeline_months", 12),
            "monthly_cost": costs.get("total_monthly", 0),
            "migration_budget_estimate": costs.get("migration_budget_estimate", 0),
            "within_budget": costs.get("within_budget", True),
            "overall_readiness": assessment.get("overall_readiness", ""),
            "risk_level": risk_level,
            "total_risks": len(risks),
        },
        "assessment": assessment,
        "plan": {
            "workload_inventory": workloads,
            "migration_waves": plan.get("migration_waves", []),
        },
        "cost_estimation": costs,
        "risk_register": risks,
        "governance_recommendations": plan.get("governance_recommendations", {}),
        "landing_zone": design,
        "diagram": diagram_info,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  9.  PIPELINE ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════

async def run_full_pipeline(content: str) -> dict[str, Any]:
    """Chain Agent 1 → Agent 2 → Agent 3, returning the complete CAF report.

    This is the top-level function called by api.py, main.py, and run_local.py.
    """
    # Step 0: Parse input
    caf_input = await parse_caf_input(content)

    # Step 1: Assessment (Agent 1)
    assessment = await run_assessment(caf_input)

    # Step 2: Plan & Analyze (Agent 2)
    plan = await run_plan(caf_input, assessment)

    # Step 3: Design (Agent 3)
    design = await design_landing_zone(caf_input, plan)

    # Step 4: Generate diagram
    run_id = uuid.uuid4().hex[:8]
    workloads = plan.get("workload_inventory", [])
    lz_elements = generate_landing_zone_elements(design, workloads)

    # Step 4a: Diagram QA — LLM reviews and fixes layout issues
    lz_elements["elements_json"] = await refine_diagram_layout(
        lz_elements["elements_json"]
    )

    excalidraw_path = save_excalidraw_file(
        lz_elements["elements_json"],
        f"./output/architecture_{run_id}.excalidraw",
    )
    png_path = export_landing_zone_png(
        design,
        f"./output/architecture_{run_id}.png",
        workloads=workloads,
    )

    excalidraw_file = None
    try:
        with open(excalidraw_path, "r", encoding="utf-8") as f:
            excalidraw_file = json.load(f)
    except Exception:
        pass

    diagram_info = {
        "element_count": lz_elements["element_count"],
        "local_file": excalidraw_path,
        "png_file": png_path,
        "excalidraw_file": excalidraw_file,
        "run_id": run_id,
    }

    # Step 5: Build report
    return build_caf_report(caf_input, assessment, plan, design, diagram_info)
