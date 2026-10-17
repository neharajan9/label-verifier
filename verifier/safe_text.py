"""Make untrusted text safe to show on screen or write to a CSV file.

Untrusted text is anything a user types or uploads (form fields, CSV rows,
file names) and anything the AI copied from a label image.
"""

# Characters that HTML or Markdown would treat as code or formatting.
_SPECIAL = set("&<>\"'`*_[](){}#!|~\\$=+-.:")


def html_text(text: str) -> str:
    """Show text as plain characters inside an HTML block.

    Every special character becomes a numeric entity, so the text can add
    no tags, scripts, links, images or formatting.
    """
    return "".join(f"&#{ord(c)};" if c in _SPECIAL else c for c in text)


def markdown_text(text: str) -> str:
    """Show text as plain characters where Streamlit reads Markdown."""
    return "".join("\\" + c if c in _SPECIAL else c for c in text)


def csv_cell(value: str) -> str:
    """Stop spreadsheet apps from running a cell as a formula."""
    if value and value[0] in "=+-@\t\r":
        return "'" + value
    return value
