from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict


class ProfileStatus(StrEnum):
    active = "active"
    retired = "retired"
    deceased = "deceased"
    unknown = "unknown"


class ProfileMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aliases: list[str] = []
    affiliation: list[str] = []
    powers: list[str] = []
    status: ProfileStatus = ProfileStatus.unknown
    base_of_operations: str | None = None
    first_appearance: str | None = None
