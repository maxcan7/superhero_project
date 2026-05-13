"""Pydantic metadata schema for location articles (cities, bases, anomalous zones)."""

from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict


class LocationType(StrEnum):
    """Category of location."""

    city = "city"
    base = "base"
    zone = "zone"
    dimension = "dimension"
    other = "other"


class LocationStatus(StrEnum):
    """Current status of a location."""

    active = "active"
    destroyed = "destroyed"
    abandoned = "abandoned"
    unknown = "unknown"


class LocationMetadata(BaseModel):
    """Validated shape of the JSONB metadata column for location articles."""

    model_config = ConfigDict(extra="forbid")

    location_type: LocationType = LocationType.other
    region: str | None = None
    status: LocationStatus = LocationStatus.unknown
    notable_residents: list[str] = []
