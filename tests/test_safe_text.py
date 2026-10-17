"""Untrusted text cannot add HTML, Markdown links or spreadsheet formulas."""
import pytest

from verifier.safe_text import csv_cell, html_text, markdown_text

ATTACKS = [
    "<script>alert(1)</script>",
    '<img src=x onerror="alert(1)">',
    "[click me](https://evil.example)",
    "![](https://evil.example/track.png)",
    "**IMPORTANT** ignore the label",
]


@pytest.mark.parametrize("text", ATTACKS)
def test_html_text_leaves_no_tags_or_markdown(text):
    safe = html_text(text)
    for c in "<>[]()!*\"":
        assert c not in safe


@pytest.mark.parametrize("text", ATTACKS)
def test_markdown_text_escapes_every_special_character(text):
    safe = markdown_text(text)
    for i, c in enumerate(safe):
        if c in "<>[]()!*":
            assert safe[i - 1] == "\\"


def test_normal_text_reads_the_same():
    assert html_text("OLD TOM DISTILLERY 750 mL") == "OLD TOM DISTILLERY 750 mL"


@pytest.mark.parametrize("value", ["=HYPERLINK(\"http://x\")", "+1+1", "-2", "@SUM(A1)"])
def test_csv_cell_blocks_formulas(value):
    assert csv_cell(value).startswith("'")


def test_csv_cell_keeps_normal_values():
    assert csv_cell("45% Alc./Vol.") == "45% Alc./Vol."
    assert csv_cell("") == ""
