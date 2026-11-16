/* Intakely front end. Edit CONFIG below to personalise the site. */
const CONFIG = {
  builder: '',   // e.g. "Intakely was built by Your Name, a Bioinformatics and Data Science student, as a project to ..."
  email: '',     // shown in the Contact section if set
  linkedin: ''   // full LinkedIn profile URL, shown in the Contact section if set
};

const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const S = { token: null, doctor: null, lang: 'en', alert: null };
try { S.token = sessionStorage.getItem('tok'); S.doctor = JSON.parse(sessionStorage.getItem('doc') || 'null'); } catch (e) {}

async function api(path, body, method) {
  const h = { 'Content-Type': 'application/json' };
  if (S.token) h.Authorization = 'Bearer ' + S.token;
  const r = await fetch('/api/' + path, { method: method || (body ? 'POST' : 'GET'), headers: h, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(j.error || 'Something went wrong. Please try again.'); e.status = r.status; throw e; }
  return j;
}

/* ---------- site: copy from CONFIG, menu, scroll highlight ---------- */
$('#yr').textContent = new Date().getFullYear();
$('#builder').textContent = CONFIG.builder ||
  'Intakely was built by a student with a background in Bioinformatics and Data Science, as a project to explore how AI can responsibly support healthcare. The aim is to reduce the paperwork doctors carry, not to take decisions out of their hands.';
(function () {
  const parts = [];
  if (CONFIG.email) parts.push('Email: ' + CONFIG.email);
  const el = $('#contactline'); el.textContent = parts.join(' ');
  if (CONFIG.linkedin) { const a = document.createElement('a'); a.href = CONFIG.linkedin; a.target = '_blank'; a.rel = 'noopener'; a.textContent = 'LinkedIn'; el.append(parts.length ? ' · ' : '', a); }
})();
$('#burger').onclick = () => { const o = $('#links').classList.toggle('open'); $('#burger').setAttribute('aria-expanded', o); };
$('#links').onclick = e => { if (e.target.closest('a')) { $('#links').classList.remove('open'); $('#burger').setAttribute('aria-expanded', false); } };
const SECTIONS = ['home', 'about', 'patient', 'doctor', 'contact'];
let ticking = false;
function spy() {
  ticking = false; let cur = 'home';
  SECTIONS.forEach(id => { if ($('#' + id).getBoundingClientRect().top <= 140) cur = id; });
  if (innerHeight + scrollY >= document.body.scrollHeight - 4) cur = 'contact';
  document.querySelectorAll('.links a').forEach(a => a.classList.toggle('on', a.dataset.s === cur));
}
addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(spy); } }, { passive: true });
spy();

/* ---------- full-page views ---------- */
function openApp(id) { const el = $('#' + id); el.classList.add('open'); document.body.classList.add('locked'); el.scrollTop = 0; return el; }
function closeApp(id) { $('#' + id).classList.remove('open'); document.body.classList.remove('locked'); }
const brandBar = (mid, acts) => `<div class="app-bar"><div class="brand"><img src="/logo.png" alt="">Intakely</div>${mid || ''}<div class="acts">${acts || ''}</div></div>`;

