"""Shared utilities for domain metadata schemas."""

from typing import Annotated

from pydantic import BeforeValidator


def normalize_str(s: str) -> str:
    return s.strip().lower()


def _normalize_str_list(v: list[str]) -> list[str]:
    """Lowercase and strip each string, dropping blanks."""
    return [normalize_str(s) for s in v if s.strip()]


NormalizedStrList = Annotated[list[str], BeforeValidator(_normalize_str_list)]
