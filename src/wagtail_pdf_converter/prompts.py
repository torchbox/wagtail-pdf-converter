# Note: This prompt template requires 'intro', 'pronoun', and 'output_instructions'
# variables to be formatted into it.
DEFAULT_IMAGE_DESCRIPTION_PROMPT_TEMPLATE: str = """{intro} from a PDF document and classify {pronoun} as either 'MEANINGFUL' or 'DECORATIVE'.

**MEANINGFUL images** are essential for understanding content and include:
- Charts, graphs, and data visualizations of any kind
- Organizational charts and process diagrams
- Screenshots and technical drawings
- Maps, floor plans, and architectural drawings
- Product photos and equipment images
- Infographics and educational diagrams
- Any image that conveys specific information or data
- Complex tables that are better viewed as images
- Visual frameworks and conceptual models
- Network diagrams and system architectures

**DECORATIVE images** are for visual appeal and include:
- Generic stock photos used purely for visual appeal
- Abstract background patterns or textures
- Purely decorative borders or dividers
- Company logos used only for branding (without informational context)
- Images that represent icons, including social media icons and any kind of iconography
- Any image that is part of a cover page design (e.g., title pages, back covers)

**Guiding Rule:** When in doubt, choose MEANINGFUL. It's better to include a useful image than to exclude one that conveys important information.

**Instructions:**
{output_instructions}

**Examples:**
- 'MEANINGFUL: Pie chart showing portfolio allocation across different asset classes'
- 'MEANINGFUL: Organizational chart displaying European management structure'
- 'MEANINGFUL: Process flow diagram illustrating ESG integration steps'
- 'DECORATIVE'
"""

DEFAULT_SINGLE_IMAGE_OUTPUT_INSTRUCTIONS: str = """1. If the image is MEANINGFUL, provide a clear, descriptive alt text prefixed with 'MEANINGFUL:'.
2. If the image is DECORATIVE, respond with only the word 'DECORATIVE'.
3. Keep the alt text description under 250 characters."""

DEFAULT_BATCH_IMAGE_OUTPUT_INSTRUCTIONS: str = """1. For each MEANINGFUL image, provide a clear, concise description suitable for web accessibility (alt text), starting with 'MEANINGFUL:'.
2. For each DECORATIVE image, just respond with 'DECORATIVE'.
3. Keep each description under 250 characters.
4. Return the results for all images in the same order they were provided, separated by '---SEPARATOR---'."""

DEFAULT_IMAGE_SINGLE_DESCRIPTION_PROMPT: str = DEFAULT_IMAGE_DESCRIPTION_PROMPT_TEMPLATE.format(
    intro="Analyze this image",
    pronoun="it",
    output_instructions=DEFAULT_SINGLE_IMAGE_OUTPUT_INSTRUCTIONS,
)

DEFAULT_IMAGE_BATCH_DESCRIPTION_PROMPT: str = DEFAULT_IMAGE_DESCRIPTION_PROMPT_TEMPLATE.format(
    intro="Analyze these images",
    pronoun="each one",
    output_instructions=DEFAULT_BATCH_IMAGE_OUTPUT_INSTRUCTIONS,
)

