import os
import tempfile

os.environ["INTAKELY_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["INTAKELY_USE_LLM"] = "0"

from app import llm, rules  # noqa: E402
from app.seed import SAMPLES  # noqa: E402


def base(**kw):
    a = ["Fever", "3 days", "5", [], "None", "None", "None", "Nothing else"]
    for k, v in kw.items():
        a[{"complaint": 0, "dur": 1, "sev": 2, "assoc": 3, "meds": 4, "allergy": 5, "hist": 6, "other": 7}[k]] = v
    return a


def test_duration_parsing_and_unknown():
    assert rules.parse_duration("since yesterday") == 1
    assert rules.parse_duration("2 weeks") == 14
    assert rules.parse_duration("3 months") == 90
    assert rules.parse_duration("since Diwali") is None
    assert rules.parse_duration("2 din se") is None  # known gap, documented in README


def test_meds_brand_to_generic_and_dose():
    m = rules.parse_meds("Dolo 650 twice a day, Ecosprin 75 mg once daily")["list"]
    assert [x["generic"] for x in m] == ["paracetamol", "aspirin"]
    assert m[0]["dose"] == "650 mg" and m[0]["assumed"] and m[0]["freq"] == "twice daily"
    assert rules.parse_meds("BP ki goli")["unrecognised"] == ["BP ki goli"]


def test_allergies():
    assert rules.parse_allergies("None") == []
    assert rules.parse_allergies("Not sure") == "unknown"
    assert rules.parse_allergies("Penicillin and sulfa") == ["penicillin", "sulfa"]


def test_red_flags_fire_and_urgency():
    r = rules.run_pipeline(base(complaint="Chest pain when I climb stairs"))
    assert r["urgency"] == "urgent" and r["flags"][0]["id"] == "RF01"
    assert rules.run_pipeline(base(sev="9"))["flags"][0]["id"] == "RF09"
    assert rules.run_pipeline(base())["urgency"] == "routine"


def test_known_red_flag_gap_without_llm():
    r = rules.run_pipeline(base(other="I feel like a burden and do not want to be here anymore"))
    assert r["flags"] == []  # rules alone miss indirect wording; llm second screen is meant to add RF99


def test_faithfulness_blocks_errors():
    r = rules.run_pipeline(base(meds="Dolo 650 twice a day"))
    ok = rules.build_hpi(r)
    assert all(c["ok"] for c in rules.faithfulness(r, ok))
    bad = ok.replace("3 days", "5 days") + " Patient takes ibuprofen. This is likely a viral infection."
    assert [c["ok"] for c in rules.faithfulness(r, bad)] == [False, False, False]


def test_llm_items_need_real_quotes():
    a = llm.Analysis(medicines=[llm.MedItem(generic="telmisartan", quote="Telma"),
                                llm.MedItem(generic="hydrochlorothiazide", quote="Telma-H"),
                                llm.MedItem(generic="warfarin", quote="warfarin 5 mg")],  # invented, not in answer
                     duration_days=6, duration_quote="since Diwali", distress=True)
    r = rules.run_pipeline(base(dur="since Diwali", meds="Telma-H"), analysis=a)
    gens = {m["generic"] for m in r["meds"]["list"]}
    assert "hydrochlorothiazide" in gens and "warfarin" not in gens
    assert r["days"] == 6
    assert any(f["id"] == "RF99" for f in r["flags"]) and r["urgency"] == "urgent"


def test_llm_disabled_without_key(monkeypatch):
    for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert llm.enabled() is False and llm.analyze(base()) is None


def test_seed_samples_run():
    for _, _, _, _, answers in SAMPLES:
        assert rules.run_pipeline(answers)["urgency"] in {"urgent", "review", "routine"}
