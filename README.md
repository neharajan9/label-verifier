Alcohol Label Verifier

A prototype that checks an alcohol label image against its application data,
the routine matching work TTB compliance agents do by eye today. Claude AI
reads the label. Plain rules check each field. The agent makes the final
decision.

Deployed app: https://label-verifier-7qpf9j97k37uawks5etqch.streamlit.app/

The deployed app is ready to use. No API key or setup is needed to test it.
AI usage is capped at 20 dollars a month. If the cap is reached, the app shows
a clear message. Running it locally needs your own API key (see SETUP).

Approach, tools, assumptions and trade offs: see APPROACH.md


WHAT IT DOES (MAPPED TO THE REQUIREMENTS)

Matches the label to the application
  Brand name, class or type, alcohol content and net contents are required.
  Country of origin (imports) and bottler name and address are checked when
  filled in.

Uses judgment, not just exact matching
  STONE'S THROW on the label matches Stone's Throw in the application.
  45% Alc./Vol. matches 90 Proof. 750 mL matches 75 cl. Close but unclear
  matches go to "Check by eye" instead of failing.

Checks the Government Warning exactly
  The text must match the legal wording word for word. The heading must be
  GOVERNMENT WARNING: in all caps and in bold. Title case is rejected.

Fast
  One AI call per label, usually a few seconds. Large photos are shrunk first.

Handles imperfect photos
  The AI reads labels that are tilted, have glare or poor lighting. If it
  cannot read a label, it says so clearly.

Batch uploads
  Upload many label images plus one CSV file with a row per label. Labels
  are checked 8 at a time, with a progress bar, a summary, and a results
  CSV to download.

Simple to use
  Large text and buttons, three steps, plain words: Matches, Check by eye,
  Likely does not match. A message near the button points to the results.

Safe with untrusted labels
  Text printed on a label cannot instruct the AI. Labels that try are sent
  to a person. See PROMPT INJECTION in APPROACH.md.

Stores nothing
  Images and results are not saved. Images are sent only to the Anthropic API.


REQUIREMENTS

  Python 3.10 or newer (tested on 3.13)
  An Anthropic API key (steps below)
  Network access to api.anthropic.com


SETUP (ONE TIME)

1. Get an Anthropic API key with a 20 dollar limit:

    a. Sign in at https://console.anthropic.com and add credit under Billing.
    b. Go to Settings, then Workspaces, and create a workspace named label-verifier.
    c. Open the workspace, go to Limits, and set the monthly spend limit to 20 dollars.
    d. Go to API Keys and create a key in the label-verifier workspace.
       Copy it. It starts with sk-ant- and is shown only once.

   Use this key only for this app. Any key in that workspace stops working
   for the month once 20 dollars is spent.

2. Get the code and create a Python environment:

    git clone <this repository URL>
    cd label-verifier
    python3 -m venv .venv
    source .venv/bin/activate

   On Windows, activate with: .venv\Scripts\activate

3. Install the packages:

    pip install -r requirements.txt

4. Add the API key:

    cp .streamlit/secrets.toml.example .streamlit/secrets.toml

   Open .streamlit/secrets.toml and replace sk-ant-your-key-here with your key.
   This file is in .gitignore, so the key is never uploaded. Run git status
   to confirm secrets.toml is not listed.

   You can instead set an environment variable:

    export ANTHROPIC_API_KEY="sk-ant-your-key-here"


RUN

    source .venv/bin/activate
    streamlit run app.py

The app opens at http://localhost:8501
Press Control and C in the terminal to stop it.

To try it quickly, click "Load an example label" on the first tab, or tick
"Use the 7 example labels instead" on the batch tab.


BATCH CSV FORMAT

One row per label. The filename must match the image file name.

    filename,brand_name,class_type,alcohol_content,net_contents,country_of_origin,bottler
    old_tom.png,OLD TOM DISTILLERY,Kentucky Straight Bourbon Whiskey,45%,750 mL,,

country_of_origin and bottler can be left blank. A blank template can be
downloaded from the batch tab.


DEPLOY ON STREAMLIT COMMUNITY CLOUD

1. Push the code to GitHub.
2. At https://share.streamlit.io create an app from the repository, with
   app.py as the main file.
3. Open the app Settings, then Secrets, and paste:

    ANTHROPIC_API_KEY = "sk-ant-your-key-here"

4. Save. The app restarts and is ready to use.


TEST

    pytest

The matching rules, warning checks and injection guards run offline. The
tests that read the sample labels call the AI service, so they run only when
ANTHROPIC_API_KEY is set as an environment variable. They also check that a
label is read in under 5 seconds.


SAMPLE LABELS

sample_labels/ holds 7 test labels and their applications.csv: matching
labels, a case difference (STONE'S THROW), a title case warning, a wrong
ABV, altered warning text, an imported wine, and a tilted photo with glare.

To make them again:

    python sample_labels/make_sample_labels.py


PROJECT LAYOUT

    app.py                  the screen (Streamlit)
    verifier/ai_reader.py   sends the image to Claude and checks the answer
    verifier/matchers.py    brand, class, ABV and net contents rules
    verifier/warning.py     Government Warning rules
    verifier/injection.py   spots text aimed at the AI
    verifier/safe_text.py   makes user and label text safe for the page and CSV
    verifier/verifier.py    runs all checks, single label and batch
    tests/                  pytest tests
    sample_labels/          test images and CSV
    APPROACH.md             approach, tools, assumptions, trade offs


PRIVACY

Claude sees only the label image and a fixed reading prompt. It gets no chat
history, no application data, no other files and no tools. Each request
starts fresh. Anthropic does not train on API data by default. The app saves
nothing.
