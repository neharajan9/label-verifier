"""Ties the AI reader and the field checks together, for one label or a batch."""
import csv
import io
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from verifier.matchers import match_abv, match_net_contents, match_text
from verifier.models import FAIL, PASS, REVIEW, FieldResult, LabelApplication
from verifier.ai_reader import AiReader, LabelReading, ReadError
from verifier.injection import check_injection
from verifier.warning import WarningChecker

CSV_COLUMNS = ["filename", "brand_name", "class_type", "alcohol_content",
               "net_contents", "country_of_origin", "bottler"]
REQUIRED_COLUMNS = CSV_COLUMNS[:5]


@dataclass
class VerificationReport:
    filename: str
    results: list[FieldResult] = field(default_factory=list)
    label_text: str = ""
    error: str = ""
    seconds: float = 0.0

    @property
    def status(self) -> str:
        if self.error:
            return FAIL
        statuses = {r.status for r in self.results}
        if FAIL in statuses:
            return FAIL
        return REVIEW if REVIEW in statuses else PASS


class LabelVerifier:
    def __init__(self, reader: AiReader):
        self.reader = reader
        self.warning_checker = WarningChecker()

    def verify(self, image_bytes: bytes, app: LabelApplication,
               filename: str = "label") -> VerificationReport:
        started = time.perf_counter()
        report = VerificationReport(filename)
        try:
            reading = self.reader.read(image_bytes)
        except ReadError as exc:
            report.error = str(exc)
        else:
            report.label_text = reading.text
            report.results = self.check_reading(reading, app)
        report.seconds = time.perf_counter() - started
        return report

    def check_reading(self, reading: LabelReading, app: LabelApplication) -> list[FieldResult]:
        """All field checks against text the reader already extracted."""
        ocr_text = reading.text
        results = [
            match_text("Brand name", app.brand_name, ocr_text),
            match_text("Class/type", app.class_type, ocr_text),
            match_abv(app.alcohol_content, ocr_text),
            match_net_contents(app.net_contents, ocr_text),
        ]
        if app.country_of_origin.strip():
            results.append(match_text("Country of origin", app.country_of_origin, ocr_text))
        if app.bottler.strip():
            results.append(match_text("Bottler name/address", app.bottler, ocr_text))
        results.extend(self.warning_checker.check(ocr_text, reading.heading_bold))
        injection = check_injection(ocr_text, reading.instructions_found)
        if injection:
            results.insert(0, injection)
        return results

    def verify_batch(self, images: dict[str, bytes],
                     applications: dict[str, LabelApplication],
                     workers: int = 8,
                     on_progress: Callable[[int, int], None] | None = None,
                     ) -> list[VerificationReport]:
        """Verify many labels in parallel. Each label is one AI call that
        mostly waits on the network, so threads work well. on_progress(done,
        total) is called after each label, e.g. to move a progress bar."""
        def one(name: str) -> VerificationReport:
            app = applications.get(name)
            if app is None:
                return VerificationReport(name, error="No row for this image in the CSV file")
            return self.verify(images[name], app, name)

        names = sorted(images)
        reports = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for report in pool.map(one, names):
                reports.append(report)
                if on_progress:
                    on_progress(len(reports), len(names))

        for name in sorted(set(applications) - set(images)):
            reports.append(VerificationReport(name, error="Listed in the CSV but no image uploaded"))
        return reports


def load_applications(csv_text: str) -> dict[str, LabelApplication]:
    """Read the batch CSV: one row per label, keyed by image filename."""
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("﻿")))
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in headers]
    if missing:
        raise ValueError(f"CSV is missing column(s): {', '.join(missing)}")

    apps = {}
    for row in reader:
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        if not row.get("filename"):
            continue
        apps[row["filename"]] = LabelApplication(
            brand_name=row["brand_name"],
            class_type=row["class_type"],
            alcohol_content=row["alcohol_content"],
            net_contents=row["net_contents"],
            country_of_origin=row.get("country_of_origin", ""),
            bottler=row.get("bottler", ""),
        )
    return apps
