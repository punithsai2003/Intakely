"""Intakely API (Starlette; FastAPI is built on the same core, so routes port over directly)."""
import os
import re
import secrets
import time
from typing import Literal, Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field, ValidationError
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import assistant, db, llm, rules
from .content import DONE_MSG, STEPS, URGENT_MSG

SECRET = os.environ.get("INTAKELY_SECRET") or secrets.token_hex(16)
signer = URLSafeTimedSerializer(SECRET, salt="doctor-session")
TOKEN_TTL = 8 * 3600
FAILS: dict = {}  # doctor id -> (count, first_fail_time)


class StartIn(BaseModel):
    doctor_id: str
    lang: Literal["en", "hi", "te"] = "en"
    name: str = Field(min_length=1, max_length=60)
    age: Optional[int] = Field(default=None, ge=0, le=120)


class AnswerIn(BaseModel):
    session_id: str
    answer: str | list[str]


class LoginIn(BaseModel):
    id: str = Field(max_length=20)
    pin: str = Field(max_length=12)


class PlanItem(BaseModel):
    id: str
    minutes: int = Field(ge=5, le=90)


class PlanIn(BaseModel):
    start: str
    items: list[PlanItem] = Field(max_length=100)


class ContactIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(default="", max_length=60)
    email: str = Field(max_length=120)
    phone: str = Field(default="", max_length=20)
    org: str = Field(default="", max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    website: str = ""  # honeypot: real people leave this empty


class HpiIn(BaseModel):
    text: str = Field(min_length=1, max_length=1500)


async def parse(request: Request, model):
    try:
        return model.model_validate(await request.json())
    except (ValidationError, ValueError):
        raise HTTPException(400, "Invalid request")


def step_payload(i, lang):
    s = STEPS[i]
    return {"index": i, "total": len(STEPS), "id": s["id"], "type": s["type"], "question": s["q"][lang],
            "options": s.get("options"), "hints": s.get("hints")}


def doctor_id_from(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Please log in")
    try:
        return signer.loads(auth[7:], max_age=TOKEN_TTL)["d"]
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "Session expired, please log in again")


def own_case(request: Request, iid: str):
    did = doctor_id_from(request)
    it = db.get_intake(iid)
    if not it or it["doctor_id"] != did or it["status"] == "in_progress":
        raise HTTPException(404, "Case not found")
    return did, it


def complete(iid):
    it = db.get_intake(iid)
    answers = it["answers"]
    analysis = llm.analyze(answers)
    record = rules.run_pipeline(answers, analysis)
    hpi, source = rules.build_hpi(record), "template"
    draft = llm.write_hpi(record)
    if draft and all(c["ok"] for c in rules.faithfulness(record, draft)):
        hpi, source = draft, "ai"
    db.finalize(iid, record, hpi, source)
    db.log(iid, "system", f"Intake submitted ({'AI-assisted' if analysis else 'rules only'})")
    return record


# ---------- patient ----------
async def list_doctors(request):
    return JSONResponse(db.doctors())


async def intake_start(request):
    b = await parse(request, StartIn)
    if not db.doctor(b.doctor_id):
        raise HTTPException(404, "Doctor not found")
    iid = db.new_intake(b.doctor_id, b.name.strip(), b.age, b.lang)
    return JSONResponse({"session_id": iid, "step": step_payload(0, b.lang)})


async def intake_answer(request):
    b = await parse(request, AnswerIn)
    it = db.get_intake(b.session_id)
    if not it or it["status"] != "in_progress":
        raise HTTPException(404, "Session not found")
    i, st = it["step"], STEPS[it["step"]]
    ans = b.answer
    if st["type"] == "scale":
        if not isinstance(ans, str) or not ans.isdigit() or not 0 <= int(ans) <= 10:
            raise HTTPException(400, "Choose a number from 0 to 10")
    elif st["type"] == "multi":
        if not isinstance(ans, list) or any(x not in st["options"] for x in ans):
            raise HTTPException(400, "Invalid choice")
    else:
        if not isinstance(ans, str) or not ans.strip() or len(ans) > 500:
            raise HTTPException(400, "Please type an answer (up to 500 characters)")
        ans = ans.strip()
    answers = it["answers"] + [ans]
    db.save_progress(b.session_id, i + 1, answers)
    padded = answers + [[] if s["type"] == "multi" else "" for s in STEPS[len(answers):]]
    sev = int(padded[2]) if padded[2] != "" else 0
    urgent = bool(rules.screen_red(padded, sev))  # rules only, every answer
    out = {"urgent_message": URGENT_MSG[it["lang"]] if urgent else None}
    if i + 1 < len(STEPS):
        out.update(done=False, step=step_payload(i + 1, it["lang"]))
    else:
        complete(b.session_id)
        doc = db.doctor(it["doctor_id"])
        out.update(done=True, message=DONE_MSG[it["lang"]].format(doctor=doc["name"]))
    return JSONResponse(out)


# ---------- doctor ----------
async def doctor_login(request):
    b = await parse(request, LoginIn)
    did = b.id.strip().upper()
    n, t0 = FAILS.get(did, (0, time.time()))
    if n >= 5 and time.time() - t0 < 60:
        raise HTTPException(429, "Too many attempts. Wait a minute and try again.")
    d = db.check_pin(did, b.pin)
    if not d:
        FAILS[did] = (n + 1, t0 if n else time.time())
        raise HTTPException(401, "Wrong ID or PIN")
    FAILS.pop(did, None)
    return JSONResponse({"token": signer.dumps({"d": d["id"]}), "doctor": {"id": d["id"], "name": d["name"], "specialty": d["specialty"]}})


async def doctor_queue(request):
    did = doctor_id_from(request)
    rank = {"urgent": 0, "review": 1, "routine": 2}
    q = sorted(db.queue(did), key=lambda x: (x["plan_order"] is None, x["plan_order"] or 0,
                                              x["status"] == "approved", rank[x["urgency"]]))
    return JSONResponse(q)


async def doctor_plan_get(request):
    return JSONResponse({"start": db.plan_start(doctor_id_from(request))})


async def doctor_plan_set(request):
    did = doctor_id_from(request)
    b = await parse(request, PlanIn)
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", b.start):
        raise HTTPException(400, "Start time must look like 09:30")
    mine = {c["id"] for c in db.queue(did)}
    ids = [i.id for i in b.items]
    if len(set(ids)) != len(ids) or any(i not in mine for i in ids):
        raise HTTPException(400, "Plan contains an unknown or repeated patient")
    db.set_plan(did, b.start, [(i.id, i.minutes) for i in b.items])
    return JSONResponse({"ok": True})


CONTACT_HITS: dict = {}  # ip -> [timestamps]


async def contact(request):
    b = await parse(request, ContactIn)
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "?"))
    now = time.time()
    hits = [t for t in CONTACT_HITS.get(ip, []) if now - t < 3600]
    if len(hits) >= 5:
        raise HTTPException(429, "Too many messages from this connection. Please try again later.")
    if b.website:                                   # honeypot filled: pretend success, store nothing
        return JSONResponse({"ok": True})
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", b.email.strip()):
        raise HTTPException(400, "Please enter a valid email address")
    CONTACT_HITS[ip] = hits + [now]
    db.add_message(b.first_name.strip(), b.last_name.strip(), b.email.strip(), b.phone.strip(), b.org.strip(), b.message.strip())
    return JSONResponse({"ok": True})


