"""Exercises the model path with fake providers. No API keys or network needed."""
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ["INTAKELY_DB"] = os.path.join(tempfile.mkdtemp(), "t2.db")

import pytest  # noqa: E402

from app import llm, rules  # noqa: E402


@pytest.fixture(autouse=True)
def restore_state():
    env, prov, order = dict(os.environ), dict(llm.PROVIDERS), list(llm.ORDER)
    yield
    os.environ.clear(); os.environ.update(env)
    llm.PROVIDERS.clear(); llm.PROVIDERS.update(prov); llm.ORDER[:] = order

MODE = {"hpi": "good"}


class Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.startswith("/down"):
            self.send_response(503); self.end_headers(); return
        system = body["messages"][0]["content"]
        if "convert a patient" in system:
            text = json.dumps({"duration_days": 6, "duration_quote": "since Diwali",
                               "medicines": [{"generic": "telmisartan", "quote": "Telma"},
                                             {"generic": "hydrochlorothiazide", "quote": "Telma-H"},
                                             {"generic": "warfarin", "quote": "warfarin 5 mg"}],
                               "allergies": [], "allergies_unknown": False, "distress": True})
        else:
            text = ("Patient reports tiredness for about 6 days, with severity 4/10." if MODE["hpi"] == "good"
                    else "Patient reports tiredness for about 9 days. Likely a viral infection.")
        out = json.dumps({"choices": [{"message": {"content": text}}]}).encode()
        self.send_response(200); self.end_headers(); self.wfile.write(out)

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 8798), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
ANS = ["Tiredness and low energy", "since Diwali", "4", [], "Telma-H", "None", "High BP", "Nothing else"]


def use(first, second):
    llm.PROVIDERS["gemini"] = ("http://127.0.0.1:8798/" + first, "GEMINI_API_KEY", "m1")
    llm.PROVIDERS["groq"] = ("http://127.0.0.1:8798/" + second, "GROQ_API_KEY", "m2")
    llm.ORDER[:] = ["gemini", "groq"]
    os.environ.update(GEMINI_API_KEY="k1", GROQ_API_KEY="k2", INTAKELY_USE_LLM="1")


def test_fallback_to_second_provider_when_first_is_down():
    use("down", "ok")
    assert llm.enabled() and llm.analyze(ANS) is not None


def test_all_providers_down_falls_back_to_rules():
    use("down", "down")
    assert llm.analyze(ANS) is None
    r = rules.run_pipeline(ANS, llm.analyze(ANS))
    assert r["days"] is None and r["urgency"] == "review"


def test_model_output_is_verified_and_invented_items_dropped():
    use("ok", "ok")
    r = rules.run_pipeline(ANS, llm.analyze(ANS))
    gens = {m["generic"] for m in r["meds"]["list"]}
    assert gens == {"telmisartan", "hydrochlorothiazide"}      # warfarin was invented, quote not in answer
    assert r["days"] == 6
    assert any(f["id"] == "RF99" for f in r["flags"])           # model second screen only adds


def test_hpi_draft_must_pass_faithfulness():
    use("ok", "ok")
    r = rules.run_pipeline(ANS, llm.analyze(ANS))
    MODE["hpi"] = "good"
    assert all(c["ok"] for c in rules.faithfulness(r, llm.write_hpi(r)))
    MODE["hpi"] = "bad"
    assert not all(c["ok"] for c in rules.faithfulness(r, llm.write_hpi(r)))   # main.complete() then uses the template
