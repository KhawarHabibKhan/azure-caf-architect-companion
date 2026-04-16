"""
CAF Companion - Planning Tools (Agent 2)
Workload classification, migration waves, cost estimation, risk assessment, governance.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from tools.common import _llm_call, _load_knowledge

logger = logging.getLogger("caf-companion")


# ---------------------------------------------------------------------------
#  Workload Classification (7 R's)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
#  Migration Wave Planning
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
#  Cost Estimation
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
#  Risk Assessment
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
#  Governance Recommendations
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
#  Agent 2 Orchestrator
# ---------------------------------------------------------------------------

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
