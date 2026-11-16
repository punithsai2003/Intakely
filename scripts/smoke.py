"""End-to-end check against a running server:  python scripts/smoke.py http://127.0.0.1:8000"""
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def call(path, body=None, token=None):
    req = urllib.request.Request(BASE + "/api/" + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


ok = True
def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


s, h = call("health"); check("health", s == 200)
s, docs = call("doctors"); check("3 doctors listed, no PIN leaked", s == 200 and len(docs) == 3 and "pin_hash" not in json.dumps(docs))

s, st = call("intake/start", {"doctor_id": "DR-1001", "lang": "hi", "name": "Test Patient", "age": 40})
sid = st["session_id"]; check("start in Hindi", s == 200 and "डॉक्टर" in st["step"]["question"])
answers = ["Chest pain on exertion", "2 weeks", "7", ["Breathlessness"], "Ecosprin 75 mg once daily", "None", "Diabetes", "Nothing else"]
urgent = None
for a in answers:
    s, r = call("intake/answer", {"session_id": sid, "answer": a})
    if s != 200: print(s, r); break
    urgent = urgent or r.get("urgent_message")
check("completed intake", r.get("done") is True)
check("urgent message shown (Hindi, fixed text)", urgent and "108" in urgent)
s, r = call("intake/answer", {"session_id": sid, "answer": "x"}); check("answering a finished session is rejected", s == 404)
s, st2 = call("intake/start", {"doctor_id": "DR-1001", "lang": "en", "name": "B", "age": 1})
s, r = call("intake/answer", {"session_id": st2["session_id"], "answer": "<script>" * 100}); check("oversized answer rejected", s == 400)

s, r = call("doctor/queue"); check("queue needs login", s == 401)
s, r = call("doctor/login", {"id": "DR-1001", "pin": "0000"}); check("wrong PIN rejected", s == 401)
s, r = call("doctor/login", {"id": "dr-1001", "pin": "4821"}); check("login works, ID case-insensitive", s == 200)
tok = r["token"]
s, q = call("doctor/queue", token=tok)
names = [c["name"] for c in q]
check("own patients only, new case first-urgent", s == 200 and "Test Patient" in names and "Ravi S." not in names and q[0]["urgency"] == "urgent")
cid = next(c["id"] for c in q if c["name"] == "Test Patient")
s, c = call("doctor/case/" + cid, token=tok)
check("case detail has flags + passing checks", s == 200 and c["flags"][0]["id"] == "RF01" and all(x["ok"] for x in c["checks"]))
s, r = call("doctor/login", {"id": "DR-1002", "pin": "7305"}); tok2 = r["token"]
s, r = call("doctor/case/" + cid, token=tok2); check("another doctor cannot open this case", s == 404)
s, r = call("doctor/case/" + cid + "/hpi", {"text": c["hpi"].replace("14 days", "9 days")}, tok)
check("edit with wrong number blocks approval", s == 200 and not all(x["ok"] for x in r["checks"]))
s, r = call("doctor/case/" + cid + "/approve", {}, tok); check("approve refused while check fails", s == 409)
s, r = call("doctor/case/" + cid + "/hpi", {"text": c["hpi"]}, tok)
s, r = call("doctor/case/" + cid + "/approve", {}, tok); check("approve works after fix", s == 200 and r["status"] == "approved")
check("audit log has 3+ entries", len(r["audit"]) >= 3)

# ---- day plan ----
s, q = call("doctor/queue", token=tok)
ids = [c["id"] for c in q]
s, r = call("doctor/plan", {"start": "09:30", "items": [{"id": i, "minutes": 20} for i in reversed(ids)]}, tok); check("save day plan", s == 200)
s, q2 = call("doctor/queue", token=tok); check("queue follows plan order", [c["id"] for c in q2] == list(reversed(ids)) and q2[0]["plan_order"] == 1 and q2[0]["plan_minutes"] == 20)
s, r = call("doctor/plan", token=tok); check("plan start time stored", r.get("start") == "09:30")
s, r = call("doctor/plan", {"start": "9:5", "items": []}, tok); check("bad start time rejected", s == 400)
s, r = call("doctor/plan", {"start": "10:00", "items": [{"id": "not-mine", "minutes": 20}]}, tok); check("foreign patient in plan rejected", s == 400)
s, r = call("doctor/plan", {"start": "10:00", "items": [{"id": ids[0], "minutes": 3}]}, tok); check("too-short slot rejected", s == 400)

# ---- contact form ----
good = {"first_name": "Asha", "last_name": "K", "email": "asha@example.com", "phone": "", "org": "", "message": "Hello, can I try this in my clinic?"}
s, r = call("contact", good); check("contact message accepted", s == 200 and r.get("ok"))
s, r = call("contact", {**good, "email": "nope"}); check("bad email rejected", s == 400)
s, r = call("contact", {**good, "message": ""}); check("empty message rejected", s == 400)
for _ in range(6): s, r = call("doctor/login", {"id": "DR-1003", "pin": "1111"})
check("lockout after repeated bad PINs", s == 429)
print("\nALL PASSED" if ok else "\nSOME FAILED"); sys.exit(0 if ok else 1)
