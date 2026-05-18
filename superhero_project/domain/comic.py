"""Pydantic metadata schema for comic article types."""

from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict

from superhero_project.domain._utils import NormalizedStrList


class ComicType(StrEnum):
    """Format of the comic series or property."""

    series = "series"
    miniseries = "miniseries"
    one_shot = "one_shot"
    anthology = "anthology"
    other = "other"


class ComicStatus(StrEnum):
    """Publication status of the comic series."""

    ongoing = "ongoing"
    completed = "completed"
    cancelled = "cancelled"
    unknown = "unknown"


class ComicMetadata(BaseModel):
    """Validated shape of the JSONB metadata column for comic articles."""

    model_config = ConfigDict(extra="forbid")

    comic_type: ComicType = ComicType.series
    publishers: NormalizedStrList = []
    first_issue: str | None = None
    last_issue: str | None = None
    status: ComicStatus = ComicStatus.unknown
