"""Pydantic metadata schema for profile articles.

Covers heroes, villains, and other notable individuals.
"""

from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict


class ProfileStatus(StrEnum):
    """Activity status of a profile subject."""

    active = "active"
    retired = "retired"
    deceased = "deceased"
    unknown = "unknown"


class ProfileMetadata(BaseModel):
    """Validated shape of the JSONB metadata column for profile articles."""

    model_config = ConfigDict(extra="forbid")

    aliases: list[str] = []
    affiliation: list[str] = []
    powers: list[str] = []
    status: ProfileStatus = ProfileStatus.unknown
    base_of_operations: str | None = None
    first_appearance: str | None = None
