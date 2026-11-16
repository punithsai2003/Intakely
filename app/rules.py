"""Deterministic logic: parsing, red-flag screening, summary template, faithfulness check.
Nothing in this module calls a model. The LLM can only add information on top of it."""
import re
from .content import STEPS, DRUGS, RED_RULES

FREQ = [
    (r"twice|\bbd\b|b\.d|two times", "twice daily"),
    (r"once|\bod\b|o\.d|daily|every day", "once daily"),
    (r"thrice|\btds\b|three times", "three times daily"),
    (r"at night|bedtime", "at night"),
    (r"morning", "morning"),
    (r"when needed|sos|if needed|as needed", "as needed"),
]


def parse_duration(text):
    s = str(text or "").lower()
    if "yesterday" in s:
        return 1
    if "couple of days" in s:
        return 2
    if re.search(r"(\d+)\s*(hour|hr)", s):
        return 1
    for pat, mult in ((r"(\d+)\s*(day|days)\b", 1), (r"(\d+)\s*(week|weeks|wk)", 7), (r"(\d+)\s*(month|months)", 30)):
        m = re.search(pat, s)
        if m:
            return int(m.group(1)) * mult
    if re.search(r"\b(a|one)\s+week\b", s):
        return 7
    if re.search(r"\b(a|one)\s+month\b", s):
        return 30
    return None  # vague input stays unknown, never guessed


def parse_meds(text):
    s = str(text or "").strip()
    if not s or re.match(r"^(none|no|nil|nothing|not taking)\b", s, re.I):
        return {"list": [], "unrecognised": []}
    out, unrec = [], []
    for seg in [x.strip() for x in re.split(r"[,;]|\band\b", s, flags=re.I) if x.strip()]:
        low = seg.lower()
        hit = next((d for d in DRUGS if d[0] in low), None)
        if not hit:
            unrec.append(seg)
            continue
        dose, assumed = None, False
        m = re.search(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g)\b", low)
        if m:
            dose = f"{m.group(1)} {m.group(2)}"
        else:
            m = re.search(r"\b(\d{2,4})\b", low)
            if m:
                dose, assumed = f"{m.group(1)} mg", True
        freq = next((label for pat, label in FREQ if re.search(pat, low)), None)
        if not any(x["generic"] == hit[1] for x in out):
            out.append({"generic": hit[1], "said": seg, "dose": dose, "assumed": assumed, "freq": freq})
    return {"list": out, "unrecognised": unrec}


def parse_allergies(text):
    s = str(text or "").strip().lower()
    if not s or re.match(r"^(none|no|nil|nothing|koi nahi)\b", s):
        return []
    if re.search(r"(not sure|don'?t know|unsure|pata nahi)", s):
        return "unknown"
    s = re.sub(r"^allergic to\s+", "", s)
    items = [x.strip() for x in re.split(r"[,;]|\band\b", s) if x.strip()]
    return list(dict.fromkeys(items))


def screen_red(answers, severity=0, extra_distress=False):
    """Rules only ever add flags. A model second screen can add RF99, never remove anything."""
    flags = []
    for i, ans in enumerate(answers):
        txt = ", ".join(ans) if isinstance(ans, list) else str(ans)
        for rid, label, pat in RED_RULES:
            m = re.search(pat, txt, re.I)
            if m and not any(f["id"] == rid for f in flags):
                flags.append({"id": rid, "label": label, "trigger": m.group(0), "step": STEPS[i]["id"]})
    if severity >= 9:
        flags.append({"id": "RF09", "label": "Severity 9 or 10", "trigger": f"{severity}/10", "step": "severity"})
    if extra_distress:
        flags.append({"id": "RF99", "label": "Possible distress (model second screen)", "trigger": "see answers", "step": "other"})
    return flags


def _quote_ok(quote, text):
    return bool(quote) and quote.strip().lower() in str(text).lower()


