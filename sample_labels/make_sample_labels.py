"""Generate the sample label images and applications.csv used for testing.

Run:  python sample_labels/make_sample_labels.py
Each label is designed to exercise one scenario (see SCENARIOS below).
"""
import csv
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).parent
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
WARNING_BODY = (
    "(1) According to the Surgeon General, women should not drink alcoholic "
    "beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car "
    "or operate machinery, and may cause health problems."
)

# filename -> (what is printed on the label, what the application says, notes)
SCENARIOS = {
    "01_old_tom_bourbon_pass.png": dict(
        label=dict(brand="OLD TOM DISTILLERY", type="Kentucky Straight Bourbon Whiskey",
                   abv="45% Alc./Vol. (90 Proof)", net="750 mL"),
        app=dict(brand_name="OLD TOM DISTILLERY",
                 class_type="Kentucky Straight Bourbon Whiskey",
                 alcohol_content="45% Alc./Vol. (90 Proof)", net_contents="750 mL"),
    ),
    "02_stones_throw_case_difference_pass.png": dict(
        label=dict(brand="STONE'S THROW", type="London Dry Gin",
                   abv="47% Alc./Vol. (94 Proof)", net="1 LITER"),
        app=dict(brand_name="Stone's Throw", class_type="London Dry Gin",
                 alcohol_content="47%", net_contents="1000 mL"),
    ),
    "03_titlecase_warning_fail.png": dict(
        label=dict(brand="RIVER BEND", type="Straight Rye Whiskey",
                   abv="50% Alc./Vol. (100 Proof)", net="750 mL",
                   heading="Government Warning:"),
        app=dict(brand_name="River Bend", class_type="Straight Rye Whiskey",
                 alcohol_content="50%", net_contents="750 mL"),
    ),
    "04_wrong_abv_fail.png": dict(
        label=dict(brand="HARBOR LIGHT", type="Spiced Rum",
                   abv="40% Alc./Vol. (80 Proof)", net="750 mL"),
        app=dict(brand_name="Harbor Light", class_type="Spiced Rum",
                 alcohol_content="45%", net_contents="750 mL"),
    ),
    "05_altered_warning_fail.png": dict(
        label=dict(brand="BLUE MESA", type="Blanco Tequila",
                   abv="40% Alc./Vol. (80 Proof)", net="750 mL",
                   body=WARNING_BODY.replace("should not drink", "may want to avoid")),
        app=dict(brand_name="Blue Mesa", class_type="Blanco Tequila",
                 alcohol_content="40%", net_contents="750 mL"),
    ),
    "06_imported_wine_pass.png": dict(
        label=dict(brand="CHATEAU LUMIERE", type="Bordeaux Red Wine",
                   abv="13.5% Alc./Vol.", net="75 cl", country="Product of France"),
        app=dict(brand_name="Chateau Lumiere", class_type="Bordeaux Red Wine",
                 alcohol_content="13.5%", net_contents="750 mL", country_of_origin="France"),
    ),
    "07_tilted_with_glare.png": dict(
        label=dict(brand="OLD TOM DISTILLERY", type="Kentucky Straight Bourbon Whiskey",
                   abv="45% Alc./Vol. (90 Proof)", net="750 mL"),
        app=dict(brand_name="OLD TOM DISTILLERY",
                 class_type="Kentucky Straight Bourbon Whiskey",
                 alcohol_content="45%", net_contents="750 mL"),
        distort=True,
    ),
}


def font(size: int, bold: bool = False, serif: bool = False) -> ImageFont.FreeTypeFont:
    name = ("DejaVuSerif" if serif else "DejaVuSans") + ("-Bold" if bold else "") + ".ttf"
    return ImageFont.truetype(str(FONT_DIR / name), size)


def draw_label(label: dict) -> Image.Image:
    width, height = 1000, 1300
    img = Image.new("RGB", (width, height), (246, 239, 222))
    d = ImageDraw.Draw(img)
    d.rectangle([30, 30, width - 30, height - 30], outline=(60, 40, 20), width=6)

    def centered(y, text, f, fill=(40, 25, 10)):
        w = d.textlength(text, font=f)
        d.text(((width - w) / 2, y), text, font=f, fill=fill)

    centered(120, label["brand"], font(70, bold=True, serif=True), fill=(110, 30, 20))
    centered(260, label["type"], font(40, serif=True))
    centered(420, label["abv"], font(42, bold=True))
    centered(500, label["net"], font(42))
    if label.get("country"):
        centered(580, label["country"], font(36))

    # Government warning: bold heading followed by the body, wrapped.
    heading = label.get("heading", "GOVERNMENT WARNING:")
    body = label.get("body", WARNING_BODY)
    y = 760
    d.text((90, y), heading, font=font(30, bold=True), fill=(0, 0, 0))
    y += 45
    for line in textwrap.wrap(body, width=52):
        d.text((90, y), line, font=font(30), fill=(0, 0, 0))
        y += 40
    return img


def distort(img: Image.Image) -> Image.Image:
    """Simulate a phone photo: slight tilt, uneven light, glare spot, softness."""
    img = img.rotate(4, expand=True, fillcolor=(90, 80, 70))
    w, h = img.size
    glare = Image.new("L", (w, h), 0)
    gd = ImageDraw.Draw(glare)
    gd.ellipse([w * 0.55, h * 0.05, w * 0.95, h * 0.30], fill=150)
    glare = glare.filter(ImageFilter.GaussianBlur(60))
    img = Image.composite(Image.new("RGB", (w, h), (255, 255, 255)), img, glare)
    shade = Image.linear_gradient("L").resize((w, h)).point(lambda v: v // 3)
    img = Image.composite(Image.new("RGB", (w, h), (40, 30, 20)), img, shade)
    return img.filter(ImageFilter.GaussianBlur(1.2))


def main() -> None:
    rows = []
    for filename, s in SCENARIOS.items():
        img = draw_label(s["label"])
        if s.get("distort"):
            img = distort(img)
        img.save(OUT / filename)
        rows.append({"filename": filename, "country_of_origin": "", **s["app"]})

    with open(OUT / "applications.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "brand_name", "class_type",
                                               "alcohol_content", "net_contents",
                                               "country_of_origin"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} labels and applications.csv to {OUT}")


if __name__ == "__main__":
    main()
