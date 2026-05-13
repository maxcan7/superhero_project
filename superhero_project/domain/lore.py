from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict


class LoreCategory(StrEnum):
    power_system = "power_system"
    history = "history"
    law = "law"
    geography = "geography"
    culture = "culture"
    other = "other"


class LoreMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: LoreCategory = LoreCategory.other
    related_articles: list[str] = []
