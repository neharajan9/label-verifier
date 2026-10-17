"""Streamlit screen for the label verifier. All checking logic lives in verifier/."""
import csv
import hashlib
import io
import os
from pathlib import Path

import streamlit as st
from PIL import Image, ImageOps

from verifier.ai_reader import AiReader
from verifier.models import FAIL, PASS, REVIEW, LabelApplication
from verifier.safe_text import csv_cell, html_text
from verifier.verifier import CSV_COLUMNS, LabelVerifier, VerificationReport, load_applications

SAMPLES = Path(__file__).parent / "sample_labels"
TAGS = {PASS: "MATCH", REVIEW: "CHECK", FAIL: "MISMATCH"}
WORDS = {PASS: "Matches", REVIEW: "Check by eye", FAIL: "Likely does not match"}
MAX_BATCH = 500
WAIT_ONE = "Reading the label. This usually takes about 5 seconds..."

st.set_page_config(page_title="Label Verifier", layout="wide")

# Large text, strong contrast, and status shown by word as well as colour.
st.markdown("""
<style>
.stMarkdown p, .stMarkdown li, [data-testid="stWidgetLabel"] p, input, button[role="tab"] p,
[data-testid="stAlert"] p, [data-testid="stFileUploaderDropzone"] span,
[data-testid="stExpander"] summary p { font-size: 1.2rem !important; }
.stButton button p, .stDownloadButton button p { font-size: 1.25rem !important; font-weight: 600; }
.stButton button { padding: 0.65rem 1.5rem; }
.step { font-size: 1.35rem; font-weight: 700; color: #1f2937; margin: 0.25rem 0 0.5rem; }
.hint { font-size: 1.1rem; color: #374151; }

.banner { padding: 1rem 1.25rem; border-left: 10px solid; border-radius: 6px; margin-bottom: 1rem; }
.banner .title { font-size: 1.7rem; font-weight: 700; line-height: 1.3; }
.banner .detail { font-size: 1.2rem; margin-top: 0.3rem; }
.banner.PASS { border-color: #1e7b45; background: #eaf5ee; color: #12512d; }
.banner.REVIEW { border-color: #b7791f; background: #fdf4e3; color: #6b4610; }
.banner.FAIL { border-color: #b42318; background: #fdecea; color: #7a1a12; }

.item { border: 1px solid #d0d5dd; border-left: 8px solid; border-radius: 6px;
        padding: 0.8rem 1rem; margin-bottom: 0.7rem; background: #ffffff; }
.item.PASS { border-left-color: #1e7b45; }
.item.REVIEW { border-left-color: #b7791f; }
.item.FAIL { border-left-color: #b42318; }
.item .name { font-size: 1.25rem; font-weight: 700; color: #111827; }
.item .row { font-size: 1.15rem; margin-top: 0.3rem; color: #111827; }
.item .row span { display: inline-block; min-width: 7.5rem; color: #4b5563; }
.item .why { font-size: 1.05rem; color: #374151; margin-top: 0.4rem; }
.tag { display: inline-block; font-size: 0.85rem; font-weight: 700; letter-spacing: 0.06em;
       padding: 0.15rem 0.55rem; border-radius: 4px; color: #ffffff; margin-left: 0.6rem;
       vertical-align: middle; }
.tag.PASS { background: #1e7b45; }
.tag.REVIEW { background: #9a6215; }
.tag.FAIL { background: #b42318; }
</style>
""", unsafe_allow_html=True)


def api_key() -> str:
    """From Streamlit secrets (the hosted app) or an environment variable (local)."""
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:          # no secrets file
        key = ""
    return (key or os.environ.get("ANTHROPIC_API_KEY", "")).strip()


@st.cache_resource
def get_verifier(key: str) -> LabelVerifier:
    return LabelVerifier(AiReader(key))


# ---- Result display ------------------------------------------------------------------

def summary(report: VerificationReport) -> tuple[str, str]:
    """The headline and one plain sentence for the result box."""
    if report.error:
        return "Could not check this label", report.error
    attention = [r.field for r in report.results if r.status != PASS]
    total = len(report.results)
    if not attention:
        return "All items match", f"All {total} items match the application."
    title = "Check by eye" if report.status == REVIEW else "Likely does not match"
    noun = "item needs" if len(attention) == 1 else "items need"
    return title, f"{len(attention)} {noun} attention: {', '.join(attention)}."


