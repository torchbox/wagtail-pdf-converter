---
icon: lucide/file-text
---

# wagtail-pdf-converter

`wagtail-pdf-converter` converts PDF documents to accessible HTML using AI. Upload a PDF via the Wagtail admin and the package produces a Markdown representation rendered as semantic HTML — an accessible alternative to sending users a binary file to download.

## When to use it

- You need to meet accessibility requirements (WCAG, public sector body regulations) for documents on your site
- You want PDF content to be readable and indexable, not just downloadable
- You're using Wagtail's document management and want conversion to run automatically on upload
- You want the flexibility to use different AI models (Google Gemini, OpenAI, etc.) via a pluggable backend architecture.

## Requirements

| Requirement      | Versions                       |
| ---------------- | ------------------------------ |
| Python           | 3.10 – 3.14                    |
| Django           | 4.2, 5.1, 5.2, 6.0             |
| Wagtail          | 6.3, 7.0, 7.1, 7.2             |
| AI Model Backend | Required (e.g., Google Gemini) |

[Get started →](getting-started.md)
