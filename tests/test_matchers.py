from verifier.matchers import match_abv, match_net_contents, match_text, normalize
from verifier.models import FAIL, PASS, REVIEW


def test_normalize_ignores_case_and_apostrophes():
    assert normalize("STONE'S THROW") == normalize("Stone’s Throw") == "stones throw"


class TestMatchText:
    def test_case_difference_passes(self):
        # Dave's example: same brand, different capitalization.
        result = match_text("Brand name", "Stone's Throw", "STONE'S THROW\nLondon Dry Gin")
        assert result.status == PASS

    def test_exact_match_passes(self):
        assert match_text("Brand name", "OLD TOM DISTILLERY",
                          "OLD TOM DISTILLERY\nBourbon").status == PASS

    def test_small_ocr_error_still_passes(self):
        result = match_text("Class/type", "Kentucky Straight Bourbon Whiskey",
                            "Kentucky Straight Bourbon Whiskev")
        assert result.status == PASS

    def test_partial_match_needs_review(self):
        result = match_text("Brand name", "Old Tom Distillery", "OLD TOMB DIST")
        assert result.status == REVIEW

    def test_different_brand_fails(self):
        result = match_text("Brand name", "Old Tom Distillery", "HARBOR LIGHT Spiced Rum")
        assert result.status == FAIL

    def test_blank_optional_field_passes(self):
        assert match_text("Country of origin", "", "anything").status == PASS


class TestMatchAbv:
    def test_same_abv_passes(self):
        result = match_abv("45% Alc./Vol. (90 Proof)", "45% Alc./Vol. (90 Proof)")
        assert result.status == PASS

    def test_application_can_omit_proof(self):
        assert match_abv("45%", "45% Alc./Vol. (90 Proof)").status == PASS

    def test_different_abv_fails(self):
        result = match_abv("45%", "40% Alc./Vol. (80 Proof)")
        assert result.status == FAIL
        assert "40%" in result.reason

    def test_proof_must_be_double_abv(self):
        assert match_abv("45%", "45% Alc./Vol. (80 Proof)").status == FAIL

    def test_decimal_abv(self):
        assert match_abv("13.5%", "13.5% Alc./Vol.").status == PASS

    def test_missing_abv_on_label_fails(self):
        assert match_abv("45%", "OLD TOM DISTILLERY").status == FAIL

    def test_unreadable_application_value_needs_review(self):
        assert match_abv("forty five", "45%").status == REVIEW


class TestMatchNetContents:
    def test_same_volume_passes(self):
        assert match_net_contents("750 mL", "Net 750 mL").status == PASS

    def test_unit_spacing_and_case_ignored(self):
        assert match_net_contents("750 mL", "750ML").status == PASS

    def test_centiliters_converted(self):
        assert match_net_contents("750 mL", "75 cl").status == PASS

    def test_liters_converted(self):
        assert match_net_contents("1000 mL", "1 LITER").status == PASS
        assert match_net_contents("1.75 L", "1750 mL").status == PASS

    def test_different_volume_fails(self):
        assert match_net_contents("750 mL", "375 mL").status == FAIL

    def test_missing_volume_fails(self):
        assert match_net_contents("750 mL", "no volume here").status == FAIL