/* ---------- patient ---------- */
const TXT = {
  en: { next: 'Next', exit: 'Exit', ph: 'Type your answer here', q: 'Question', of: 'of', low: 'No problem', high: 'Worst imaginable', thanks: 'Thank you', back: 'Back to home', pick: 'Please type an answer, or pick one above.' },
  hi: { next: 'अगला', exit: 'बाहर निकलें', ph: 'अपना उत्तर यहाँ लिखें', q: 'प्रश्न', of: '/', low: 'कोई तकलीफ़ नहीं', high: 'सबसे ज़्यादा', thanks: 'धन्यवाद', back: 'होम पर वापस', pick: 'कृपया उत्तर लिखें या ऊपर से चुनें।' },
  te: { next: 'తరువాత', exit: 'నిష్క్రమించు', ph: 'మీ సమాధానం ఇక్కడ రాయండి', q: 'ప్రశ్న', of: '/', low: 'ఇబ్బంది లేదు', high: 'అత్యధికం', thanks: 'ధన్యవాదాలు', back: 'హోమ్‌కు తిరిగి', pick: 'దయచేసి సమాధానం రాయండి లేదా పైన ఎంచుకోండి.' }
};
(async function loadDoctors() {
  try {
    const ds = await api('doctors');
    $('#docs').innerHTML = ds.map(d => `<label><input type="radio" name="doc" value="${esc(d.id)}" data-n="${esc(d.name)}"><span>${esc(d.name)}<small>${esc(d.specialty)}</small></span></label>`).join('') || 'No doctors available yet.';
  } catch (e) { $('#docs').textContent = 'Could not load doctors. Please refresh the page.'; }
})();
$('#pform').onsubmit = async e => {
  e.preventDefault(); const er = $('#perr'); er.textContent = '';
  const name = $('#pname').value.trim(), doc = document.querySelector('input[name=doc]:checked'), age = $('#page').value;
  if (!name) { er.textContent = 'Please enter your name.'; return; }
  if (!doc) { er.textContent = 'Please choose the doctor you are meeting.'; return; }
  S.lang = document.querySelector('input[name=lang]:checked').value; S.alert = null;
  try {
    const r = await api('intake/start', { doctor_id: doc.value, lang: S.lang, name, age: age ? +age : null });
    openApp('app-patient'); showQuestion(r.session_id, r.step, doc.dataset.n);
  } catch (x) { er.textContent = x.message; }
};
function exitPatient() { closeApp('app-patient'); S.alert = null; }
function showQuestion(sid, st, docName) {
  const t = TXT[S.lang], el = $('#app-patient'); let sel = [];
  el.innerHTML = brandBar(`<span class="who">${esc(docName)}</span>`, `<button class="tlink" id="px">${t.exit}</button>`) +
    `<div class="prog"><i style="width:${st.index / st.total * 100}%"></i></div>` +
    (S.alert ? `<div class="alertbar" role="alert">${esc(S.alert)}</div>` : '') +
    `<div class="qwrap"><div class="qcount">${t.q} ${st.index + 1} ${t.of} ${st.total}</div><h1 class="q">${esc(st.question)}</h1><div class="ans" id="ans"></div><div class="err" id="qe" role="alert"></div></div>`;
  $('#px').onclick = exitPatient;
  const zone = $('#ans');
  const send = async v => {
    try { const r = await api('intake/answer', { session_id: sid, answer: v }); if (r.urgent_message) S.alert = r.urgent_message;
      r.done ? showDone(r.message) : showQuestion(sid, r.step, docName); }
    catch (x) { $('#qe').textContent = x.message; }
  };
  if (st.type === 'scale') {
    zone.innerHTML = '<div class="scale">' + Array.from({ length: 11 }, (_, i) => `<button data-v="${i}" aria-label="${i}">${i}</button>`).join('') + `</div><div class="scalenote"><span>0 · ${t.low}</span><span>10 · ${t.high}</span></div>`;
    zone.onclick = e => { const b = e.target.closest('button'); if (b) send(b.dataset.v); };
  } else if (st.type === 'multi') {
    zone.innerHTML = `<div class="hints">${st.options.map(o => `<button class="pick" data-o="${esc(o)}" aria-pressed="false">${esc(o)}</button>`).join('')}</div><div class="next"><button class="btn light" id="nx">${t.next}</button></div>`;
    zone.onclick = e => { const b = e.target.closest('.pick'); if (!b) return; const o = b.dataset.o; sel = sel.includes(o) ? sel.filter(x => x !== o) : sel.concat(o); b.setAttribute('aria-pressed', sel.includes(o)); };
    $('#nx').onclick = () => send(sel.slice());
  } else {
    zone.innerHTML = ((st.hints || []).length ? `<div class="hints">${st.hints.map(h => `<button class="pick" data-h="${esc(h)}">${esc(h)}</button>`).join('')}</div>` : '') +
      `<textarea id="tx" maxlength="500" rows="2" placeholder="${esc(t.ph)}" aria-label="${esc(st.question)}"></textarea><div class="next"><button class="btn light" id="nx">${t.next}</button></div>`;
    zone.onclick = e => { const b = e.target.closest('.pick'); if (b) send(b.dataset.h); };
    const go = () => { const v = $('#tx').value.trim(); v ? send(v) : ($('#qe').textContent = t.pick); };
    $('#nx').onclick = go; $('#tx').onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); go(); } };
    $('#tx').focus({ preventScroll: true });
  }
}
function showDone(msg) {
  const t = TXT[S.lang];
  $('#app-patient').innerHTML = brandBar('', '') + `<div class="prog"><i style="width:100%"></i></div>` + (S.alert ? `<div class="alertbar" role="alert">${esc(S.alert)}</div>` : '') +
    `<div class="qwrap done"><h1>${t.thanks}</h1><p>${esc(msg)}</p><div class="next"><button class="btn light" id="bk">${t.back}</button></div></div>`;
  $('#bk').onclick = () => { exitPatient(); $('#pform').reset(); scrollTo(0, 0); };
}

