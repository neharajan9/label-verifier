"""Field matching functions.

Each function takes the value from the application form and the full OCR
text from the label, and returns a FieldResult. They are plain functions so
they are easy to test without any images.
"""
import re

from rapidfuzz import fuzz

from verifier.models import FAIL, PASS, REVIEW, FieldResult

PASS_SCORE = 90     # at or above: treat as the same text
REVIEW_SCORE = 75   # between REVIEW_SCORE and PASS_SCORE: ask a human


def normalize(text: str) -> str:
    """Lower-case, unify apostrophes, drop punctuation and extra spaces.

    "STONE'S THROW" and "Stone's Throw" both become "stones throw".
    """
    text = text.lower().replace("’", "'").replace("`", "'")
    text = re.sub(r"[^a-z0-9%. ]+", " ", text.replace("'", ""))
    return re.sub(r"\s+", " ", text).strip()


def match_text(field: str, expected: str, ocr_text: str) -> FieldResult:
    """Fuzzy check that the expected text appears somewhere on the label."""
    if not expected.strip():
        return FieldResult(field, expected, "", PASS, "Not provided on the application")

    want = normalize(expected)
    have = normalize(ocr_text)
    if len(have) < len(want):
        # partial_ratio would search for the label inside the expected value,
        # so a short or cut-off label could wrongly pass. Compare whole strings.
        score, found = fuzz.ratio(want, have), have
    else:
        match = fuzz.partial_ratio_alignment(want, have)
        score = match.score if match else 0
        found = have[match.dest_start:match.dest_end] if match else ""

    found = _best_line(expected, ocr_text) or found   # show text as printed

    if score >= PASS_SCORE:
        reason = "Matches" if score == 100 else f"Close match ({score:.0f}%)"
        return FieldResult(field, expected, found, PASS, reason)
    if score >= REVIEW_SCORE:
        return FieldResult(field, expected, found, REVIEW,
                           f"Partial match ({score:.0f}%) - please check by eye")
    return FieldResult(field, expected, found, FAIL, "Not found on the label")


def _best_line(expected: str, ocr_text: str) -> str:
    """The label line (as printed) that looks most like the expected value."""
    want = normalize(expected)
    lines = [line.strip() for line in ocr_text.splitlines() if line.strip()]
    if not lines:
        return ""
    best = max(lines, key=lambda line: fuzz.partial_ratio(want, normalize(line)))
    return best if fuzz.partial_ratio(want, normalize(best)) >= REVIEW_SCORE else ""


def _percentages(text: str) -> list[float]:
    return [float(n) for n in re.findall(r"(\d{1,2}(?:\.\d+)?)\s*%", text)]


def match_abv(expected: str, ocr_text: str) -> FieldResult:
    """Compare alcohol-by-volume numerically, and check proof if shown."""
    field = "Alcohol content"
    wanted = _percentages(expected)
    if not wanted:
        return FieldResult(field, expected, "", REVIEW,
                           "Could not read a % value from the application")
    want = wanted[0]

    on_label = _percentages(ocr_text)
    if not on_label:
        return FieldResult(field, expected, "", FAIL, "No alcohol % found on the label")

    if want not in on_label:
        found = ", ".join(f"{v:g}%" for v in on_label)
        return FieldResult(field, expected, found, FAIL,
                           f"Label shows {found}, application says {want:g}%")

    # Proof is optional, but if printed it must be twice the ABV.
    proofs = [float(p) for p in re.findall(r"(\d{2,3}(?:\.\d+)?)\s*proof", ocr_text, re.I)]
    if proofs and abs(proofs[0] - want * 2) > 0.01:
        return FieldResult(field, expected, f"{want:g}% / {proofs[0]:g} proof", FAIL,
                           f"Proof should be {want * 2:g}, label shows {proofs[0]:g}")

    found = f"{want:g}%" + (f" ({proofs[0]:g} proof)" if proofs else "")
    return FieldResult(field, expected, found, PASS, "Matches")


_UNIT_TO_ML = {"ml": 1, "cl": 10, "l": 1000, "liter": 1000, "litre": 1000,
               "liters": 1000, "litres": 1000, "fl oz": 29.5735, "floz": 29.5735}
_VOLUME_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(ml|cl|fl\.?\s?oz|litres?|liters?|l)\b", re.I)


def _volumes_ml(text: str) -> list[float]:
    volumes = []
    for number, unit in _VOLUME_RE.findall(text):
        unit = re.sub(r"[.\s]", "", unit.lower())
        unit = "fl oz" if unit == "floz" else unit
        volumes.append(float(number.replace(",", ".")) * _UNIT_TO_ML[unit])
    return volumes


def match_net_contents(expected: str, ocr_text: str) -> FieldResult:
    """Compare volumes after converting to mL (750 mL == 75 cl == 0.75 L)."""
    field = "Net contents"
    wanted = _volumes_ml(expected)
    if not wanted:
        return FieldResult(field, expected, "", REVIEW,
                           "Could not read a volume from the application")
    on_label = _volumes_ml(ocr_text)
    if not on_label:
        return FieldResult(field, expected, "", FAIL, "No volume found on the label")

    for volume in on_label:
        if abs(volume - wanted[0]) / wanted[0] < 0.01:
            return FieldResult(field, expected, f"{volume:g} mL", PASS, "Matches")
    found = ", ".join(f"{v:g} mL" for v in on_label)
    return FieldResult(field, expected, found, FAIL,
                       f"Label shows {found}, application says {wanted[0]:g} mL")