def show_banner(title: str, detail: str, status: str) -> None:
    st.markdown(f'<div class="banner {status}"><div class="title">{html_text(title)}</div>'
                f'<div class="detail">{html_text(detail)}</div></div>', unsafe_allow_html=True)


def show_item(r) -> None:
    found = r.found if r.found else "(not found on label)"
    # The warning is compared with the legal text, everything else with the application.
    source = "Required:" if r.field.startswith("Warning") or r.field == "Hidden instructions" \
        else "Application:"
    st.markdown(
        f'<div class="item {r.status}"><div class="name">{html_text(r.field)}'
        f'<span class="tag {r.status}">{TAGS[r.status]}</span></div>'
        f'<div class="row"><span>{source}</span>{html_text(r.expected)}</div>'
        f'<div class="row"><span>Label:</span>{html_text(found)}</div>'
        f'<div class="why">{html_text(r.reason)}</div></div>',
        unsafe_allow_html=True)


def show_report(report: VerificationReport) -> None:
    """Result box first, then the items that need attention, then the rest folded away."""
    title, detail = summary(report)
    if not report.error:
        detail += f" Checked in {report.seconds:.1f} seconds."
    show_banner(title, detail, report.status)
    if report.error:
        return

    for r in report.results:
        if r.status != PASS:
            show_item(r)
    matched = [r for r in report.results if r.status == PASS]
    if matched:
        with st.expander(f"{len(matched)} items match - show them"):
            for r in matched:
                show_item(r)
    with st.expander("Show all text read from the label"):
        st.text(report.label_text)
    st.caption("The app suggests a result. The reviewer makes the final decision.")


@st.cache_data(max_entries=50, show_spinner=False)
def clean_image(image_bytes: bytes, max_side: int = 1600) -> bytes | None:
    """A re-saved copy of an uploaded photo, for showing on screen.

    The browser only ever gets a JPEG made by Pillow, never the uploaded file
    itself, so a disguised non-image file cannot reach the page. Returns None
    if the file is not an image.
    """
    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
        image.thumbnail((max_side, max_side))
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=85)
        return out.getvalue()
    except Exception:
        return None


# ---- Single label --------------------------------------------------------------------

FIELDS = ["brand", "class_type", "abv", "net", "country", "bottler"]


def load_example() -> None:
    st.session_state.update(
        brand="OLD TOM DISTILLERY", class_type="Kentucky Straight Bourbon Whiskey",
        abv="45% Alc./Vol. (90 Proof)", net="750 mL", country="", bottler="",
        example=(SAMPLES / "01_old_tom_bourbon_pass.png").read_bytes())
    st.session_state.pop("single", None)


def _set_busy(key: str) -> None:
    st.session_state[key] = True


def start_over() -> None:
    for key in FIELDS:
        st.session_state[key] = ""
    for key in ("example", "single"):
        st.session_state.pop(key, None)
    st.session_state["upload_round"] = st.session_state.get("upload_round", 0) + 1


