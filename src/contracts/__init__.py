"""Frozen data contracts shared by ShopLens modules."""

from .config import CONFIGS, RunConfig, get_run_config
from .parsing import ParsedTurn
from .response import AgentReply, AskAttribute, Recommendation, Usage
from .retrieval import Candidate, RetrievalQuery, Retriever
from .state import SessionState, Slot, UserProfile

__all__ = [
    "AgentReply", "AskAttribute", "Candidate", "CONFIGS", "ParsedTurn",
    "Recommendation", "RetrievalQuery", "Retriever", "RunConfig",
    "SessionState", "Slot", "Usage", "UserProfile", "get_run_config",
]
