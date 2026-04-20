"""
CAF Companion Agents Package

Each of the 3 CAF agents is a standalone GA Agent() instance with registered
tools. The orchestrator chains them linearly.
"""

from agents.assessment_agent import create_assessment_agent

__all__ = ["create_assessment_agent"]