/* ---------- contact form ---------- */
$('#cform').onsubmit = async e => {
  e.preventDefault(); const m = $('#cmsg'); m.className = 'cmsg'; m.textContent = '';
  const body = { first_name: $('#c1').value.trim(), last_name: $('#c2').value.trim(), email: $('#c3').value.trim(), phone: $('#c4').value.trim(), org: $('#c5').value.trim(), message: $('#c6').value.trim(), website: $('#c7').value };
  if (!body.first_name || !body.email || !body.message) { m.className = 'cmsg bad'; m.textContent = 'Please fill in your first name, email and message.'; return; }
  $('#csend').disabled = true;
  try { await api('contact', body); m.textContent = 'Thank you. Your message has been sent.'; $('#cform').reset(); }
  catch (x) { m.className = 'cmsg bad'; m.textContent = x.message; }
  $('#csend').disabled = false;
};

/* ---------- doctor ---------- */
const RANK = { urgent: 0, review: 1, routine: 2 };
const LBL = { urgent: 'Urgent', review: 'Needs review', routine: 'Routine', reviewed: 'Reviewed' };
const D = { queue: [], plan: [], start: '09:30', defMin: 20, dirty: false, note: '' };

function doctorForm() {
  const f = $('#dform');
  if (!S.token || !S.doctor) return;
  f.innerHTML = `<p style="font-size:20px;font-weight:600;margin-bottom:6px">Signed in as ${esc(S.doctor.name)}</p><p style="opacity:.9;margin-bottom:22px">${esc(S.doctor.specialty)}</p>
    <button class="btn light" type="button" id="dopen">Open dashboard</button> <button class="btn line" type="button" id="dout">Sign out</button>`;
  $('#dopen').onclick = openDashboard; $('#dout').onclick = signOut;
}
function signOut() {
  S.token = null; S.doctor = null; try { sessionStorage.clear(); } catch (e) {}
  closeApp('app-doctor'); location.reload();
}
const dformHTML = $('#dform').innerHTML;
$('#dform').onsubmit = async e => {
  e.preventDefault(); const er = $('#derr'); er.textContent = '';
  if (!$('#did').value.trim() || !$('#dpin').value) { er.textContent = 'Enter your doctor ID and PIN.'; return; }
  try {
    const r = await api('doctor/login', { id: $('#did').value, pin: $('#dpin').value });
    S.token = r.token; S.doctor = r.doctor;
    try { sessionStorage.setItem('tok', r.token); sessionStorage.setItem('doc', JSON.stringify(r.doctor)); } catch (x) {}
    openDashboard();
  } catch (x) { er.textContent = x.message; }
};
doctorForm();

