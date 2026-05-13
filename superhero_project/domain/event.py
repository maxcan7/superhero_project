from pydantic import BaseModel
from pydantic import ConfigDict


class EventMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_date: str | None = None
    location: str | None = None
    participants: list[str] = []
    outcome: str | None = None