def merge_analysis(answers, meds, days, allergies, analysis):
    """Merge validated model output into rule output. Every model item needs a quote that really
    appears in the patient's own answer, otherwise it is dropped."""
    if analysis is None:
        return meds, days, allergies, False
    if days is None and analysis.duration_days is not None and _quote_ok(analysis.duration_quote, answers[1]):
        days = analysis.duration_days
    known = {m["generic"] for m in meds["list"]}
    added_quotes = []
    for m in analysis.medicines:
        g = m.generic.strip().lower()
        if g and g not in known and _quote_ok(m.quote, answers[4]):
            meds["list"].append({"generic": g, "said": m.quote, "dose": m.dose, "assumed": False, "freq": m.frequency})
            known.add(g)
            added_quotes.append(m.quote.strip().lower())
    # a segment the rules could not read is no longer "unrecognised" once a verified model item covers it
    meds["unrecognised"] = [u for u in meds["unrecognised"] if not any(q in u.lower() or u.lower() in q for q in added_quotes)]
    if allergies == "unknown" and not analysis.allergies_unknown:
        good = [a.name.strip().lower() for a in analysis.allergies if _quote_ok(a.quote, answers[5])]
        if good:
            allergies = good
    return meds, days, allergies, bool(analysis.distress)


def run_pipeline(answers, analysis=None):
    try:
        sev = int(str(answers[2]))
    except (ValueError, TypeError):
        sev = 0
    days = parse_duration(answers[1])
    meds = parse_meds(answers[4])
    allergies = parse_allergies(answers[5])
    meds, days, allergies, distress = merge_analysis(answers, meds, days, allergies, analysis)
    flags = screen_red(answers, sev, distress)
    unknowns = []
    if days is None:
        unknowns.append(f'Duration not stated clearly: "{answers[1]}"')
    if allergies == "unknown":
        unknowns.append("Patient unsure about allergies")
    unknowns += [f'Medicine not recognised: "{u}"' for u in meds["unrecognised"]]
    urgency = "urgent" if flags else ("review" if unknowns or sev >= 7 else "routine")
    return {"complaint": str(answers[0]).strip(), "duration_raw": answers[1], "days": days, "severity": sev,
            "assoc": answers[3] or [], "meds": meds, "allergies": allergies, "history": answers[6],
            "other": answers[7], "flags": flags, "unknowns": unknowns, "urgency": urgency}


def med_line(m):
    return m["generic"] + (f" {m['dose']}" if m.get("dose") else "") + (f", {m['freq']}" if m.get("freq") else "") + (" (unit assumed)" if m.get("assumed") else "")


def build_hpi(r):
    c = r["complaint"].rstrip(". ")
    c = c[:1].lower() + c[1:]
    dur = " (duration not stated clearly)" if r["days"] is None else f" for about {r['days']} {'day' if r['days'] == 1 else 'days'}"
    assoc = ", ".join(x.lower() for x in r["assoc"]) or "none reported"
    return f"Patient reports {c}{dur}, with severity {r['severity']}/10. Associated symptoms reported: {assoc}."


def faithfulness(r, hpi):
    allowed = {"10", str(r["severity"])}
    if r["days"] is not None:
        allowed.add(str(r["days"]))
    allowed |= {m["dose"].split()[0] for m in r["meds"]["list"] if m.get("dose")}
    nums = re.findall(r"\d+(?:\.\d+)?", hpi)
    bad_nums = [n for n in nums if n not in allowed]
    # position-aware: a number must also sit in the right role, not just exist somewhere in the record
    m = re.search(r"(?:for|about|over)\s+(?:about\s+)?(\d+)\s+days?", hpi, re.I)
    if m and str(r["days"]) != m.group(1) and m.group(1) not in bad_nums:
        bad_nums.append(m.group(1))
    m = re.search(r"severity\s+(\d+)\s*/\s*10", hpi, re.I)
    if m and str(r["severity"]) != m.group(1) and m.group(1) not in bad_nums:
        bad_nums.append(m.group(1))
    known = {m["generic"] for m in r["meds"]["list"]}
    low = hpi.lower()
    bad_meds = sorted({g for b, g in DRUGS if (b in low or g in low) and g not in known})
    diag = re.search(r"(diagnos|suffers from|likely|probably|consistent with|viral|infection)", hpi, re.I)
    return [
        {"ok": not bad_nums, "text": f"Number not in the record: {', '.join(bad_nums)}" if bad_nums else f"All {len(nums)} numbers match the patient's answers."},
        {"ok": not bad_meds, "text": f"Medicine not in the record: {', '.join(bad_meds)}" if bad_meds else "No medicines outside the patient's list."},
        {"ok": not diag, "text": f'Diagnostic or reassuring wording: "{diag.group(0)}"' if diag else "Wording stays descriptive, with no diagnosis."},
    ]
