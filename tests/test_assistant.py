from app import assistant


def test_faq_answers_without_key(monkeypatch):
    monkeypatch.setenv("INTAKELY_USE_LLM", "0")
    assert "8" in assistant.answer("how does it work for a patient?")["answer"]
    assert "DR-1001" in assistant.answer("how do doctors sign in")["answer"]


def test_medical_and_emergency_are_rules(monkeypatch):
    monkeypatch.setenv("INTAKELY_USE_LLM", "0")
    r = assistant.answer("what dose of paracetamol should i take")
    assert r["source"] == "rule" and "doctor" in r["answer"].lower()
    r = assistant.answer("I have chest pain")
    assert r["source"] == "rule" and "108" in r["answer"]


def test_off_topic(monkeypatch):
    monkeypatch.setenv("INTAKELY_USE_LLM", "0")
    assert "only help" in assistant.answer("who won the cricket match")["answer"]
