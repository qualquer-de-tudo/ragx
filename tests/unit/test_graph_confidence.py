from __future__ import annotations

import pytest

from ragx.graph.store import confidence_tier

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "confidence,expected",
    [
        (1.0, "extracted"),
        (0.95, "extracted"),
        (0.94, "inferred"),
        (0.75, "inferred"),
        (0.6, "inferred"),
        (0.0, "inferred"),
    ],
)
def test_confidence_tier_boundary(confidence: float, expected: str) -> None:
    assert confidence_tier(confidence) == expected
