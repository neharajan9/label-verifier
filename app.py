"""Streamlit screen for the label verifier. All checking logic lives in verifier/."""
import csv
import io
from pathlib import Path

import streamlit as st

from verifier.models import FAIL, PASS, REVIEW, LabelApplication
from verifier.verifier import CSV_COLUMNS, LabelVerifier, VerificationReport, load_applications

SAMPLES = Path(__file__).parent / "sample_labels"
ICONS = {PASS: "✅", REVIEW: "⚠️", FAIL: "❌"}
WORDS = {PASS: "Matches", REVIEW: "Check by eye", FAIL: "Does not match"}
BATCH_WORDS = {PASS: "Passed", REVIEW: "Check by eye", FAIL: "Problems"}
MAX_BATCH = 500

st.set_page_config(page_title="Label Verifier", page_icon="🔍", layout="wide")

# Larger text and buttons, for readability.
st.markdown("""
<style>
.stMarkdown p, [data-testid="stWidgetLabel"] p, input, button[role="tab"] p, [data-testid="stAlert"] p,
[data-testid="stFileUploaderDropzone"] span { font-size: 1.2rem !important; }
.stButton button p, .stDownloadButton button p { font-size: 1.25rem !important; }
.stButton button { padding: 0.6rem 2rem; }
.result-row { padding: 0.7rem 1rem; border-radius: 8px; margin-bottom: 0.5rem; font-size: 1.15rem; }
.result-row small { font-size: 1rem; }
.PASS { background: rgba(33, 150, 83, 0.12); }
.REVIEW { background: rgba(230, 160, 0, 0.16); }
.FAIL { background: rgba(214, 48, 49, 0.12); }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_verifier() -> LabelVerifier:
    return LabelVerifier()


def show_overall(report: VerificationReport) -> None:
    if report.error:
        st.error(f"❌ **Could not check this label.** {report.error}")
    elif report.status == PASS:
        st.success(f"✅ **All checks passed** ({report.seconds:.1f} seconds)")
    elif report.status == REVIEW:
        st.warning(f"⚠️ **Needs a quick look** - see the yellow items below "
                   f"({report.seconds:.1f} seconds)")
    else:
        st.error(f"❌ **Problems found** - see the red items below ({report.seconds:.1f} seconds)")


def show_results(report: VerificationReport) -> None:
    show_overall(report)
    for r in report.results:
        found = r.found if r.found else "(nothing found)"
        st.markdown(
            f'<div class="result-row {r.status}">{ICONS[r.status]} <b>{r.field}: '
            f'{WORDS[r.status]}</b><br>'
            f'<small>Expected: {_html(r.expected)}<br>Label: {_html(found)}<br>'
            f'{_html(r.reason)}</small></div>',
            unsafe_allow_html=True)
    if report.ocr_text:
        with st.expander("Show all text read from the label"):
            st.text(report.ocr_text)


def _html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---- Single label --------------------------------------------------------------

def single_label_tab() -> None:
    st.write("**1.** Upload a photo of the label. **2.** Type what the application says. "
             "**3.** Click **Check label**.")

    if st.button("Load an example label", type="secondary"):
        st.session_state.update(
            brand="OLD TOM DISTILLERY", class_type="Kentucky Straight Bourbon Whiskey",
            abv="45% Alc./Vol. (90 Proof)", net="750 mL", country="",
            example=(SAMPLES / "01_old_tom_bourbon_pass.png").read_bytes())

    left, right = st.columns(2, gap="large")
    with left:
        upload = st.file_uploader("Label image (JPG or PNG)", type=["jpg", "jpeg", "png"])
        image = upload.getvalue() if upload else st.session_state.get("example")
        if image:
            st.image(image, width="stretch")

    with right:
        brand = st.text_input("Brand name", key="brand", placeholder="e.g. OLD TOM DISTILLERY")
        class_type = st.text_input("Class / type", key="class_type",
                                   placeholder="e.g. Kentucky Straight Bourbon Whiskey")
        abv = st.text_input("Alcohol content", key="abv", placeholder="e.g. 45% Alc./Vol.")
        net = st.text_input("Net contents", key="net", placeholder="e.g. 750 mL")
        country = st.text_input("Country of origin (imports only)", key="country")

        if st.button("Check label", type="primary", width="stretch"):
            missing = [n for n, v in [("Brand name", brand), ("Class / type", class_type),
                                      ("Alcohol content", abv), ("Net contents", net)]
                       if not v.strip()]
            if not image:
                st.error("Please upload a label image first.")
            elif missing:
                st.error("Please fill in: " + ", ".join(missing))
            else:
                app = LabelApplication(brand, class_type, abv, net, country)
                with st.spinner("Reading the label..."):
                    st.session_state["single_report"] = get_verifier().verify(image, app)

    if "single_report" in st.session_state:
        st.divider()
        show_results(st.session_state["single_report"])


# ---- Batch -------------------------------------------------------------------------

def batch_tab() -> None:
    st.write("Check many labels at once. Upload all the label images, plus one CSV file "
             "with a row for each image.")
    with st.expander("What should the CSV file look like?"):
        st.write("One row per label. The **filename** column must match the image file name. "
                 "**country_of_origin** can be left blank.")
        template = ",".join(CSV_COLUMNS) + "\n" + \
            "old_tom.png,OLD TOM DISTILLERY,Kentucky Straight Bourbon Whiskey,45%,750 mL,\n"
        st.code(template, language="text")
        st.download_button("Download blank template", template, "applications_template.csv")
        st.download_button("Download the example labels' CSV",
                           (SAMPLES / "applications.csv").read_bytes(), "applications.csv")

    images = st.file_uploader("Label images", type=["jpg", "jpeg", "png"],
                              accept_multiple_files=True)
    csv_file = st.file_uploader("Application data (CSV)", type=["csv"])
    use_examples = st.checkbox("Use the 7 example labels instead")

    if not st.button("Check all labels", type="primary"):
        if "batch_reports" in st.session_state:
            show_batch_results(st.session_state["batch_reports"])
        return

    if use_examples:
        image_bytes = {p.name: p.read_bytes() for p in sorted(SAMPLES.glob("*.png"))}
        csv_text = (SAMPLES / "applications.csv").read_text()
    else:
        if not images or not csv_file:
            st.error("Please upload the label images and the CSV file.")
            return
        image_bytes = {f.name: f.getvalue() for f in images}
        csv_text = csv_file.getvalue().decode("utf-8-sig", errors="replace")

    if len(image_bytes) > MAX_BATCH:
        st.error(f"Please upload at most {MAX_BATCH} images at a time.")
        return
    try:
        applications = load_applications(csv_text)
    except ValueError as exc:
        st.error(f"There is a problem with the CSV file: {exc}")
        return

    bar = st.progress(0, text="Starting...")
    reports = get_verifier().verify_batch(
        image_bytes, applications,
        on_progress=lambda done, total: bar.progress(done / total,
                                                     text=f"Checked {done} of {total} labels"))
    bar.empty()
    st.session_state["batch_reports"] = reports
    show_batch_results(reports)


def show_batch_results(reports: list[VerificationReport]) -> None:
    counts = {s: sum(r.status == s for r in reports) for s in (PASS, REVIEW, FAIL)}
    st.divider()
    a, b, c = st.columns(3)
    a.metric("✅ Passed", counts[PASS])
    b.metric("⚠️ Check by eye", counts[REVIEW])
    c.metric("❌ Problems", counts[FAIL])

    rows = [{"Status": f"{ICONS[r.status]} {BATCH_WORDS[r.status]}", "File": r.filename,
             "Issues": r.error or "; ".join(f"{x.field}: {x.reason}"
                                            for x in r.results if x.status != PASS)}
            for r in reports]
    st.dataframe(rows, width="stretch", hide_index=True)
    st.download_button("Download results (CSV)", results_csv(reports), "label_results.csv")

    st.subheader("Details")
    order = {FAIL: 0, REVIEW: 1, PASS: 2}
    for r in sorted(reports, key=lambda r: (order[r.status], r.filename)):
        with st.expander(f"{ICONS[r.status]} {r.filename}"):
            show_results(r)


def results_csv(reports: list[VerificationReport]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["filename", "overall", "field", "status", "application", "label", "reason"])
    for r in reports:
        if r.error:
            writer.writerow([r.filename, r.status, "", "", "", "", r.error])
        for x in r.results:
            writer.writerow([r.filename, r.status, x.field, x.status, x.expected, x.found, x.reason])
    return out.getvalue()


# ---- Page --------------------------------------------------------------------------

st.title("🔍 Alcohol Label Verifier")
st.caption("Compares a label image with its application and checks the Government Warning. "
           "Images are processed in memory and never stored.")
one, many = st.tabs(["Check one label", "Check many labels"])
with one:
    single_label_tab()
with many:
    batch_tab()
