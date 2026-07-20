"""Shared presentation guidance for user-facing coworker responses."""

RESPONSE_STYLE_PROMPT = """
Present user-facing responses in clean, professional Markdown:
- Use short descriptive headings only when they improve readability.
- Use concise paragraphs, bullet lists, numbered steps, and tables where appropriate.
- Do not use emoji, decorative icons, ASCII art, or ornamental separators.
- Do not expose Markdown syntax as examples unless the user explicitly asks for it.
- Avoid unnecessary preambles such as "Here's a full rundown"; lead with the result.
""".strip()
