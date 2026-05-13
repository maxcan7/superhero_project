from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict


class TechType(StrEnum):
    gear = "gear"
    serum = "serum"
    relic = "relic"
    weapon = "weapon"
    vehicle = "vehicle"
    other = "other"


class TechStatus(StrEnum):
    active = "active"
    destroyed = "destroyed"
    lost = "lost"
    unknown = "unknown"


class TechMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tech_type: TechType = TechType.other
    origin: str | None = None
    current_holder: str | None = None
    status: TechStatus = TechStatus.unknown
