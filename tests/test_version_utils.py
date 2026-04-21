import pytest

from wagtail_pdf_converter import _get_version_tuple


@pytest.mark.parametrize(
    "version_string, expected",
    [
        # Standard semver
        ("1.2.3", (1, 2, 3)),
        ("0.1.0", (0, 1, 0)),
        # With pre-release identifiers (should be ignored)
        ("1.2.3-alpha", (1, 2, 3)),
        ("0.2.1-rc1", (0, 2, 1)),
        # PEP 440 style
        ("1.2.3a0", (1, 2, 3)),
        ("1.2.3b1", (1, 2, 3)),
        ("1.2.3rc1", (1, 2, 3)),
        ("1.2.3.post1", (1, 2, 3)),
        ("1.2.3.dev1", (1, 2, 3)),
        # Fallback for simpler versions
        ("1.2", (1, 2)),
        ("1", (1,)),
        # With non-digit parts that should be ignored by fallback
        ("1.2.beta", (1, 2)),
        # Empty string
        ("", ()),
        # Non-standard versions
        ("v1.2.3", (1, 2, 3)),
    ],
)
def test_get_version_tuple(version_string, expected):
    """Test that _get_version_tuple correctly parses various version strings."""
    assert _get_version_tuple(version_string) == expected
