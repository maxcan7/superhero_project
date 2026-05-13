from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict


class OrgType(StrEnum):
    team = "team"
    agency = "agency"
    corporation = "corporation"
    cult = "cult"
    other = "other"


class OrgStatus(StrEnum):
    active = "active"
    disbanded = "disbanded"
    defunct = "defunct"
    unknown = "unknown"


class OrgMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aliases: list[str] = []
    org_type: OrgType = OrgType.other
    founded: str | None = None
    headquarters: str | None = None
    status: OrgStatus = OrgStatus.unknown
    affiliation: list[str] = []
