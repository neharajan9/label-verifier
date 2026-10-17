from verifier.models import FAIL, PASS, REVIEW
from verifier.warning import BODY, STANDARD_WARNING, WarningChecker

checker = WarningChecker()


def statuses(text):
    heading, body = checker.check(text)
    return heading.status, body.status


def test_exact_warning_passes():
    assert statuses(STANDARD_WARNING) == (PASS, PASS)


def test_warning_wrapped_across_lines_passes():
    wrapped = STANDARD_WARNING.replace(" women ", "\nwomen ").replace(" machinery", "\nmachinery")
    assert statuses(wrapped) == (PASS, PASS)


def test_hyphenated_line_break_is_rejoined():
    text = STANDARD_WARNING.replace("machinery", "machin-\nery")
    assert statuses(text) == (PASS, PASS)


def test_title_case_heading_fails():
    # Jenny's example: "Government Warning" in title case is a rejection.
    text = STANDARD_WARNING.replace("GOVERNMENT WARNING:", "Government Warning:")
    heading, _ = checker.check(text)
    assert heading.status == FAIL
    assert "ALL CAPS" in heading.reason


def test_heading_without_colon_fails():
    text = STANDARD_WARNING.replace("GOVERNMENT WARNING:", "GOVERNMENT WARNING")
    assert checker.check(text)[0].status == FAIL


def test_reworded_warning_fails():
    text = STANDARD_WARNING.replace("should not drink", "may want to avoid")
    _, body = checker.check(text)
    assert body.status == FAIL
    assert "should not drink" in body.reason


def test_missing_sentence_fails():
    text = STANDARD_WARNING.replace(" and may cause health problems", "")
    assert checker.check(text)[1].status == FAIL


def test_single_character_ocr_misread_needs_review():
    text = STANDARD_WARNING.replace("drive a car", "drive @ car")
    assert checker.check(text)[1].status == REVIEW


def test_missing_warning_fails_both_checks():
    assert statuses("OLD TOM DISTILLERY 45% 750 mL") == (FAIL, FAIL)


def test_bold_is_flagged_for_human_check():
    heading, _ = checker.check(STANDARD_WARNING)
    assert "Bold" in heading.reason


def test_body_constant_is_the_statutory_text():
    assert BODY.startswith("(1) According to the Surgeon General")
    assert BODY.endswith("may cause health problems.")