const toMin = hhmm => { const [h, m] = hhmm.split(':').map(Number); return h * 60 + m; };
const fmt = m => { const h = Math.floor(m / 60) % 24, mm = String(m % 60).padStart(2, '0'); return ((h + 11) % 12 + 1) + ':' + mm + ' ' + (h < 12 ? 'am' : 'pm'); };
function slots() {
  let t = toMin(D.start); const out = {};
  D.plan.forEach(p => { out[p.id] = fmt(t) + ' to ' + fmt(t + p.minutes); t += p.minutes; });
  return out;
}
function byId(id) { return D.queue.find(c => c.id === id); }
function suggest() {
  const q = D.queue.slice().sort((a, b) => (a.status === 'approved') - (b.status === 'approved') || RANK[a.urgency] - RANK[b.urgency] || a.created - b.created);
  D.plan = q.map(c => ({ id: c.id, minutes: D.defMin })); D.dirty = true;
}
async function openDashboard() {
  const el = openApp('app-doctor');
  el.innerHTML = brandBar('', '') + '<div class="dwrap"><p>Loading today\'s patients…</p></div>';
  try {
    const [q, p] = await Promise.all([api('doctor/queue'), api('doctor/plan')]);
    D.queue = q; D.start = p.start || '09:30'; D.dirty = false; D.note = '';
    const planned = q.filter(c => c.plan_order != null).sort((a, b) => a.plan_order - b.plan_order).map(c => ({ id: c.id, minutes: c.plan_minutes || 20 }));
    const rest = q.filter(c => c.plan_order == null).sort((a, b) => RANK[a.urgency] - RANK[b.urgency]).map(c => ({ id: c.id, minutes: D.defMin }));
    D.plan = planned.concat(rest); if (rest.length) D.dirty = true;
    drawDashboard();
  } catch (e) { if (e.status === 401) signOut(); else el.innerHTML = brandBar() + `<div class="dwrap"><p>${esc(e.message)}</p></div>`; }
}
function drawDashboard() {
  const el = $('#app-doctor'), sl = slots();
  const today = new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' });
  const urgent = D.queue.filter(c => c.urgency === 'urgent' && c.status !== 'approved').length;
  const total = D.plan.reduce((a, p) => a + p.minutes, 0);
  const rows = D.plan.map((p, i) => {
    const c = byId(p.id), k = c.status === 'approved' ? 'reviewed' : c.urgency, isNew = c.plan_order == null;
    return `<li class="prow"><span class="n">${i + 1}</span>
      <div class="who"><b>${esc(c.name)}${c.age != null ? ', ' + c.age : ''}</b><span>${esc(c.complaint)}</span></div>
      <div><span class="pill ${k}">${LBL[k]}</span>${isNew ? ' <span class="newtag">New</span>' : ''}</div>
      <div class="slot">${sl[p.id].split(' to ')[0]}<small>to ${sl[p.id].split(' to ')[1]}</small></div>
      <select data-m="${p.id}" aria-label="Minutes for ${esc(c.name)}">${[10, 15, 20, 30, 45, 60].map(m => `<option value="${m}" ${m === p.minutes ? 'selected' : ''}>${m} min</option>`).join('')}</select>
      <div class="mv"><button data-up="${i}" aria-label="Move ${esc(c.name)} earlier" ${i === 0 ? 'disabled' : ''}>Earlier</button><button data-dn="${i}" aria-label="Move ${esc(c.name)} later" ${i === D.plan.length - 1 ? 'disabled' : ''}>Later</button><button class="open-btn" data-open="${c.id}">Open</button></div></li>`;
  }).join('');
  el.innerHTML = brandBar(`<span class="who">${esc(S.doctor.name)} · ${esc(S.doctor.specialty)}</span>`,
      '<button class="tlink" id="dback">Back to site</button><button class="tlink" id="dout2">Sign out</button>') +
    `<div class="dwrap"><h1>Today's patients</h1>
      <p class="sub">${today} · ${D.plan.length} patient${D.plan.length === 1 ? '' : 's'}${urgent ? ' · ' + urgent + ' urgent' : ''}${D.plan.length ? ' · ' + (total < 60 ? total + ' min' : Math.floor(total / 60) + ' h' + (total % 60 ? ' ' + total % 60 + ' min' : '')) + ' planned' : ''}</p>
      <div class="plan">
        <div><label class="fl" for="pstartt">First patient at</label><input type="time" id="pstartt" value="${D.start}"></div>
        <div><label class="fl" for="pdef">Usual time each</label><select id="pdef">${[10, 15, 20, 30].map(m => `<option value="${m}" ${m === D.defMin ? 'selected' : ''}>${m} min</option>`).join('')}</select></div>
        <button class="btn line" id="psug">Put urgent first</button>
        <button class="btn light" id="psave">Start day</button>
        <span class="ok" id="pnote">${D.dirty ? 'Plan not saved yet.' : esc(D.note)}</span>
      </div>
      ${D.plan.length ? `<ol class="plist">${rows}</ol>` : '<p class="empty">No patients have submitted their details yet.</p>'}
    </div>`;
  $('#dback').onclick = () => { closeApp('app-doctor'); document.getElementById('doctor').scrollIntoView(); };
  $('#dout2').onclick = signOut;
  $('#pstartt').onchange = e => { if (e.target.value) { D.start = e.target.value; D.dirty = true; drawDashboard(); } };
  $('#pdef').onchange = e => { D.defMin = +e.target.value; };
  $('#psug').onclick = () => { suggest(); drawDashboard(); };
  $('#psave').onclick = async () => {
    try { await api('doctor/plan', { start: D.start, items: D.plan }); D.dirty = false; D.plan.forEach((p, i) => { const c = byId(p.id); if (c) c.plan_order = i + 1; }); D.note = 'Saved. First patient at ' + fmt(toMin(D.start)) + '.'; drawDashboard(); }
    catch (x) { $('#pnote').textContent = x.message; }
  };
  el.querySelectorAll('[data-m]').forEach(s => s.onchange = () => { D.plan.find(p => p.id === s.dataset.m).minutes = +s.value; D.dirty = true; drawDashboard(); });
  el.querySelectorAll('[data-up]').forEach(b => b.onclick = () => { const i = +b.dataset.up;[D.plan[i - 1], D.plan[i]] = [D.plan[i], D.plan[i - 1]]; D.dirty = true; drawDashboard(); });
  el.querySelectorAll('[data-dn]').forEach(b => b.onclick = () => { const i = +b.dataset.dn;[D.plan[i + 1], D.plan[i]] = [D.plan[i], D.plan[i + 1]]; D.dirty = true; drawDashboard(); });
  el.querySelectorAll('[data-open]').forEach(b => b.onclick = () => openCase(b.dataset.open));
}