# Note: This prompt template requires an `image_report` variable to be formatted into it.
DEFAULT_PDF_CONVERSION_PROMPT_TEMPLATE: str = """Convert this PDF document to clean, semantic markdown optimized for web accessibility.

**Examples of Good Conversions:**

**Example 1 - Handling Cover Page and Table of Contents:**

INPUT (PDF pages):
```
Page 1 (Cover):
═══════════════════════════
    Annual Report 2024
    Organization Name
    March 2024
═══════════════════════════

Page 2 (Contents):
Contents
─────────────────────
Strategic Report ......... 3
Governance ............... 12
Financial Statements ..... 18

Page 3 (Content starts):
Strategic Report
Our performance this year...
```

OUTPUT (Markdown):
```
[TOC]

## Strategic Report

Our performance this year...
```

**Example 2 - Document Without Table of Contents:**

INPUT (PDF pages):
```
Page 1 (Cover):
═══════════════════════════
    Technical Standard
═══════════════════════════

Page 2 (Content starts):
Introduction
This standard covers...
```

OUTPUT (Markdown):
```
## Introduction

This standard covers...
```

**Example 3 - Good Heading Hierarchy:**
```
## Strategic Report                         (Major section - H2)

### 1. Performance Overview                 (Subsection - H3)

Key achievements and financial highlights...  (Body text)

### 2. Stakeholder Engagement               (Subsection - H3)

Our approach to engagement...               (Body text)

## Governance                               (Major section - H2)

### Board Structure                         (Subsection - H3)
```

**Example 4 - Complex Nested Hierarchy (CORRECT):**
```
## 3. Financial Performance {{: #section-3 }}

### Revenue Analysis

Detailed revenue breakdown...

#### Regional Performance

Performance by region...

### Cost Management

Our approach to costs...

#### Operating Expenses

Details of operating costs...

## 4. Risk Management {{: #section-4 }}

### Assessment Process

How we assess risks...
```

**Example 5 - ANTI-PATTERN (WRONG - Don't Do This):**
```
## 3. Financial Performance {{: #section-3 }}

### Revenue Analysis

Detailed revenue breakdown...

#### Regional Performance

Performance by region...

## Cost Management                          WRONG - should be ### not ##
                                            (This breaks the hierarchy of Section 3)

### Operating Expenses

Details of operating costs...
```

**Example 6 - Numbered Sections with Custom IDs:**
```
## 1. Executive Summary {{: #section-1 }}

This report covers our performance...

## 2. Strategic Objectives {{: #section-2 }}

### 2.1 Financial Performance {{: #section-2-1 }}

Our financial results show...

## Governance

Our board structure and processes...
```
(Note: Use `{{: #id }}` syntax for numbered sections only. Regular headings like "Governance" get auto-generated IDs.)

**Example 7 - Alphabetical Lists:**
```
## Requirements

The following conditions must be met:

<ol type="a" markdown="1">
<li>The entity must be registered in the UK or ROI</li>
<li>Annual revenue must exceed £10 million</li>
<li>The auditor must be ~~struck through~~ independent</li>
</ol>

For uppercase alphabetical lists:

<ol type="A" markdown="1">
<li>First criterion</li>
<li>Second criterion with **bold** text</li>
<li>Third criterion</li>
</ol>
```
(Note: Use HTML `<ol type="a" markdown="1">` for lowercase or `<ol type="A" markdown="1">` for uppercase alphabetical lists. Always include `markdown="1"` to ensure markdown formatting inside list items is parsed.)

**Example 8 - Hyperlink Handling (CRITICAL):**

**CORRECT - Explicit Link:**
Text in PDF: "Visit our website at www.example.com"
Markdown: `Visit our website at [www.example.com](https://www.example.com)`

**CORRECT - Clickable Text:**
Text in PDF: "Read the full report" (hyperlinked to https://example.com/report)
Markdown: `[Read the full report](https://example.com/report)`

**CORRECT - No Link:**
Text in PDF: "Guidance on Audit Matters" (bold text, no hyperlink)
Markdown: `**Guidance on Audit Matters**`

**WRONG - Hallucinated Link (Don't do this):**
Text in PDF: "Guidance on Audit Matters" (no hyperlink)
Markdown: `[Guidance on Audit Matters](https://www.example.com/guidance-on-audit-matters)` -> WRONG! Don't guess URLs.
Markdown: `[Guidance on Audit Matters](Guidance%20on%20Audit%20Matters)` -> WRONG! Don't make the text the URL.

**Requirements:**

1. **Table of Contents Handling:**
- **Begin with first substantive content:** Start your markdown output with the first real content section, omitting cover pages, title pages, and decorative elements
- **When PDF has a Table of Contents page:** Insert the placeholder `[TOC]` on a new line where the original Contents page was located
  * The Contents heading and its list items become: `[TOC]`
  * This single marker will be replaced with an auto-generated, linked table of contents
  * Document flow: cover pages (omitted) → `[TOC]` marker → main content
- **When PDF has no Table of Contents:** Begin directly with the first content section - do not insert `[TOC]`

2. **Document Structure:**
- **Use proper markdown heading levels (# ## ###) to preserve document hierarchy**
  * **H1 (#):** Never use - reserved for page title
  * **H2 (##):** ONLY for major top-level sections (e.g., "1. Introduction", "2. Methodology", "Appendices")
  * **H3 (###):** For subsections under H2 (e.g., "Background", "Purpose", "Assessment Process")
  * **H4 (####):** For sub-subsections under H3
  * **CRITICAL:** Once you open a numbered section (e.g., "## 3. Risk Assessment"), ALL subsections within that section MUST use H3 or deeper - NEVER promote them back to H2 until you reach the next numbered section (e.g., "## 4. Next Section")
  * **Heading hierarchy must be continuous** - don't skip levels (e.g., don't go from H2 to H4 without an H3)
- Remove any running headers, footers, and page numbers
- Include ALL substantive content including legal disclaimers, copyright notices, and appendices
- Skip only purely decorative elements (page borders, background graphics, etc.)
- Use semantic structure rather than visual formatting
- Add blank lines before headings for readability
- **For lists:**
  * Each list item MUST start on a new line
  * Use `-` for unordered lists, numbers for ordered lists (e.g., `1.`, `2.`, `3.`)
  * Maintain proper indentation for nested lists
  * If a list continues from a previous page/chunk, continue the numbering sequence
  * Ensure there are blank lines before and after lists for proper rendering
  * **For alphabetical lists (a., b., c. or A., B., C.):** Use HTML ordered lists with `type` and `markdown="1"` attributes:
    - Lowercase: `<ol type="a" markdown="1"><li>First item</li><li>Second item</li></ol>`
    - Uppercase: `<ol type="A" markdown="1"><li>First item</li><li>Second item</li></ol>`
    - **CRITICAL: Always include `markdown="1"`** to ensure markdown formatting inside list items (bold, italic, strikethrough, links, etc.) is properly parsed
- **For tables:**
  * **CRITICAL: Wrap all tables in a container div for horizontal scrolling:** `<div class="table-container">` before the table and `</div>` after
  * Each table row MUST be on its own line
  * Use `|` delimiters with proper spacing: `| Column 1 | Column 2 |`
  * Include header separator row: `|----------|----------|`
  * For tables, you MUST include a header row. If the original document provides no headers, create a header row with blank cells.
  * Do not merge rows or cells
  * If a table continues from a previous page/chunk, do not repeat the header
  * Ensure proper alignment using colons in separator row if needed
  * Example structure:
    ```
    <div class="table-container">

    | Header 1 | Header 2 |
    |----------|----------|
    | Data 1   | Data 2   |

    </div>
    ```
- **Heading Cleanup and Hierarchy Verification:**
  * Delete any titles or headings that contain "(continued)"
  * If a heading is exactly "ACME Corporation", convert it to a bold paragraph (`**ACME Corporation**`) instead of a heading.
  * Delete any heading that is identical to the immediately preceding heading at the same level.
  * **Before creating an H2 heading, verify:** Is this truly a major top-level section, or is it a subsection of the current numbered section? If it's a subsection (like "Assessment Period", "Reporting Requirements", "Summary of Requirements" within a numbered section), use H3 (###) instead.
  * **Watch for PDF layout tricks:** Sometimes PDFs make subsection titles look prominent (bold, larger font), but they're still subsections. Look at the numbering and logical flow, not just visual appearance.
- **Extraneous Elements:**
  * Remove any purely decorative horizontal lines (e.g., `---`, `***`).

3. **Content Preservation:**
- Include legal disclaimers, copyright notices, and important notices
- Preserve all tables, even if they contain legal or administrative information
- Maintain all substantive text regardless of whether it appears "administrative"
- Only skip content that is purely decorative or redundant page elements

4. **Content Formatting:**
- **Emphasis:** Preserve bold and italic text using markdown syntax (`**bold**`, `*italic*`)
- **Footnotes:** Convert to markdown format using [^1] syntax, with footnotes collected at end of document
- **Hyperlinks:**
  * Convert ALL hyperlinks to markdown format `[text](url)`.
  * **CRITICAL:** Only include URLs that are explicitly present in the PDF (either visible in text or as a clickable link).
  * **NEVER invent URLs.** If text looks like a title but has no link in the PDF, leave it as plain text.
  * **NEVER create links where the URL is just the text itself.** (e.g., `[Title](Title)` is WRONG).
  * **NEVER guess URLs** based on the text content.
- **Amendment Documents (e.g. FRED, draft standards):** Preserve editing marks:
  * Strikethrough text → `~~deleted text~~`
  * Underlined insertions → `<ins>inserted text</ins>`
  * (Regular underline for emphasis uses standard markdown)
- **HTML Elements with Markdown Content:** When using HTML block-level elements that contain markdown-formatted content (bold, italic, lists, etc.), always add `markdown="1"` attribute to the opening tag. Examples:
  * `<blockquote markdown="1">Governments lie; bankers lie; even auditors sometimes lie: gold tells the truth.</blockquote>`
  * `<div class="chart-description" markdown="1">**Chart showing quarterly results:**\n\nRevenue increased by *25%* over the previous quarter.\n</div>`
  * `<div class="diagram-description" markdown="1">## Financial Reporting Framework\n\nThe diagram illustrates the relationship between:\n\n1. **IFRS Standards** - International requirements\n2. **FRS 102** - UK GAAP for most entities\n3. **The Code** - UK Corporate Governance requirements\n</div>`
- **Blockquotes:** Do NOT wrap the entire blockquote content in `**bold**` -- only use bold for specific emphasized words/phrases that are bold in the original PDF. Blockquotes should use normal body text weight by default.
  * **Correct:** `<blockquote markdown="1">Companies should ensure that all requirements are met when presenting disclosures.</blockquote>`
  * **Correct with selective emphasis:** `<blockquote markdown="1">Companies should ensure that **all** requirements are met.</blockquote>`
  * **WRONG:** `<blockquote markdown="1">**Companies should ensure that all requirements are met when presenting disclosures.**</blockquote>`

5. **Numbered Sections and Paragraphs for Web Linking:**
- **Identify numbered sections/paragraphs:** Look for content with explicit numbering like "1.", "2.1", "3.a)", "Section 1", "Paragraph 5", etc.
- **Handle numbered paragraphs and sections differently:**
  * **For numbered paragraphs:** Create self-linking anchor tags: `<a id="paragraph-N" href="#paragraph-N" class="section__global-number">N</a>Content goes here...`
  * **For numbered section headings:** Use markdown headings with attr_list syntax to add IDs: `## Section 2.1 Overview {{: #section-2-1 }}`
  * **IMPORTANT:** Always use markdown syntax (##, ###) for headings, NOT HTML tags. The markdown processor will automatically make all headings self-linking.
- **Anchor ID formatting rules:**
  * Use lowercase for the prefix ("paragraph-" or "section-")
  * Keep numbers and letters exactly as they appear
  * For hierarchical numbering: Use dashes instead of dots for IDs (e.g., `#section-2-1` not `#section-2.1`)
  * **For parenthetical numbering:** Convert to dashes (e.g., "3.a)" becomes `#paragraph-3-a` or `#section-3-a`)
  * For attr_list IDs, use the syntax `{{: #id-name }}` with spaces inside the braces
- **ID Uniqueness:** All `id` attributes MUST be unique within the document. If a number is repeated (e.g., paragraph 1 in multiple sections), create a unique ID by appending a letter or number (e.g., `#paragraph-1`, `#paragraph-1-a`, `#paragraph-1-b`).
- **Examples of numbered content to mark:**
  * **Numbered paragraphs:** "1. The Panel is authorised..." → `<a id="paragraph-1" href="#paragraph-1" class="section__global-number">1</a>The Panel is authorised...`
  * **Numbered paragraphs:** "2.1 Overview details" → `<a id="paragraph-2-1" href="#paragraph-2-1" class="section__global-number">2.1</a>Overview details`
  * **Section headings:** "Section 2.1 Overview" → `## Section 2.1 Overview {{: #section-2-1-overview }}` (Note: ID includes heading text to ensure uniqueness)
  * **Section headings:** "3.a) Requirements" → `### 3.a) Requirements {{: #section-3-a-requirements }}`
  * **Section headings without explicit "Section" word:** "1. 2024/25 highlights" → `## 1. 2024/25 highlights {{: #section-1-2024-25-highlights }}`
  * **Regular headings (no numbers):** "Financial Statements" → `## Financial Statements` (gets auto-generated ID)
- **Custom IDs only for numbered content:** Add attr_list IDs `{{: #section-N }}` only for headings with explicit numbering. Regular headings get auto-generated IDs from their text for TOC linking.

6. **Image Handling:**
- I'm providing an IMAGE REPORT below containing meaningful embedded images that were extracted and uploaded
- When you encounter an embedded image that corresponds to an entry in the IMAGE REPORT, replace it with: `![description from report](URL from report)`
- For charts, diagrams, or illustrations that appear visual but are NOT in the IMAGE REPORT (likely drawn as vector graphics/text), wrap descriptions in semantic HTML: use `<div class="chart-description">` for charts/graphs, `<div class="diagram-description">` for technical diagrams, `<div class="illustration-description">` for other visual elements
- For purely decorative visual elements (borders, design patterns, logos used decoratively), skip them entirely
- Include any image captions or titles as part of the surrounding text context

7. **Content Guidelines:**
- Focus on capturing the semantic meaning of the document
- Preserve the logical flow and relationships between content
- Ensure all content is presented in a screen-reader friendly format
- Include all pages unless they contain only decorative elements
- Keep the output clean and well-structured without extraneous formatting

**IMAGE REPORT:**
{image_report}

---

Provide ONLY the markdown content."""

