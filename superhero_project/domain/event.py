"""Pydantic metadata schema for event articles (battles, disasters, turning points)."""

from pydantic import BaseModel
from pydantic import ConfigDict

from superhero_project.domain._utils import NormalizedStrList


class EventMetadata(BaseModel):
    """Validated shape of the JSONB metadata column for event articles."""

    model_config = ConfigDict(extra="forbid")

    event_date: str | None = None
    location: str | None = None
    participants: NormalizedStrList = []
    outcome: str | None = None
