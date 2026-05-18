"""Pydantic metadata schema for organization articles.

Covers teams, agencies, corporations, and cults.
"""

from enum import StrEnum

from pydantic import BaseModel
from pydantic import ConfigDict

from superhero_project.domain._utils import NormalizedStrList


class OrgType(StrEnum):
    """Organizational category."""

    team = "team"
    agency = "agency"
    corporation = "corporation"
    cult = "cult"
    publisher = "publisher"
    other = "other"


class OrgStatus(StrEnum):
    """Operational status of an organization."""

    active = "active"
    disbanded = "disbanded"
    defunct = "defunct"
    unknown = "unknown"


class OrgMetadata(BaseModel):
    """Validated shape of the JSONB metadata column for organization articles."""

    model_config = ConfigDict(extra="forbid")

    aliases: NormalizedStrList = []
    org_type: OrgType = OrgType.other
    founded: str | None = None
    headquarters: str | None = None
    status: OrgStatus = OrgStatus.unknown
    affiliation: NormalizedStrList = []
