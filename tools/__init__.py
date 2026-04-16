"""
CAF Companion Tools Package
Re-exports for backwards compatibility.
"""

from tools.common import _llm_call, _normalize_input, _load_knowledge
from tools.assessment import (
    parse_caf_input,
    assess_readiness,
    recommend_operating_model,
    assess_skills,
    run_assessment,
)
from tools.planning import (
    classify_workloads,
    plan_migration_waves,
    estimate_costs,
    assess_risks,
    recommend_governance,
    run_plan,
)
