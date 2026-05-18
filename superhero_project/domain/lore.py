"""Pydantic metadata schema for lore articles.

Covers world-building entries: power systems, history, and in-universe law.
"""

from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict

from superhero_project.domain._utils import NormalizedStrList


class LoreCategory(StrEnum):
    """Thematic category of a lore entry."""

    power_system = "power_system"
    history = "history"
    law = "law"
    geography = "geography"
    culture = "culture"
    other = "other"


class LoreMetadata(BaseModel):
    """Validated shape of the JSONB metadata column for lore articles."""

    model_config = ConfigDict(extra="forbid")

    category: LoreCategory = LoreCategory.other
    related_articles: NormalizedStrList = []
