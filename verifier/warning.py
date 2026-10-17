"""Government Health Warning check (27 CFR 16.21).

The wording must be word-for-word and the heading "GOVERNMENT WARNING:"
must be in capital letters and bold. Bold type is judged by the AI reader;
if it is unsure, the agent is asked to confirm by eye.
"""
import difflib
import re

from rapidfuzz import fuzz

from verifier.models import FAIL, PASS, REVIEW, FieldResult

HEADING = "GOVERNMENT WARNING:"
BODY = (
    "(1) According to the Surgeon General, women should not drink alcoholic "
    "beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car "
    "or operate machinery, and may cause health problems."
)
STANDARD_WARNING = f"{HEADING} {BODY}"

# Reading small print can misread a character or two. If every changed word
# is at least this similar to the expected word, we treat it as a misread and
# ask a human to confirm rather than failing the label.
WORD_SIMILARITY = 70


def _clean(text: str) -> str:
    text = re.sub(r"-\s*\n\s*", "", text)       # re-join hyphenated line breaks
    text = text.replace("’", "'")
    return re.sub(r"\s+", " ", text).strip()


class WarningChecker:
    def check(self, label_text: str, heading_bold: str = "unsure") -> list[FieldResult]:
        text = _clean(label_text)
        heading = self._check_heading(text, heading_bold)
        body = self._check_body(text)
        return [heading, body]

    def _check_heading(self, text: str, heading_bold: str) -> FieldResult:
        field = "Warning heading"
        if HEADING in text:
            if heading_bold == "bold":
                return FieldResult(field, HEADING, HEADING, PASS, "All caps and bold")
            if heading_bold == "not_bold":
                return FieldResult(field, HEADING, HEADING, FAIL,
                                   "All caps, but the heading is not in bold type")
            return FieldResult(field, HEADING, HEADING, REVIEW,
                               "All caps. Could not tell if it is bold - please check by eye")
        found = re.search(r"government\s+warning\s*:?", text, re.I)
        if found:
            return FieldResult(field, HEADING, found.group(0), FAIL,
                               "Heading must be in ALL CAPS with a colon")
        return FieldResult(field, HEADING, "", FAIL, "Government warning not found")

    def _check_body(self, text: str) -> FieldResult:
        field = "Warning text"
        start = re.search(r"government\s+warning\s*:?", text, re.I)
        if not start:
            return FieldResult(field, BODY, "", FAIL, "Government warning not found")

        after = text[start.end():].strip()
        found = after[:len(BODY) + 40]              # warning plus a little slack
        if BODY in after:
            return FieldResult(field, BODY, BODY, PASS, "Word-for-word match")

        changes = self._word_changes(BODY, found)
        summary = "; ".join(self._describe(exp, got) for exp, got in changes[:3])
        # If every difference is a near-identical word ("machinery," vs
        # "machinerv,") it is most likely a misread, so ask a human to look.
        # A real wording change ("should not drink" -> "may want to avoid") fails.
        if all(self._looks_like_ocr_noise(exp, got) for exp, got in changes):
            return FieldResult(field, BODY, found, REVIEW,
                               f"Nearly exact - may be a misread. Check: {summary}")
        return FieldResult(field, BODY, found, FAIL, f"Wording differs: {summary}")

    @staticmethod
    def _word_changes(expected: str, found: str) -> list[tuple[str, str]]:
        """(expected words, found words) for each place the texts differ."""
        want, have = expected.split(), found.split()
        changes = []
        matcher = difflib.SequenceMatcher(a=want, b=have, autojunk=False)
        for op, a1, a2, b1, b2 in matcher.get_opcodes():
            if op == "equal" or a1 == len(want):    # ignore text after the warning
                continue
            changes.append((" ".join(want[a1:a2]), " ".join(have[b1:b2])))
        return changes

    @staticmethod
    def _looks_like_ocr_noise(exp: str, got: str) -> bool:
        if not exp or not got:
            return False                           # a whole word added or removed
        if max(len(exp), len(got)) <= 2:
            return True                            # "a" read as "@"
        return fuzz.ratio(exp, got) >= WORD_SIMILARITY

    @staticmethod
    def _describe(exp: str, got: str) -> str:
        if not got:
            return f'missing "{exp}"'
        if not exp:
            return f'extra "{got}"'
        return f'expected "{exp}" but found "{got}"'
