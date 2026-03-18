"""Phoebe — Multimodal Knowledge Engine.

Stores memories of where she saw things and what they meant.
Never stores originals. References + extractions + graph structure.
Answers WHY, not just WHAT.
"""

__version__ = "0.1.0"

from phoebe.tome import Tome
from phoebe.store import GraphStore
from phoebe.reasoning import Reasoner

__all__ = ["Tome", "GraphStore", "Reasoner"]
