"""Pydantic metadata schema for disambiguation articles."""

from pydantic import BaseModel
from pydantic import ConfigDict


class DisambiguationMetadata(BaseModel):
    """Validated shape of the JSONB metadata column for disambiguation articles."""

    model_config = ConfigDict(extra="forbid")
