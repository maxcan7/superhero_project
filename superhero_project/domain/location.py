from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict


class LocationType(StrEnum):
    city = "city"
    base = "base"
    zone = "zone"
    dimension = "dimension"
    other = "other"


class LocationStatus(StrEnum):
    active = "active"
    destroyed = "destroyed"
    abandoned = "abandoned"
    unknown = "unknown"


class LocationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_type: LocationType = LocationType.other
    region: str | None = None
    status: LocationStatus = LocationStatus.unknown
    notable_residents: list[str] = []