ASK_HITS: dict = {}


class AskIn(BaseModel):
    q: str = Field(min_length=1, max_length=400)


async def ask(request):
    b = await parse(request, AskIn)
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "?"))
    now = time.time()
    hits = [t for t in ASK_HITS.get(ip, []) if now - t < 600]
    if len(hits) >= 20:
        raise HTTPException(429, "Too many questions for now. Please try again in a few minutes.")
    ASK_HITS[ip] = hits + [now]
    return JSONResponse(assistant.answer(b.q))


def case_json(it):
    r = it["record"]
    return {"id": it["id"], "name": it["patient_name"], "age": it["age"], "status": it["status"], "urgency": r["urgency"],
            "complaint": r["complaint"], "hpi": it["hpi"], "hpi_source": it["hpi_source"],
            "meds": [rules.med_line(m) for m in r["meds"]["list"]], "meds_unrecognised": r["meds"]["unrecognised"],
            "allergies": r["allergies"], "history": r["history"], "other": r["other"], "unknowns": r["unknowns"],
            "flags": r["flags"], "checks": rules.faithfulness(r, it["hpi"]),
            "answers": [{"label": s["label"], "value": (", ".join(a) or "none selected") if isinstance(a, list) else a}
                        for s, a in zip(STEPS, it["answers"])],
            "audit": db.audit(it["id"])}


async def doctor_case(request):
    _, it = own_case(request, request.path_params["iid"])
    return JSONResponse(case_json(it))


async def doctor_hpi(request):
    did, it = own_case(request, request.path_params["iid"])
    b = await parse(request, HpiIn)
    db.set_hpi(it["id"], b.text.strip())
    db.log(it["id"], did, "Edited history of present illness")
    return JSONResponse(case_json(db.get_intake(it["id"])))


async def doctor_approve(request):
    did, it = own_case(request, request.path_params["iid"])
    if not all(c["ok"] for c in rules.faithfulness(it["record"], it["hpi"])):
        raise HTTPException(409, "The summary does not match the patient's answers. Fix it before marking it reviewed.")
    db.set_status(it["id"], "approved")
    db.log(it["id"], did, "Marked as reviewed")
    return JSONResponse(case_json(db.get_intake(it["id"])))


async def health(request):
    return JSONResponse({"ok": True, "llm": llm.enabled(), "providers": llm._active()})


async def http_error(request, exc):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


class NoCacheStatic(StaticFiles):
    """Browsers always re-check the site files, so an updated page shows up straight away."""
    async def get_response(self, path, scope):
        r = await super().get_response(path, scope)
        r.headers["Cache-Control"] = "no-cache"
        return r


STATIC = os.path.join(os.path.dirname(__file__), "..", "static")
routes = [
    Route("/api/health", health),
    Route("/api/doctors", list_doctors),
    Route("/api/intake/start", intake_start, methods=["POST"]),
    Route("/api/intake/answer", intake_answer, methods=["POST"]),
    Route("/api/doctor/login", doctor_login, methods=["POST"]),
    Route("/api/doctor/queue", doctor_queue),
    Route("/api/doctor/plan", doctor_plan_get),
    Route("/api/doctor/plan", doctor_plan_set, methods=["POST"]),
    Route("/api/contact", contact, methods=["POST"]),
    Route("/api/ask", ask, methods=["POST"]),
    Route("/api/doctor/case/{iid}", doctor_case),
    Route("/api/doctor/case/{iid}/hpi", doctor_hpi, methods=["POST"]),
    Route("/api/doctor/case/{iid}/approve", doctor_approve, methods=["POST"]),
    Mount("/", NoCacheStatic(directory=STATIC, html=True)),
]


def create_app():
    db.init()
    if os.environ.get("INTAKELY_DEMO_SEED", "1") == "1":
        from .seed import seed
        seed()
    return Starlette(routes=routes, exception_handlers={HTTPException: http_error})


app = create_app()
