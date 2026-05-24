"""Infobox display logic: format link-graph edge data for template rendering."""

from typing import Literal
from typing import TypedDict

from superhero_project.db.models import ArticleType
from superhero_project.domain._utils import normalize_str
from superhero_project.domain.links import _HANDLERS


class ResolvedLink(TypedDict):
    """Infobox link item that resolved to a published article."""

    resolved: Literal[True]
    page_name: str
    article_type: str


class UnresolvedLink(TypedDict):
    """Infobox link item that did not resolve at save time."""

    resolved: Literal[False]
    label: str


InboxLinkItem = ResolvedLink | UnresolvedLink


def _field_edge_map(
    outgoing: list[dict[str, str | None]],
) -> dict[str, dict[str, ResolvedLink]]:
    """Index metadata edges by field_name → resolved_via → ResolvedLink."""
    result: dict[str, dict[str, ResolvedLink]] = {}
    for edge in outgoing:
        fn = edge.get("field_name")
        rv = edge.get("resolved_via")
        page_name = edge.get("page_name")
        article_type = edge.get("article_type")
        if fn is None or rv is None or page_name is None or article_type is None:
            continue
        result.setdefault(fn, {})[rv] = ResolvedLink(
            resolved=True, page_name=page_name, article_type=article_type
        )
    return result


def _resolve_field_values(
    values: list[str],
    resolved_map: dict[str, ResolvedLink],
) -> list[InboxLinkItem]:
    """Map metadata strings to resolved links or unresolved plain-text fallbacks."""
    items: list[InboxLinkItem] = []
    for v in values:
        normalized = normalize_str(v)
        if normalized in resolved_map:
            items.append(resolved_map[normalized])
        else:
            items.append(UnresolvedLink(resolved=False, label=v))
    return items


def build_infobox_links(
    outgoing: list[dict[str, str | None]],
    article_type: ArticleType,
    metadata: dict[str, str | list[str] | None],
) -> dict[str, list[InboxLinkItem]]:
    """Pre-compute linked-field items for infobox rendering.

    Returns field_name → list of resolved links or unresolved plain-text fallbacks.
    """
    handler = _HANDLERS.get(article_type)
    if handler is None:
        return {}

    edge_map = _field_edge_map(outgoing)
    result: dict[str, list[InboxLinkItem]] = {}
    for edge_field_name, meta_key, _is_list in handler.edge_fields:
        value = metadata.get(meta_key)
        if not value:
            continue
        values: list[str] = value if isinstance(value, list) else [value]
        result[edge_field_name] = _resolve_field_values(
            values, edge_map.get(edge_field_name, {})
        )
    return result
