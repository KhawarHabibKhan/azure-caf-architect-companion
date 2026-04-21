"""
CAF Companion Agents Package

Each of the 3 CAF agents is a standalone GA Agent() instance with registered
tools. The orchestrator chains them linearly.
"""

from agents.assessment_agent import create_assessment_agent
from agents.design_agent import create_design_agent
from agents.orchestrator import create_workflow, run_pipeline, stream_pipeline
from agents.plan_agent import create_plan_agent

__all__ = [
    "create_assessment_agent",
    "create_design_agent",
    "create_plan_agent",
    "create_workflow",
    "run_pipeline",
    "stream_pipeline",
]
