"""Demo data: three doctors and a few synthetic patients. Synthetic only. Change or remove before real use."""
from . import db, rules

DOCTORS = [
    ("DR-1001", "Dr. Ananya Rao", "General Medicine", "4821"),
    ("DR-1002", "Dr. Vikram Shah", "Cardiology", "7305"),
    ("DR-1003", "Dr. Sana Khan", "Diabetology", "2956"),
]
SAMPLES = [
    ("DR-1001", "Asha K.", 34, "en", ["Fever and body ache", "since 3 days", "6", ["Fever", "Fatigue"], "Dolo 650 twice a day", "Penicillin", "Thyroid problem", "Nothing else"]),
    ("DR-1001", "Suresh P.", 45, "en", ["Burning in stomach after food", "1 week", "4", ["Nausea"], "Pantop 40 mg before breakfast", "Not sure", "Gastritis two years ago", "Nothing else"]),
    ("DR-1002", "Ravi S.", 58, "en", ["Chest pain when I climb stairs", "2 weeks", "7", ["Breathlessness"], "Ecosprin 75 mg once daily, Telma 40 mg morning", "None", "Diabetes, father had a heart attack", "Nothing else"]),
    ("DR-1003", "Sunita G.", 55, "en", ["High sugar, very thirsty", "10 days", "5", ["Fatigue"], "Glimepiride 2 mg morning, metformin 500 mg twice daily", "Iodine contrast", "Diabetes for 8 years", "Nothing else"]),
]


def seed():
    if db.doctors():
        return
    for d in DOCTORS:
        db.add_doctor(*d)
    for did, name, age, lang, answers in SAMPLES:
        iid = db.new_intake(did, name, age, lang)
        db.save_progress(iid, len(answers), answers)
        rec = rules.run_pipeline(answers)
        db.finalize(iid, rec, rules.build_hpi(rec), "template")
        db.log(iid, "system", "Intake submitted (sample)")
