import pytest

from django.test import override_settings

from wagtail_pdf_converter.services.converter import HybridPDFConverter


class TestLinkFixing:
    @pytest.fixture
    @override_settings(
        WAGTAIL_PDF_CONVERTER={
            "AI_BACKENDS": {
                "default": {
                    "CLASS": "wagtail_pdf_converter.services.backends.gemini.GeminiBackend",
                    "CONFIG": {"API_KEY": "test-key"},
                }
            }
        }
    )
    def converter(self):
        return HybridPDFConverter()

    def test_fix_hallucinated_links_text_equals_url(self, converter):
        """Test removing links where the URL is identical to the text."""
        content = "This is a [Title](Title) link."
        expected = "This is a Title link."
        assert converter._fix_hallucinated_links(content) == expected

    def test_fix_hallucinated_links_url_in_text(self, converter):
        """Test removing links where the URL is a substring of the text."""
        content = "See [Guidance on Audit](Guidance) for details."
        expected = "See Guidance on Audit for details."
        assert converter._fix_hallucinated_links(content) == expected

    def test_fix_hallucinated_links_encoded_url(self, converter):
        """Test removing links where the URL is an encoded version of the text."""
        content = "Read [The Report](The%20Report) now."
        expected = "Read The Report now."
        assert converter._fix_hallucinated_links(content) == expected

    def test_fix_hallucinated_links_valid_http(self, converter):
        """Test preserving valid HTTP links."""
        content = "Visit [Google](https://google.com)."
        expected = "Visit [Google](https://google.com)."
        assert converter._fix_hallucinated_links(content) == expected

    def test_fix_hallucinated_links_valid_relative(self, converter):
        """Test preserving valid relative links (anchors)."""
        content = "See [Section 1](#section-1)."
        expected = "See [Section 1](#section-1)."
        assert converter._fix_hallucinated_links(content) == expected

    def test_fix_hallucinated_links_valid_path(self, converter):
        """Test preserving valid absolute path links."""
        content = "Go to [Home](/)."
        expected = "Go to [Home](/)."
        assert converter._fix_hallucinated_links(content) == expected

    def test_fix_hallucinated_links_mixed(self, converter):
        """Test mixed content with both valid and invalid links."""
        content = "Good: [Link](https://example.com). Bad: [Bad](Bad)."
        expected = "Good: [Link](https://example.com). Bad: Bad."
        assert converter._fix_hallucinated_links(content) == expected

    def test_fix_hallucinated_links_url_encoded_text(self, converter):
        """Test content with URL-encoded text that's not a valid link."""
        content = (
            "The [Guidance on the Going Concern Basis of Accounting and Reporting on "
            "Solvency and Liquidity Risks](Guidance%20on%20the%20Going%20Concern%20"
            "Basis%20of%20Accounting%20and%20Reporting%20on%20Solvency%20and%20"
            "Liquidity%20Risks), issued in 2016"
        )
        expected = (
            "The Guidance on the Going Concern Basis of Accounting and Reporting on "
            "Solvency and Liquidity Risks, issued in 2016"
        )
        assert converter._fix_hallucinated_links(content) == expected

    def test_fix_hallucinated_links_mailto(self, converter):
        """Test preserving mailto links."""
        content = "Contact [Support](mailto:support@example.com)."
        expected = "Contact [Support](mailto:support@example.com)."
        assert converter._fix_hallucinated_links(content) == expected
