# Label Verifier

A web app that checks alcohol label images against their application data.

**Live app:** `https://label-verifier-7qpf9j97k37uawks5etqch.streamlit.app/`

## Setup

```bash
brew install tesseract            # Ubuntu: sudo apt-get install tesseract-ocr
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

## Test

```bash
pytest
```

## Regenerate sample labels

```bash
python sample_labels/make_sample_labels.py
```