DEFAULT_MARKDOWN_CONTINUATION_PROMPT: str = """
IMPORTANT: You are continuing a PDF-to-markdown conversion. This is chunk {chunk_number} of {total_chunks}.

The previous chunk ended with:
---
{previous_chunk_markdown_end}
---

CONTINUATION REQUIREMENTS:
1. Continue the conversion seamlessly from where the previous chunk ended
2. If the previous chunk ended mid-list, continue the list with proper numbering/bullets
3. If the previous chunk ended mid-table, continue the table structure
4. If the previous chunk ended mid-paragraph, continue the paragraph naturally
5. Maintain consistent formatting and numbering sequences
6. **MAINTAIN HEADING HIERARCHY:** If the previous chunk was within a numbered section (e.g., "## 3. Risk Assessment"), continue using H3 (###) for subsections within that section. Only use H2 (##) when you reach the next major numbered section (e.g., "## 4. Next Section").
7. Do NOT repeat content from the previous chunk
8. Do NOT include any conversational responses - provide ONLY the markdown content

Continue the markdown conversion now:
"""

DEFAULT_CONVERSATIONAL_PHRASES: list[str] = [
    "no problem, i can help",
    "please provide the pdf",
    "i am ready for the pdf",
    "as per your requirements",
    "i will ensure",
]