def single_label_tab() -> None:
    top = st.columns([3, 1, 1])
    top[0].markdown('<p class="hint">Add the label photo, type what the application says, '
                    'then press Check label.</p>', unsafe_allow_html=True)
    top[1].button("Try an example", on_click=load_example, width="stretch")
    top[2].button("Start over", on_click=start_over, width="stretch")

    left, right = st.columns([1, 1], gap="large")

    with left:
        st.markdown('<p class="step">Step 1. Label photo</p>', unsafe_allow_html=True)
        upload = st.file_uploader("Label photo (JPG or PNG)", type=["jpg", "jpeg", "png"],
                                  key=f"upload_{st.session_state.get('upload_round', 0)}")
        image = upload.getvalue() if upload else st.session_state.get("example")
        if image:
            shown = clean_image(image)
            if shown:
                st.image(shown, width="stretch")
                st.caption("Hover over the photo and use the expand button to see it full size.")
            else:
                st.error("This file can't be shown. It may not be a real JPG or PNG image.")

    with right:
        result_area = st.container()   # the result goes here, at the top, beside the photo

        st.markdown('<p class="step">Step 2. What the application says</p>',
                    unsafe_allow_html=True)
        brand = st.text_input("Brand name", key="brand", placeholder="e.g. OLD TOM DISTILLERY")
        class_type = st.text_input("Class or type of drink", key="class_type",
                                   placeholder="e.g. Kentucky Straight Bourbon Whiskey")
        abv = st.text_input("Alcohol content", key="abv", placeholder="e.g. 45% Alc./Vol.")
        net = st.text_input("Net contents (bottle size)", key="net", placeholder="e.g. 750 mL")
        country = st.text_input("Country of origin (imports only, optional)", key="country",
                                placeholder="e.g. France")
        bottler = st.text_input("Bottler name and address (optional)", key="bottler",
                                placeholder="e.g. Bottled by Old Tom Distillery, Bardstown, KY")

        st.markdown('<p class="step">Step 3. Check</p>', unsafe_allow_html=True)
        missing = ([] if image else ["label photo"]) + [
            name for name, value in [("brand name", brand), ("class or type", class_type),
                                     ("alcohol content", abv), ("net contents", net)]
            if not value.strip()]
        if missing:
            st.markdown(f'<p class="hint">Still needed: {html_text(", ".join(missing))}.</p>',
                        unsafe_allow_html=True)

        app = LabelApplication(brand, class_type, abv, net, country, bottler)
        fingerprint = (hashlib.sha256(image).hexdigest() if image else "", tuple(vars(app).values()))

        # The click only sets "busy". The next run draws the button greyed out, then
        # does the work, then reruns so the button comes back.
        busy = st.session_state.get("single_busy", False)
        st.button("Processing..." if busy else "Check label", type="primary", width="stretch",
                  disabled=bool(missing) or busy, on_click=_set_busy, args=("single_busy",))
        if busy:
            try:
                with result_area, st.spinner(WAIT_ONE):
                    report = get_verifier(api_key()).verify(image, app)
                st.session_state["single"] = (fingerprint, report)
            finally:
                st.session_state["single_busy"] = False
            st.rerun()

        # Show the result only while it still matches the photo and details on screen.
        saved = st.session_state.get("single")
        if saved and saved[0] == fingerprint:
            with result_area:
                st.markdown('<p class="step">Result</p>', unsafe_allow_html=True)
                show_report(saved[1])
                st.divider()
        elif saved:
            with result_area:
                st.info("The photo or details changed. Press Check label to check again.")


# ---- Batch ---------------------------------------------------------------------------

def batch_tab() -> None:
    st.markdown('<p class="hint">Check many labels at once. Add all the label photos, plus '
                'one spreadsheet (CSV file) with a row for each photo.</p>',
                unsafe_allow_html=True)
    with st.expander("How should the spreadsheet look?"):
        st.write("One row per label. The **filename** column must match the photo's file "
                 "name. **country_of_origin** and **bottler** can be left blank.")
        template = ",".join(CSV_COLUMNS) + "\n" + \
            "old_tom.png,OLD TOM DISTILLERY,Kentucky Straight Bourbon Whiskey,45%,750 mL,,\n"
        st.code(template, language="text")
        st.download_button("Download a blank spreadsheet", template, "applications_template.csv")
        st.download_button("Download the example spreadsheet",
                           (SAMPLES / "applications.csv").read_bytes(), "applications.csv")

    st.markdown('<p class="step">Step 1. Label photos</p>', unsafe_allow_html=True)
    images = st.file_uploader("Label photos", type=["jpg", "jpeg", "png"],
                              accept_multiple_files=True)
    st.markdown('<p class="step">Step 2. Application spreadsheet</p>', unsafe_allow_html=True)
    csv_file = st.file_uploader("Application data (CSV)", type=["csv"])
    use_examples = st.checkbox("Use the 7 example labels instead")

    st.markdown('<p class="step">Step 3. Check</p>', unsafe_allow_html=True)
    ready = use_examples or (images and csv_file)
    if not ready:
        st.markdown('<p class="hint">Still needed: label photos and the spreadsheet.</p>',
                    unsafe_allow_html=True)

    busy = st.session_state.get("batch_busy", False)
    st.button("Processing..." if busy else "Check all labels", type="primary",
              disabled=not ready or busy, on_click=_set_busy, args=("batch_busy",))
    if not busy:
        if st.session_state.get("batch_error"):
            st.error(st.session_state["batch_error"])
        elif "batch" in st.session_state:
            show_batch_results(*st.session_state["batch"])
        return
    st.session_state.pop("batch_error", None)
    st.session_state.pop("batch", None)
    try:
        run_batch(images, csv_file, use_examples)
    finally:
        st.session_state["batch_busy"] = False
    st.rerun()


