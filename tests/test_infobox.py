"""Tests for infobox display logic."""

import pytest

from superhero_project.db.models import ArticleType
from superhero_project.domain.infobox import ResolvedLink
from superhero_project.domain.infobox import UnresolvedLink
from superhero_project.domain.infobox import build_infobox_links
from tests.utils import GOTHAM_EDGE
from tests.utils import WIKILINK_EDGE

_AVENGERS_EDGE = {
    "slug": "avengers",
    "article_type": "org",
    "field_name": "affiliation",
    "resolved_via": "avengers",
}


@pytest.mark.parametrize(
    ("article_type", "outgoing", "metadata", "expected"),
    [
        pytest.param(
            ArticleType.disambiguation,
            [],
            {},
            {},
            id="no-handler-returns-empty",
        ),
        pytest.param(
            ArticleType.profile,
            [_AVENGERS_EDGE],
            {"affiliation": ["avengers"]},
            {
                "affiliation": [
                    ResolvedLink(resolved=True, slug="avengers", article_type="org")
                ]
            },
            id="resolved-list-field",
        ),
        pytest.param(
            ArticleType.profile,
            [],
            {"affiliation": ["Unknown Org"]},
            {"affiliation": [UnresolvedLink(resolved=False, label="Unknown Org")]},
            id="unresolved-list-field",
        ),
        pytest.param(
            ArticleType.profile,
            [_AVENGERS_EDGE],
            {"affiliation": ["avengers", "Unknown Org"]},
            {
                "affiliation": [
                    ResolvedLink(resolved=True, slug="avengers", article_type="org"),
                    UnresolvedLink(resolved=False, label="Unknown Org"),
                ]
            },
            id="mixed-resolved-and-unresolved",
        ),
        pytest.param(
            ArticleType.profile,
            [GOTHAM_EDGE],
            {"base_of_operations": "gotham"},
            {
                "base_of_operations": [
                    ResolvedLink(resolved=True, slug="gotham", article_type="location")
                ]
            },
            id="resolved-single-field",
        ),
        pytest.param(
            ArticleType.profile,
            [],
            {"base_of_operations": "unknown city"},
            {
                "base_of_operations": [
                    UnresolvedLink(resolved=False, label="unknown city")
                ]
            },
            id="unresolved-single-field",
        ),
        pytest.param(
            ArticleType.profile,
            [],
            {"affiliation": []},
            {},
            id="empty-metadata-field-omitted",
        ),
        pytest.param(
            ArticleType.profile,
            [WIKILINK_EDGE],
            {"base_of_operations": "gotham"},
            {"base_of_operations": [UnresolvedLink(resolved=False, label="gotham")]},
            id="wikilink-edges-ignored",
        ),
    ],
)
def test_build_infobox_links(
    article_type: ArticleType,
    outgoing: list[dict],
    metadata: dict,
    expected: dict,
) -> None:
    """build_infobox_links maps outgoing edges and metadata to typed link items."""
    assert build_infobox_links(outgoing, article_type, metadata) == expected
