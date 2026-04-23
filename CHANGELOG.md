# Changelog

All notable changes to this project will be documented here.

## Unreleased

## [0.1.0rc1](https://github.com/torchbox/wagtail-pdf-converter/releases/tag/v0.1.0rc1) - 2026-04-23

### Features

#### Core Conversion Engine

- `HybridPDFConverter` for PDF-to-Markdown conversion using [PyMuPDF](https://github.com/pymupdf/pymupdf) and AI backends.
- Automatic PDF splitting for large documents (50-page chunks with overlap).
- Image extraction and processing, including support for masks and split images.
- Hallucinated link detection and repair to ensure content integrity.

#### AI Integration

- Pluggable backend system (Google Gemini via [`google-genai`](https://github.com/googleapis/python-genai) implemented as default).
- Context-aware page processing for better continuity across chunks.
- Automated image description generation for accessibility.

#### Wagtail Integration

- `PDFConversionMixin` for easy integration with existing Wagtail Document model.
- `DocumentConversion` model for efficient storage of heavy Markdown payloads.
- Integrated admin UI for monitoring conversion status and editing converted content.
- Support for background processing via [`django-tasks`](https://github.com/RealOrangeOne/django-tasks).

#### Markdown & A11y

- Custom `HeadingAnchorExtension` for accessible, linkable headings.
- Semantic HTML rendering from converted Markdown.

#### DX

- Optional Docker support for quick-start Postgres development.
- Extensive docs for configuration and customization.
- Comprehensive test suite ([pytest](https://docs.pytest.org/en/stable/)) with >90% coverage.
