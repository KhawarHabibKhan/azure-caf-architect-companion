"""
CAF Companion - Assessment Tools (Agent 1)
Input parsing, readiness scoring, operating model, skills gap analysis.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from tools.common import _llm_call, _normalize_input

logger = logging.getLogger("caf-companion")


# ---------------------------------------------------------------------------
#  Input Parser
# ---------------------------------------------------------------------------

async def parse_caf_input(content: str) -> dict[str, Any]:
    """Extract structured CAF input from free-text using LLM.

    Takes any description of an organization's IT environment and returns
    a normalized dict matching the CAFInput schema.
    """
    from knowledge.caf_prompts import PARSE_INPUT_PROMPT

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


# ---------------------------------------------------------------------------
#  Readiness Assessment
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
#  Operating Model
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
#  Skills Gap Analysis
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
#  Agent 1 Orchestrator
# ---------------------------------------------------------------------------

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
