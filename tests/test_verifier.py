"""Tests for LabelVerifier, the batch CSV, and end-to-end runs on sample images."""
import os
from pathlib import Path

import pytest

from verifier.models import FAIL, PASS, REVIEW, LabelApplication
from verifier.ai_reader import AiReader, LabelReading, ReadError
from verifier.verifier import LabelVerifier, VerificationReport, load_applications
from verifier.warning import STANDARD_WARNING

SAMPLES = Path(__file__).parent.parent / "sample_labels"
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
# These tests call the real AI service, so they cost a little and need a key.
needs_api_key = pytest.mark.skipif(not API_KEY, reason="ANTHROPIC_API_KEY is not set")

OLD_TOM = LabelApplication("OLD TOM DISTILLERY", "Kentucky Straight Bourbon Whiskey",
                           "45% Alc./Vol. (90 Proof)", "750 mL")
GOOD_LABEL_TEXT = ("OLD TOM DISTILLERY\nKentucky Straight Bourbon Whiskey\n"
                   "45% Alc./Vol. (90 Proof)\n750 mL\n" + STANDARD_WARNING)


class FakeOcr:
    """Stands in for the AI reader so the verifier logic is tested offline."""
    def __init__(self, text="", error=None, bold="bold"):
        self.text, self.error, self.bold = text, error, bold

    def read(self, image_bytes):
        if self.error:
            raise ReadError(self.error)
        return LabelReading(self.text, self.bold)


# ---- LabelVerifier with fake OCR ---------------------------------------------

def test_matching_label_passes():
    report = LabelVerifier(FakeOcr(GOOD_LABEL_TEXT)).verify(b"img", OLD_TOM)
    assert report.status == PASS
    assert [r.field for r in report.results] == [
        "Brand name", "Class/type", "Alcohol content", "Net contents",
        "Warning heading", "Warning text"]


def test_one_bad_field_fails_the_label():
    text = GOOD_LABEL_TEXT.replace("45%", "40%").replace("90 Proof", "80 Proof")
    assert LabelVerifier(FakeOcr(text)).verify(b"img", OLD_TOM).status == FAIL


def test_country_checked_only_when_given():
    app = LabelApplication("OLD TOM DISTILLERY", "Bourbon", "45%", "750 mL", "France")
    report = LabelVerifier(FakeOcr(GOOD_LABEL_TEXT)).verify(b"img", app)
    country = next(r for r in report.results if r.field == "Country of origin")
    assert country.status == FAIL


def test_bottler_checked_only_when_given():
    app = LabelApplication("OLD TOM DISTILLERY", "Kentucky Straight Bourbon Whiskey",
                           "45%", "750 mL", bottler="Bottled by Old Tom Distillery, Bardstown, KY")
    text = GOOD_LABEL_TEXT + "\nBOTTLED BY OLD TOM DISTILLERY, BARDSTOWN, KY"
    report = LabelVerifier(FakeOcr(text)).verify(b"img", app)
    assert next(r for r in report.results if r.field == "Bottler name/address").status == PASS
    report = LabelVerifier(FakeOcr(GOOD_LABEL_TEXT)).verify(b"img", OLD_TOM)
    assert "Bottler name/address" not in [r.field for r in report.results]


def test_heading_not_bold_fails_the_label():
    report = LabelVerifier(FakeOcr(GOOD_LABEL_TEXT, bold="not_bold")).verify(b"img", OLD_TOM)
    assert report.status == FAIL


def test_not_an_image_gives_friendly_error():
    # Fails before any network call, so no key is needed.
    report = LabelVerifier(AiReader("no-key")).verify(b"this is not an image", OLD_TOM)
    assert "isn't an image" in report.error


def test_unreadable_image_reports_error():
    report = LabelVerifier(FakeOcr(error="No readable text")).verify(b"img", OLD_TOM)
    assert report.status == FAIL
    assert report.error == "No readable text"
    assert report.results == []


def test_report_status_priority():
    from verifier.models import FieldResult
    r = VerificationReport("x", [FieldResult("a", "", "", PASS, ""),
                                 FieldResult("b", "", "", REVIEW, "")])
    assert r.status == REVIEW
    r.results.append(FieldResult("c", "", "", FAIL, ""))
    assert r.status == FAIL


def test_batch_flags_missing_rows_and_images():
    verifier = LabelVerifier(FakeOcr(GOOD_LABEL_TEXT))
    reports = verifier.verify_batch({"a.png": b"1", "b.png": b"2"},
                                    {"a.png": OLD_TOM, "c.png": OLD_TOM})
    by_name = {r.filename: r for r in reports}
    assert by_name["a.png"].status == PASS
    assert "No row" in by_name["b.png"].error
    assert "no image" in by_name["c.png"].error


# ---- CSV loading -------------------------------------------------------------

def test_load_applications_reads_rows():
    csv_text = ("filename,brand_name,class_type,alcohol_content,net_contents\n"
                "a.png,Old Tom,Bourbon,45%,750 mL\n")
    apps = load_applications(csv_text)
    assert apps["a.png"].brand_name == "Old Tom"
    assert apps["a.png"].country_of_origin == ""
    assert apps["a.png"].bottler == ""


def test_load_applications_handles_excel_bom_and_header_case():
    csv_text = ("﻿Filename,Brand_Name,Class_Type,Alcohol_Content,Net_Contents\n"
                "a.png,Old Tom,Bourbon,45%,750 mL\n")
    assert "a.png" in load_applications(csv_text)


def test_load_applications_rejects_missing_columns():
    with pytest.raises(ValueError, match="net_contents"):
        load_applications("filename,brand_name,class_type,alcohol_content\n")


# ---- End to end with the real AI reader on the sample labels -----------------

EXPECTED = {
    "01_old_tom_bourbon_pass.png": PASS,
    "02_stones_throw_case_difference_pass.png": PASS,
    "03_titlecase_warning_fail.png": FAIL,
    "04_wrong_abv_fail.png": FAIL,
    "05_altered_warning_fail.png": FAIL,
    "06_imported_wine_pass.png": PASS,
}


@needs_api_key
@pytest.mark.parametrize("filename,expected", EXPECTED.items())
def test_sample_labels(filename, expected):
    apps = load_applications((SAMPLES / "applications.csv").read_text())
    report = LabelVerifier(AiReader(API_KEY)).verify((SAMPLES / filename).read_bytes(), apps[filename], filename)
    assert report.status == expected, [(r.field, r.status, r.reason) for r in report.results]


@needs_api_key
def test_tilted_photo_with_glare_is_not_failed():
    """A poor photo of a good label should pass or go to review, never fail."""
    name = "07_tilted_with_glare.png"
    apps = load_applications((SAMPLES / "applications.csv").read_text())
    report = LabelVerifier(AiReader(API_KEY)).verify((SAMPLES / name).read_bytes(), apps[name], name)
    assert report.status in (PASS, REVIEW)


@needs_api_key
def test_single_label_under_five_seconds():
    """Sarah's requirement: results back in about 5 seconds."""
    name = "01_old_tom_bourbon_pass.png"
    report = LabelVerifier(AiReader(API_KEY)).verify((SAMPLES / name).read_bytes(), OLD_TOM, name)
    assert report.seconds < 5