def run_batch(images, csv_file, use_examples: bool) -> None:
    """Check every label and keep the results for display."""

    if use_examples:
        image_bytes = {p.name: p.read_bytes() for p in sorted(SAMPLES.glob("*.png"))}
        csv_text = (SAMPLES / "applications.csv").read_text()
    else:
        image_bytes = {f.name: f.getvalue() for f in images}
        csv_text = csv_file.getvalue().decode("utf-8-sig", errors="replace")

    if len(image_bytes) > MAX_BATCH:
        st.session_state["batch_error"] = f"Please add at most {MAX_BATCH} photos at a time."
        return
    try:
        applications = load_applications(csv_text)
    except ValueError as exc:
        st.session_state["batch_error"] = f"There is a problem with the spreadsheet: {exc}"
        return

    total = len(image_bytes)
    bar = st.progress(0, text=f"Reading {total} labels, several at a time...")
    reports = get_verifier(api_key()).verify_batch(
        image_bytes, applications,
        on_progress=lambda done, total: bar.progress(done / total,
                                                     text=f"Checked {done} of {total} labels"))
    bar.empty()
    thumbs = {name: clean_image(data, 700) for name, data in image_bytes.items()}
    st.session_state["batch"] = (reports, thumbs)


def show_batch_results(reports: list[VerificationReport], thumbs: dict) -> None:
    counts = {s: sum(r.status == s for r in reports) for s in (PASS, REVIEW, FAIL)}
    attention = counts[REVIEW] + counts[FAIL]
    st.divider()
    if attention:
        show_banner(f"{attention} of {len(reports)} labels need attention",
                    f"{counts[PASS]} match, {counts[REVIEW]} to check by eye, "
                    f"{counts[FAIL]} likely do not match. They are listed first below.",
                    FAIL if counts[FAIL] else REVIEW)
    else:
        show_banner(f"All {len(reports)} labels match", "No label needs attention.", PASS)
    st.download_button("Download results (CSV)", results_csv(reports), "label_results.csv")

    rows = [{"Result": WORDS[r.status], "File": r.filename,
             "Issues": r.error or "; ".join(f"{x.field}: {x.reason}"
                                            for x in r.results if x.status != PASS)}
            for r in reports]
    st.dataframe(rows, width="stretch", hide_index=True)

    st.markdown('<p class="step">Each label</p>', unsafe_allow_html=True)
    order = {FAIL: 0, REVIEW: 1, PASS: 2}
    for r in sorted(reports, key=lambda r: (order[r.status], r.filename)):
        # Expander titles read Markdown, so the file name is shown in a code span.
        with st.expander(f"{WORDS[r.status]}:  `{r.filename.replace('`', '')}`",
                         expanded=False):
            photo, details = st.columns([1, 2], gap="large")
            if thumbs.get(r.filename):
                photo.image(thumbs[r.filename], width="stretch")
            with details:
                show_report(r)


def results_csv(reports: list[VerificationReport]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["filename", "overall", "field", "status", "application", "label", "reason"])
    for r in reports:
        rows = [[r.filename, r.status, "", "", "", "", r.error]] if r.error else []
        rows += [[r.filename, r.status, x.field, x.status, x.expected, x.found, x.reason]
                 for x in r.results]
        for row in rows:
            writer.writerow([csv_cell(v) for v in row])
    return out.getvalue()


# ---- Page ----------------------------------------------------------------------------

st.title("Alcohol Label Verifier")
st.caption("Compares a label photo with its application and checks the Government Warning. "
           "Labels are read by Claude AI. The app suggests a result; the reviewer makes "
           "the final decision. This app does not save photos or results.")
if not api_key():
    st.error("**The AI service is not set up.** Add ANTHROPIC_API_KEY to the app's secrets "
             "(Streamlit: Settings, then Secrets) or set it as an environment variable, "
             "then reload this page.")
    st.stop()

one, many = st.tabs(["Check one label", "Check many labels"])
with one:
    single_label_tab()
with many:
    batch_tab()
