"""Read text from a label image with Tesseract (runs locally, no cloud calls)."""
import io

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageOps

TARGET_WIDTH = 1800   # small images are upscaled, huge ones shrunk, for speed and accuracy


class OcrError(Exception):
    """Raised when the image cannot be opened or contains no readable text."""


class OcrReader:
    def read(self, image_bytes: bytes) -> str:
        image = self._load(image_bytes)
        cleaned = self._preprocess(image)
        text = pytesseract.image_to_string(cleaned, config="--psm 3")
        if len(text.strip()) < 10:
            raise OcrError("No readable text found. Try a clearer, closer photo of the label.")
        return text

    @staticmethod
    def _load(image_bytes: bytes) -> np.ndarray:
        try:
            image = Image.open(io.BytesIO(image_bytes))
            image = ImageOps.exif_transpose(image).convert("RGB")   # fix phone rotation
        except Exception as exc:
            raise OcrError("This file isn't an image we can open. Use JPG or PNG.") from exc
        return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)

    @staticmethod
    def _preprocess(gray: np.ndarray) -> np.ndarray:
        """Resize, even out lighting and glare, and sharpen text edges."""
        scale = TARGET_WIDTH / gray.shape[1]
        if not 0.8 < scale < 1.25:
            interpolation = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=interpolation)
        # CLAHE boosts local contrast, which helps with uneven light and glare.
        gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        gray = cv2.medianBlur(gray, 3)
        # Tesseract expects dark text on light background.
        if np.mean(gray) < 110:
            gray = cv2.bitwise_not(gray)
        return gray
