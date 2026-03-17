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
_BOX_W, _BOX_H = 180, 60
_MG_W, _MG_H = 200, 50


def _az_rect(
    elem_id: str, label: str, color_key: str,
    x: int, y: int, w: int = _BOX_W, h: int = _BOX_H,
    dashed: bool = False,
) -> list[dict]:
    """Create an Excalidraw rectangle with a centered label."""
    col = _AZURE_COLORS.get(color_key, _AZ_DEFAULT_COL)
    rect = {
        "type": "rectangle", "id": elem_id,
        "x": x, "y": y, "width": w, "height": h,
        "strokeColor": col["border"], "backgroundColor": col["bg"],
        "fillStyle": "solid", "roundness": {"type": 3},
    }
    if dashed:
        rect["strokeStyle"] = "dashed"
    text = {
        "type": "text", "id": f"{elem_id}_lbl",
        "x": x + 8, "y": y + (h // 2) - 10,
        "width": w - 16, "height": 20,
        "text": label, "fontSize": 14,
        "textAlign": "center", "strokeColor": "#1e1e1e",
    }
    return [rect, text]


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


def _render_hub_spoke(
    network: dict, x: int, y: int,
) -> list[dict]:
    """Render hub-spoke network topology."""
    elems: list[dict] = []
    hub = network.get("hub_vnet", {})
    spokes = network.get("spoke_vnets", [])
    on_prem = network.get("on_prem_connectivity", "VPN")

    # Hub VNet — larger box
    hub_w, hub_h = 280, 160
    hub_name = hub.get("name", "Hub VNet")
    hub_cidr = hub.get("cidr", "10.0.0.0/16")
    elems.extend(_az_rect("hub_vnet", f"{hub_name}\n{hub_cidr}", "vnet_hub",
                          x, y, hub_w, hub_h, dashed=True))

    # Hub components inside
    components = hub.get("components", [])
    comp_x = x + 15
    comp_y = y + 55
    for i, comp_name in enumerate(components):
        comp_id = f"hub_comp_{i}"
        ctype = "security" if "firewall" in comp_name.lower() else "networking"
        elems.extend(_az_rect(comp_id, comp_name, ctype,
                              comp_x, comp_y, 120, 35))
        comp_x += 130

    # On-premises connection (left of hub)
    on_prem_x = x - 220
    on_prem_y = y + hub_h // 2 - 30
    elems.extend(_az_rect("on_prem", "On-Premises", "on_premises",
                          on_prem_x, on_prem_y))
    elems.extend(_az_arrow("on_prem_to_hub",
                           on_prem_x + _BOX_W, on_prem_y + _BOX_H // 2,
                           x, y + hub_h // 2,
                           on_prem, dashed=True))

    # Spoke VNets — arranged in an arc to the right
    if spokes:
        spoke_start_y = y - 40
        spoke_x = x + hub_w + 80
        spoke_gap = max(90, hub_h // max(len(spokes), 1))

        for i, spoke in enumerate(spokes):
            spoke_id = f"spoke_{i}"
            spoke_name = spoke.get("name", f"Spoke {i}")
            spoke_cidr = spoke.get("cidr", "")
            spoke_label = f"{spoke_name}\n{spoke_cidr}" if spoke_cidr else spoke_name
            spoke_y = spoke_start_y + i * spoke_gap

            elems.extend(_az_rect(spoke_id, spoke_label, "vnet_spoke",
                                  spoke_x, spoke_y, 200, 55, dashed=True))

            # Peering arrow from hub to spoke
            elems.extend(_az_arrow(
                f"hub_to_{spoke_id}",
                x + hub_w, y + hub_h // 2,
                spoke_x, spoke_y + 27,
                "peering",
            ))

    return elems


def generate_landing_zone_elements(design: dict[str, Any]) -> dict[str, Any]:
    """Build Excalidraw elements for the full landing zone architecture.

    Layout: Management groups (top) → Hub-spoke network (bottom).
    Returns {"elements_json": str, "element_count": int}.
    """
    elems: list[dict] = []

    # Zone 1: Management group hierarchy
    mg = design.get("management_groups", {})
    root = mg.get("root", mg)
    if root:
        mg_elems, _ = _render_mgmt_group_tree(root, 0, 0)
        elems.extend(mg_elems)

    # Zone 2: Hub-spoke network (below management groups)
    network = design.get("network_design", {})
    if network:
        network_y = 350  # below MG tree
        hub_spoke_elems = _render_hub_spoke(network, 200, network_y)
        elems.extend(hub_spoke_elems)

    # Camera pseudo-element for auto-zoom
    if elems:
        all_x = [e.get("x", 0) for e in elems if "x" in e]
        all_y = [e.get("y", 0) for e in elems if "y" in e]
        if all_x and all_y:
            elems.insert(0, {
                "type": "cameraUpdate",
                "x": min(all_x) - 50, "y": min(all_y) - 50,
                "width": max(all_x) - min(all_x) + 400,
                "height": max(all_y) - min(all_y) + 300,
            })

    return {"elements_json": json.dumps(elems), "element_count": len(elems)}


# ═══════════════════════════════════════════════════════════════════════════
#  6.  PNG EXPORT
# ═══════════════════════════════════════════════════════════════════════════

def export_landing_zone_png(
    design: dict[str, Any],
    filepath: str = "./output/architecture.png",
    scale: float = 2.0,
) -> str:
    """Render the landing zone diagram as a PNG using Pillow.

    Uses the same layout as the Excalidraw renderer.
    Returns absolute path to the saved PNG.
    """
    from PIL import Image, ImageDraw, ImageFont

    result = generate_landing_zone_elements(design)
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
    data = {
        "type": "excalidraw",
        "version": 2,
        "source": "caf-companion",
        "elements": real,
        "appState": {"viewBackgroundColor": "#ffffff"},
        "files": {},
    }
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return os.path.abspath(filepath)


# ═══════════════════════════════════════════════════════════════════════════
#  8.  REPORT BUILDER
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
#  9.  PIPELINE ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════
