# Intakely

Pre-visit intake for clinics, doctor by doctor. The patient picks their doctor and answers a few guided
questions. The doctor signs in with an ID and PIN and sees a short, checked summary.

**Portfolio prototype. Synthetic data only. Not a medical device.** It does not diagnose, advise or reassure.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY=...                  # optional, free key from Google AI Studio
export GROQ_API_KEY=...                    # optional, free key from Groq (used if Gemini fails)
# with no keys at all the site runs on rules only
export INTAKELY_SECRET=$(python -c "import secrets;print(secrets.token_hex(32))")
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000.

Demo doctors (created by `app/seed.py`, remove for any real use):

| ID | Doctor | PIN |
|---|---|---|
| DR-1001 | Dr. Ananya Rao | 4821 |
| DR-1002 | Dr. Vikram Shah | 7305 |
| DR-1003 | Dr. Sana Khan | 2956 |

## The site

One scrolling page: **Home → About us → Patient → Doctor → Contact Us**, with a menu that highlights where you are.

- **Patient:** name, age, language, choose your doctor, START. The eight questions then open full-page, one per screen. A fixed
  emergency message appears if an answer matches a red-flag rule.
- **Doctor:** sign in with ID and PIN, then see today's patients. Set the start time, minutes per patient and order, and press
  *Start day* (the plan is saved). Each patient opens as a reading flow: summary first, then the patient's own answers under clear
  sub-headings, an accuracy check, and *Mark as reviewed*.
- **Contact:** messages are stored in the database. Read them with `python scripts/show_messages.py`. No email is sent.
- **Help bot:** the "Ask Intakely" button answers questions about the site from a fixed FAQ in `app/assistant.py` (edit it there). With a free Gemini/Groq key the model words the answer from that FAQ only; without a key the best FAQ entry is shown. Medical questions and emergency words get fixed replies, never model output.
- Background tint strength is the last two hex digits in `static/style.css` (`#ADD8E620`; `FF` is solid).
- Personalise the About and Contact text in the `CONFIG` block at the top of `static/app.js`.

## Where the LLM is used, and where it is not

| Step | Who does it |
|---|---|
| Choosing and wording questions, 3 languages | Fixed text in `app/content.py` |
| Red-flag screening and the urgent message | Rules only (`app/rules.py`). The model may *add* a flag (RF99), never remove one |
| Reading free text into fields (duration, medicines, allergies) | Model (Gemini, then Groq if Gemini fails), as JSON validated by Pydantic. Each item must **quote the patient's own words**; items whose quote is not in the answer are dropped |
| Writing the HPI paragraph | Model drafts it. A deterministic faithfulness check must pass or the template text is used |
| Marking a summary reviewed | Doctor only, and blocked while the accuracy check fails. It means "I have read this"; nothing is sent to the patient |

Without an API key the same pipeline runs on rules only, so the site always works.

## Security notes

- Doctor PINs are salted PBKDF2 hashes. Sessions are signed tokens (8 h). 5 wrong PINs lock that ID for 1 minute.
- A doctor can only open their own patients' cases. Patient answers are length-limited and validated per question type.
- Patient text is treated as untrusted input to the model (prompt-injection guard in the system prompt, JSON-only output, quote check).
- Before real use: HTTPS, a real identity system, DPDP Act compliance (consent, retention, access logs), PostgreSQL instead of SQLite, rate limiting at the proxy, and clinical validation.

## Deploy for free (Hugging Face Spaces)

1. Create a new Space, choose **Docker**, free CPU. Upload this repo (the `Dockerfile` is included).
2. In Space settings, add secrets: `INTAKELY_SECRET`, and optionally `GEMINI_API_KEY` and `GROQ_API_KEY`.
3. The app starts on port 7860. Contact messages live in the same SQLite file, so on a free Space they are lost on restart; use an email service or persistent storage for real use.
    Free Spaces sleep when idle and the SQLite file resets on restart; the seeded
   demo doctors and synthetic patients come back each time, which is fine for a showcase.
Render's free web service works too (Docker, same secrets). Free tiers change, so check current limits.

## Tests

```bash
pytest -q                                   # 16 tests: rules, quote checks, faithfulness, provider fallback (fake providers, no keys)
uvicorn app.main:app --port 8000 &          # then:
python scripts/smoke.py http://127.0.0.1:8000   # end-to-end checks incl. auth, lockout, day plan, contact form
```

## Known limits (measured on synthetic cases, not clinical claims)

- Rules do not read durations like "2 din se" or "since Diwali", or combination brands like "Telma-H"
  (the model path can recover these when a key is set; the quote check keeps it honest, and the tests prove it with fake providers).
- Indirect distress wording ("I feel like a burden") is missed by rules alone. With a key, the model second screen
  adds RF99 for the doctor. This has not been evaluated on a labelled set. Build one before relying on it.
- The medicine list is small and hand-made. Extend `DRUGS` in `app/content.py`.
- Hindi and Telugu question text should be reviewed by a native speaker and a clinician.

## Layout

```
app/content.py   questions, messages, drug list, red-flag rules
app/rules.py     parsing, red flags, summary template, faithfulness check
app/llm.py       Gemini/Groq calls with fallback + Pydantic validation (only file that touches a model)
app/db.py        SQLite (swap for PostgreSQL)    app/main.py  API    app/seed.py  demo data
static/          the website (index.html, style.css, app.js, logo.png, stethoscope.png)
tests/, scripts/smoke.py
```
