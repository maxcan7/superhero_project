"""Pydantic metadata schema for technology/artifact articles (gear, serums, relics)."""

from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict


class TechType(StrEnum):
    """Category of technology or artifact."""

    gear = "gear"
    serum = "serum"
    relic = "relic"
    weapon = "weapon"
    vehicle = "vehicle"
    other = "other"


class TechStatus(StrEnum):
    """Current status of a technology or artifact."""

    active = "active"
    destroyed = "destroyed"
    lost = "lost"
    unknown = "unknown"


class TechMetadata(BaseModel):
    """Validated shape of the JSONB metadata column for technology/artifact articles."""

    model_config = ConfigDict(extra="forbid")

    tech_type: TechType = TechType.other
    origin: str | None = None
    current_holder: str | None = None
    status: TechStatus = TechStatus.unknown
