"""SQLite storage. Swap the connection for PostgreSQL (psycopg) when you deploy for real."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager

DB_PATH = os.environ.get("INTAKELY_DB", os.path.join(os.path.dirname(__file__), "..", "intakely.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS doctors (id TEXT PRIMARY KEY, name TEXT, specialty TEXT, salt TEXT, pin_hash TEXT);
CREATE TABLE IF NOT EXISTS intakes (
  id TEXT PRIMARY KEY, doctor_id TEXT REFERENCES doctors(id), patient_name TEXT, age INTEGER, lang TEXT,
  step INTEGER DEFAULT 0, answers TEXT DEFAULT '[]', status TEXT DEFAULT 'in_progress',
  record TEXT, hpi TEXT, hpi_source TEXT, created REAL);
CREATE TABLE IF NOT EXISTS day_plan (doctor_id TEXT PRIMARY KEY, start TEXT);
CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, first_name TEXT, last_name TEXT, email TEXT, phone TEXT, org TEXT, message TEXT);
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, intake_id TEXT, ts REAL, actor TEXT, action TEXT);
"""


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)
        cols = {r["name"] for r in c.execute("PRAGMA table_info(intakes)")}
        for col in ("plan_order", "plan_minutes"):     # added later; migrate older databases
            if col not in cols:
                c.execute(f"ALTER TABLE intakes ADD COLUMN {col} INTEGER")


def hash_pin(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 120_000).hex()


def add_doctor(did, name, specialty, pin):
    salt = secrets.token_hex(8)
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO doctors VALUES (?,?,?,?,?)", (did, name, specialty, salt, hash_pin(pin, salt)))


def check_pin(did, pin):
    with conn() as c:
        r = c.execute("SELECT * FROM doctors WHERE id=?", (did.strip().upper(),)).fetchone()
    if not r:
        hash_pin(pin, "x")  # keep timing similar for unknown IDs
        return None
    return dict(r) if hmac.compare_digest(hash_pin(pin, r["salt"]), r["pin_hash"]) else None


def doctors():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT id,name,specialty FROM doctors ORDER BY name")]


def doctor(did):
    with conn() as c:
        r = c.execute("SELECT id,name,specialty FROM doctors WHERE id=?", (did,)).fetchone()
    return dict(r) if r else None


def new_intake(doctor_id, name, age, lang):
    iid = secrets.token_hex(8)
    with conn() as c:
        c.execute("INSERT INTO intakes (id,doctor_id,patient_name,age,lang,created) VALUES (?,?,?,?,?,?)",
                  (iid, doctor_id, name, age, lang, time.time()))
    return iid


def get_intake(iid):
    with conn() as c:
        r = c.execute("SELECT * FROM intakes WHERE id=?", (iid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["answers"] = json.loads(d["answers"])
    d["record"] = json.loads(d["record"]) if d["record"] else None
    return d


def save_progress(iid, step, answers):
    with conn() as c:
        c.execute("UPDATE intakes SET step=?, answers=? WHERE id=?", (step, json.dumps(answers, ensure_ascii=False), iid))


def finalize(iid, record, hpi, source, status="awaiting"):
    with conn() as c:
        c.execute("UPDATE intakes SET status=?, record=?, hpi=?, hpi_source=? WHERE id=?",
                  (status, json.dumps(record, ensure_ascii=False), hpi, source, iid))


def set_hpi(iid, hpi):
    with conn() as c:
        c.execute("UPDATE intakes SET hpi=? WHERE id=?", (hpi, iid))


def set_status(iid, status):
    with conn() as c:
        c.execute("UPDATE intakes SET status=? WHERE id=?", (status, iid))


def queue(doctor_id):
    with conn() as c:
        rows = c.execute("SELECT id,patient_name,age,status,record,created,plan_order,plan_minutes FROM intakes WHERE doctor_id=? AND status!='in_progress' ORDER BY created DESC",
                         (doctor_id,)).fetchall()
    out = []
    for r in rows:
        rec = json.loads(r["record"])
        out.append({"id": r["id"], "name": r["patient_name"], "age": r["age"], "status": r["status"],
                    "urgency": rec["urgency"], "complaint": rec["complaint"], "created": r["created"],
                    "plan_order": r["plan_order"], "plan_minutes": r["plan_minutes"]})
    return out


def log(iid, actor, action):
    with conn() as c:
        c.execute("INSERT INTO audit (intake_id,ts,actor,action) VALUES (?,?,?,?)", (iid, time.time(), actor, action))


def audit(iid):
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT ts,actor,action FROM audit WHERE intake_id=? ORDER BY id DESC", (iid,))]


def set_plan(doctor_id, start, items):
    """items: list of (intake_id, minutes) in the order the doctor will see them."""
    with conn() as c:
        c.execute("UPDATE intakes SET plan_order=NULL, plan_minutes=NULL WHERE doctor_id=?", (doctor_id,))
        for i, (iid, minutes) in enumerate(items, 1):
            c.execute("UPDATE intakes SET plan_order=?, plan_minutes=? WHERE id=? AND doctor_id=?", (i, minutes, iid, doctor_id))
        c.execute("INSERT OR REPLACE INTO day_plan VALUES (?,?)", (doctor_id, start))


def plan_start(doctor_id):
    with conn() as c:
        r = c.execute("SELECT start FROM day_plan WHERE doctor_id=?", (doctor_id,)).fetchone()
    return r["start"] if r else None


def add_message(first, last, email, phone, org, message):
    with conn() as c:
        c.execute("INSERT INTO messages (ts,first_name,last_name,email,phone,org,message) VALUES (?,?,?,?,?,?,?)",
                  (time.time(), first, last, email, phone, org, message))
