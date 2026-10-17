"""Plain data holders used across the app."""
from dataclasses import dataclass

PASS = "PASS"
REVIEW = "REVIEW"
FAIL = "FAIL"


@dataclass
class LabelApplication:
    """The values an applicant typed into the application form."""
    brand_name: str
    class_type: str
    alcohol_content: str
    net_contents: str
    country_of_origin: str = ""   # only required for imports


@dataclass
class FieldResult:
    """Outcome of checking one field on the label."""
    field: str
    expected: str
    found: str
    status: str      # PASS, REVIEW or FAIL
    reason: str
