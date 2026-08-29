"""Local evaluator entry point; kept identical to the submission shim."""

from src.agent import Agent
from src.parsing import OVERRIDE_MARKER
from src.policy import CLARIFICATION_SEQUENCE

CLARIFICATION_CYCLE = CLARIFICATION_SEQUENCE

__all__ = ["Agent", "CLARIFICATION_CYCLE", "CLARIFICATION_SEQUENCE", "OVERRIDE_MARKER"]
