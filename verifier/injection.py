"""Plain rules that spot text on a label that looks like a prompt injection.

This runs on the text Claude copied from the label. It is a second check,
alongside Claude's own instructions_found flag. A match never passes or fails
a label by itself. It sends the label to a person to check by eye.
"""
import re

from verifier.models import REVIEW, FieldResult

PATTERNS = [
    r"\b(ignore|disregard|forget|override)\b.{0,40}\b(instruction|rule|prompt|above|previous|prior)",
    r"\b(system|developer)\s+(prompt|message|instruction)",
    r"\byou\s+are\s+(now\s+)?(an?\s+|the\s+)?(ai|assistant|model|chatbot|language model)\b",
    r"\b(as|dear)\s+an?\s+(ai|assistant|language model)\b",
    # Words like "Claude" or "Gemini" are left out: they can be real brand names.
    r"\b(mark|treat|classify)\b.{0,30}\bas\s+(pass|passed|passing|approved|compliant|valid)\b",
    r"\bnew\s+instructions?\b",
    r"\b(chatgpt|llm|large language model)\b",
    r"\b(assistant|system)\s*:",
    r"<\|.*?\|>|</?(system|instructions?)>",
    r"\binstructions_found\b|\blabel_text\b|\bwarning_heading_bold\b",
]
_COMPILED = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in PATTERNS]


def find_injection(text: str) -> str:
    """Return the first suspicious piece of text, or an empty string."""
    for pattern in _COMPILED:
        match = pattern.search(text)
        if match:
            return match.group(0)[:80]
    return ""


def check_injection(text: str, flagged_by_ai: bool) -> FieldResult | None:
    """A REVIEW result when the label looks like it holds AI instructions."""
    snippet = find_injection(text)
    if not snippet and not flagged_by_ai:
        return None
    found = snippet or "(reported by the AI reader)"
    return FieldResult(
        "Hidden instructions", "No text aimed at an AI", found, REVIEW,
        "The label seems to contain instructions for an AI. The automatic results "
        "may not be reliable. Please check this label by eye.")