/* ---------- one patient, as a reading flow ---------- */
async function openCase(id) {
  try { drawCase(await api('doctor/case/' + id)); $('#app-doctor').scrollTop = 0; }
  catch (e) { if (e.status === 401) signOut(); else alert(e.message); }
}
function drawCase(c) {
  const el = $('#app-doctor'), bad = c.checks.some(x => !x.ok), k = c.status === 'approved' ? 'reviewed' : c.urgency;
  const slot = slots()[c.id], pos = D.plan.findIndex(p => p.id === c.id);
  const A = c.answers.map(a => a.value);
  const tags = c.meds.map(m => `<span class="tag">${esc(m)}</span>`).join('') + c.meds_unrecognised.map(m => `<span class="tag unk">Not recognised: ${esc(m)}</span>`).join('');
  const al = c.allergies === 'unknown' ? '<span class="tag unk">Patient unsure</span>' : (c.allergies.length ? c.allergies.map(a => `<span class="tag al">${esc(a)}</span>`).join('') : 'None reported');
  const durUnclear = c.unknowns.some(u => u.startsWith('Duration'));
  const item = (k_, v, note) => `<li><span class="k">${k_}</span><span class="v">${v}</span>${note ? `<span class="note">${note}</span>` : ''}</li>`;
  el.innerHTML = brandBar(`<span class="who">${esc(S.doctor.name)}</span>`, '<button class="tlink" id="cback">Back to today\'s patients</button>') +
    `<div class="case">
      <div class="meta"><span class="pill ${k}">${LBL[k]}</span>${pos >= 0 ? `<span>Patient ${pos + 1} · ${slot || ''}</span>` : ''}</div>
      <h1>${esc(c.name)}${c.age != null ? ', ' + c.age : ''}</h1>
      ${c.flags.length ? `<div class="flagbar">Possible emergency: ${c.flags.map(f => esc(f.label)).join(', ')}<small>The patient was shown a message to call 108. Matched: ${c.flags.map(f => '"' + esc(f.trigger) + '"').join(', ')}</small></div>` : ''}
      <div class="sec"><div class="h">Summary to read first</div>
        <p style="font-size:14px;opacity:.85;margin:8px 0">${c.hpi_source === 'ai' ? 'Drafted by AI and checked against the patient\'s answers.' : 'Generated from a fixed template.'} You can edit it.</p>
        <textarea id="hpi" aria-label="Summary">${esc(c.hpi)}</textarea>
        <div class="actions"><button class="btn line" id="sv">Save edit</button><span class="err" id="er" style="margin:0"></span></div></div>
      ${c.unknowns.length ? `<div class="sec"><div class="h">Needs your attention</div><div style="padding-top:10px">${c.unknowns.map(u => `<span class="tag unk">${esc(u)}</span>`).join('')}</div></div>` : ''}
      <div class="sec"><div class="h">What the patient told us</div>
        <ol class="flow">
          ${item('Why they came', esc(A[0]))}
          ${item('Since when', esc(A[1]), durUnclear ? 'Not clear from the answer. Worth asking.' : '')}
          ${item('How severe', esc(A[2]) + ' out of 10')}
          ${item('Other symptoms', esc(A[3]))}
          ${item('Medicines they take', esc(A[4]), tags ? 'Recorded as: ' + tags : '')}
          ${item('Allergies', esc(A[5]), 'Recorded as: ' + al)}
          ${item('Past and family history', esc(A[6]))}
          ${item('Anything else', esc(A[7]))}
        </ol></div>
      <div class="sec"><div class="h">Check before you review</div>
        <div class="checks" style="padding-top:10px">${c.checks.map(x => `<div class="${x.ok ? '' : 'bad'}">${x.ok ? '✓' : '!'}&nbsp; ${esc(x.text)}</div>`).join('')}</div>
        <div class="actions"><button class="btn light" id="ap" ${bad || c.status === 'approved' ? 'disabled' : ''}>${c.status === 'approved' ? 'Reviewed' : 'Mark as reviewed'}</button></div>
        <p class="help">Reviewed means you have read this summary and any edits are final. Nothing is sent to the patient. It is saved in the activity log, and stays unavailable while the accuracy check fails.</p>
        <details><summary>Activity log</summary>${c.audit.map(a => `<div>${new Date(a.ts * 1000).toLocaleString()} · ${esc(a.actor)} · ${esc(a.action)}</div>`).join('')}</details></div>
    </div>`;
  $('#cback').onclick = openDashboard;
  $('#sv').onclick = async () => { try { drawCase(await api('doctor/case/' + c.id + '/hpi', { text: $('#hpi').value })); } catch (x) { $('#er').textContent = x.message; } };
  $('#ap').onclick = async () => { try { drawCase(await api('doctor/case/' + c.id + '/approve', {})); } catch (x) { $('#er').textContent = x.message; } };
}

/* ---------- help bot ---------- */
(function () {
  const fab = $('#botfab'), box = $('#bot'), log = $('#botlog'), form = $('#botform'), inp = $('#botq');
  const toggle = o => { box.hidden = !o; fab.setAttribute('aria-expanded', o); fab.textContent = o ? 'Hide' : 'Ask Intakely'; if (o) inp.focus(); };
  fab.onclick = () => toggle(box.hidden); $('#botx').onclick = () => toggle(false);
  const add = (t, who) => { const p = document.createElement('p'); p.className = 'm ' + who; p.textContent = t; log.append(p); log.scrollTop = log.scrollHeight; return p; };
  async function ask(q) {
    add(q, 'mine'); const w = add('...', 'fb');
    try { const r = await api('ask', { q }); w.textContent = r.answer; }
    catch (e) { w.textContent = e.message; }
  }
  form.onsubmit = e => { e.preventDefault(); const q = inp.value.trim(); if (q) { inp.value = ''; ask(q); } };
  document.querySelector('.bot-chips').onclick = e => { const b = e.target.closest('button'); if (b) ask(b.textContent); };
})();
