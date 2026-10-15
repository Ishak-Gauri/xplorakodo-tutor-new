// Student-facing screens: auth, dashboard, placement, practice room, interview, progress, certificate, profile, verify.
import {
  $, $$, api, auth, band, esc, fmtDate, goBack, heatmapHTML, icon, lang, LANGS, loading, meter, navigate, overlay,
  pct, scoreRing, shell, store, t, toast, traceHTML, confirmBox, current,
} from "./core.js";

import { studentNav } from "./learn.js";

const nav = studentNav;
const sk = (s) => t(`sk.${s}`);
let lastTrace = null; // trace of the run that opened the current session

// ======================================================================= auth
function authFrame(formHTML) {
  $("#root").innerHTML = `<div class="auth">
    <section class="auth-art">
      <a class="brand" href="/login"><span class="brand-mark">介</span><span><b>XploraKōdo</b><span>Kaigo Sensei tutor</span></span></a>
      <div>
        <h1>Get ready for caregiving work in Japan.</h1>
        <p>A trilingual tutor that asks, listens and remembers. Practise in English, नेपाली or 日本語, rehearse your visa interview, and earn a certificate employers can verify.</p>
        <div class="auth-points">
          <div>${icon("spark")}<span>An AI router picks each session from your weak spots, so no two students get the same questions.</span></div>
          <div>${icon("db")}<span>Your answers become a learning memory in PostgreSQL + pgvector. The tutor recalls where you struggled before.</span></div>
          <div>${icon("shield")}<span>Signed QR certificate once every topic and the interview proctor are passed.</span></div>
        </div>
      </div>
      <p class="small" style="color:#8299b4">© XploraKōdo</p>
      <div class="auth-kanji" aria-hidden="true">介護</div>
    </section>
    <section class="auth-form"><div class="box">${formHTML}</div></section></div>`;
  document.title = "Sign in · XploraKōdo";
}

function afterLogin(data, next) {
  auth.set(data.token, data.user);
  store.set("xk_lang", data.user.lang);
  const dest = next && next.startsWith("/") && !next.startsWith("//") ? next : data.user.role === "admin" ? "/admin" : "/app";
  navigate(dest, { replace: true });
}

export async function loginPage({ query }) {
  if (auth.user) return navigate(auth.user.role === "admin" ? "/admin" : "/app", { replace: true });
  authFrame(`<h2>Sign in</h2><p class="sub">Students and administrators use the same sign-in.</p>
    <form id="f" novalidate>
      <div class="field"><label class="f" for="em">Email</label><input id="em" type="email" autocomplete="username" required></div>
      <div class="field"><label class="f" for="pw">Password</label><input id="pw" type="password" autocomplete="current-password" required></div>
      <p class="err" id="err" role="alert"></p>
      <button class="btn block lg" id="go">Sign in</button>
    </form>
    <p class="muted" style="margin-top:18px">New student? <a href="/register${query.next ? `?next=${encodeURIComponent(query.next)}` : ""}">Create an account</a></p>
    <div class="demo-box"><b>Demo accounts</b><br>Student: demo@xplorakodo.com / demo1234<br>Admin: the ADMIN_EMAIL and ADMIN_PASSWORD set on the server.
    <div class="row" style="margin-top:8px"><button class="btn ghost sm" id="demo" type="button">Fill student demo</button></div></div>`);
  $("#demo").onclick = () => { $("#em").value = "demo@xplorakodo.com"; $("#pw").value = "demo1234"; };
  $("#f").onsubmit = async (e) => {
    e.preventDefault();
    $("#err").textContent = "";
    $("#go").disabled = true;
    try {
      afterLogin(await api("/auth/login", { method: "POST", body: { email: $("#em").value, password: $("#pw").value } }), query.next);
    } catch (err) { $("#err").textContent = err.message; $("#go").disabled = false; }
  };
}

export async function registerPage({ query }) {
  if (auth.user) return navigate("/app", { replace: true });
  let orgs = [];
  try { orgs = await api("/public/orgs"); } catch { /* optional */ }
  authFrame(`<h2>Create your account</h2><p class="sub">Takes a minute. You can change the language any time.</p>
    <form id="f" novalidate>
      <div class="field"><label class="f" for="nm">Full name</label><input id="nm" type="text" autocomplete="name" required maxlength="80"></div>
      <div class="field"><label class="f" for="em">Email</label><input id="em" type="email" autocomplete="email" required></div>
      <div class="field"><label class="f" for="pw">Password</label><input id="pw" type="password" autocomplete="new-password" minlength="8" required><p class="hint">At least 8 characters.</p></div>
      <div class="grid g2">
        <div class="field"><label class="f" for="lg">Tutor language</label><select id="lg">${LANGS.map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></div>
        <div class="field"><label class="f" for="org">Institute</label><select id="org"><option value="">Independent learner</option>${orgs.map((o) => `<option value="${o.id}">${esc(o.name)}</option>`).join("")}</select></div>
      </div>
      <p class="err" id="err" role="alert"></p>
      <button class="btn block lg" id="go">Create account</button>
    </form>
    <p class="muted" style="margin-top:18px">Already registered? <a href="/login">Sign in</a></p>`);
  $("#f").onsubmit = async (e) => {
    e.preventDefault();
    $("#err").textContent = "";
    if ($("#pw").value.length < 8) { $("#err").textContent = "Password needs at least 8 characters."; return; }
    $("#go").disabled = true;
    try {
      afterLogin(await api("/auth/register", { method: "POST", body: {
        name: $("#nm").value, email: $("#em").value, password: $("#pw").value, lang: $("#lg").value,
        org_id: $("#org").value ? Number($("#org").value) : null } }), query.next || "/app/placement");
    } catch (err) { $("#err").textContent = err.message; $("#go").disabled = false; }
  };
}

// ======================================================================= shared bits
function whyTable(decision) {
  if (!decision || !decision.candidates) return "";
  const titles = decision.titles || {};
  return `<p style="margin-bottom:8px"><span class="formula">L = NB(t) − Σ λk·Ck(t)</span></p>
  <div class="table-wrap"><table class="t why"><thead><tr><th>${esc(t("topic"))}</th><th class="num">${esc(t("mastery"))}</th><th class="num">Gap</th><th class="num">Novelty</th><th class="num">Review</th><th class="num">Cost</th><th class="num">Repeat</th><th class="num">Fit</th><th class="num">L</th></tr></thead><tbody>
  ${decision.candidates.map((c) => `<tr class="${c.topic_id === decision.topic_id ? "pick" : ""}"><td>${esc(c.title || titles[c.topic_id] || c.topic_id)}</td>
    <td class="num">${c.mastery === null ? "–" : pct(c.mastery)}</td><td class="num">${c.gain.gap}</td><td class="num">${c.gain.novelty}</td><td class="num">${c.gain.spacing}</td>
    <td class="num">${c.constraints.cost}</td><td class="num">${c.constraints.repeat}</td><td class="num">${c.constraints.fit}</td><td class="num"><b>${c.L}</b></td></tr>`).join("")}
  </tbody></table></div>`;
}

async function startSession(body, btn) {
  if (btn) btn.disabled = true;
  try {
    const s = await api("/sessions", { method: "POST", body });
    lastTrace = s.trace;
    navigate(`/app/session/${s.session_id}`);
  } catch (e) {
    toast(e.message, true);
    if (btn) btn.disabled = false;
  }
}

function statusBadge(st) {
  return `<span class="badge ${st === "done" ? "ok" : st === "active" ? "" : "plain"}">${esc(t(`st.${st}`))}</span>`;
}

// ======================================================================= dashboard
export async function dashboardPage() {
  const page = shell({ nav: nav(), title: t("dashboard") });
  loading(page);
  const d = await api("/me/dashboard");
  auth.setUser({ ...auth.user, ...d.user });
  const s = d.stats, rec = d.recommendation;
  const active = d.active[0];
  const passedChecks = d.eligibility.checks.filter((c) => c.ok).length;
  page.innerHTML = `
    <div class="page-head"><div><h1>${esc(t("hello", { n: d.user.name.split(" ")[0] }))}</h1><p>${esc(t("hello_sub"))}</p></div></div>
    ${!d.user.level ? `<div class="banner">${icon("file")}<div class="sp"><b>${esc(t("take_place"))}</b><div class="small muted">${esc(t("place_first"))}</div></div><a class="btn" href="/app/placement">${esc(t("take_place"))}</a></div>` : ""}
    ${active ? `<div class="banner"><div class="sp"><b>${esc(t("cont_session"))}</b><div class="small muted">${esc(active.title)}</div></div><a class="btn" href="/app/session/${active.id}">${esc(t("cont"))}</a></div>` : ""}
    <div class="grid g4" style="margin-bottom:16px">
      <div class="stat"><div class="k">${esc(t("level"))}</div><div class="v">${esc(levelLabel(d.user.level))}</div><div class="d">${d.user.level ? esc(nextLevel(d.user.level) ? t("next_target", { l: nextLevel(d.user.level) }) : t("top_level")) + " · " : ""}<a href="/app/placement">${esc(d.user.level ? t("retake") : t("take_place"))}</a></div></div>
      <div class="stat"><div class="k">${esc(t("avg"))}</div><div class="v">${pct(s.avg)}</div>${meter(s.avg)}</div>
      <div class="stat"><div class="k">${esc(t("streak"))}</div><div class="v">${esc(t("days", { n: s.streak }))}</div><div class="d">${s.sessions} sessions</div></div>
      <div class="stat"><div class="k">${esc(t("answers"))}</div><div class="v">${s.answers}</div><div class="d">${s.tokens_today.toLocaleString()} / ${s.budget.toLocaleString()} tokens today</div></div>
    </div>
    <div class="split">
      <div>
        <section class="card">
          <div class="card-head"><h2>${esc(t("rec_title"))}</h2><a href="/app/learn" class="small">${esc(t("pick_own"))}</a></div>
          ${rec && rec.blocked ? `<div class="banner bad"><b>${esc(t("budget_blocked"))}</b><span>${esc(rec.blocked)}</span></div>` : rec ? `
          <div class="row" style="align-items:flex-start">
            <div class="sp"><h3 style="font-size:1.3rem">${esc(rec.title)}</h3><p class="muted" style="margin-top:4px">${esc(t(`reason_${rec.reason}`))}</p></div>
            <button class="btn lg" id="go">${icon("play")}${esc(t("rec_go"))}</button>
          </div>
          <details style="margin-top:14px"><summary class="small" style="cursor:pointer;color:var(--kon);font-weight:600">${esc(t("rec_why"))}</summary><div style="margin-top:10px">${whyTable(rec)}</div></details>` : ""}
        </section>
        <section class="card"><div class="card-head"><div><h2>${esc(t("heat"))}</h2><p>${esc(t("heat_sub"))}</p></div></div>${heatmapHTML(d.heatmap)}</section>
      </div>
      <div>
        <section class="card">
          <div class="card-head"><h2>${esc(t("readiness"))}</h2><span class="badge ${d.eligibility.eligible ? "ok" : "plain"}">${passedChecks}/${d.eligibility.checks.length}</span></div>
          ${meter(passedChecks / d.eligibility.checks.length, d.eligibility.eligible ? "s" : "")}
          <div style="margin-top:10px">${checksHTML(d.eligibility.checks.slice(0, 4))}</div>
          <a class="btn ghost block" style="margin-top:12px" href="/app/certificate">${esc(d.certificate ? t("view_cert") : t("certificate"))}</a>
        </section>
        <section class="card"><div class="card-head"><h2>${esc(t("recent"))}</h2><a href="/app/progress" class="small">${esc(t("progress"))}</a></div>
          ${d.recent.length ? `<div class="stack">${d.recent.slice(0, 6).map((r) => `<a href="/app/session/${r.id}" class="row" style="text-decoration:none;color:inherit">
            <div class="sp"><div style="font-weight:500">${esc(r.title)}</div><div class="small muted">${r.kind === "interview" ? esc(t("interview")) + " · " : ""}${fmtDate(r.created_at)}</div></div>
            ${r.avg_score !== null ? `<span class="badge ${band(r.avg_score) === "s" ? "ok" : band(r.avg_score) === "m" ? "warn" : "bad"}">${pct(r.avg_score)}</span>` : statusBadge(r.status)}</a>`).join("")}</div>`
          : `<p class="muted">${esc(t("none_yet"))}</p>`}
        </section>
      </div>
    </div>`;
  const go = $("#go");
  if (go) go.onclick = () => startSession({ kind: "practice" }, go);
}

const LEVELS = ["Pre-N5", "N5", "N4", "N3", "N2", "N1"];
function levelLabel(l) { return !l ? t("notplaced") : /^N[1-5]$/.test(l) ? `JLPT ${l}` : l; }
function nextLevel(l) { const i = LEVELS.indexOf(l); return i < 0 ? "N5" : LEVELS[i + 1] || null; }

function checksHTML(checks) {
  return checks.map((c) => `<div class="check ${c.ok ? "ok" : "no"}">${icon(c.ok ? "check" : "circle")}<div><div style="font-weight:500">${esc(c.label || ({ placement: t("place_title"), interview: t("interview") }[c.key] || c.key))}</div><div class="small muted">${esc(c.detail)}</div></div></div>`).join("");
}

// ======================================================================= placement
export async function placementPage({ query }) {
  const page = shell({ nav: nav(), title: t("place_title"), back: "/app" });
  const me = auth.user || {};
  if (me.level && !query.start) {
    // Already placed: never start a new attempt just because the page was opened (e.g. with Back).
    page.innerHTML = `<div style="max-width:620px;margin:0 auto"><section class="card" style="text-align:center;padding:36px">
      <h1>${esc(t("place_done", { l: levelLabel(me.level) }))}</h1><p class="muted" style="margin-top:8px">${esc(t("place_first"))}</p>
      <div class="row" style="justify-content:center;margin-top:22px"><a class="btn ghost" href="/app">${esc(t("go_dash"))}</a>
      <button class="btn" id="rt">${esc(t("retake"))}</button></div></section></div>`;
    $("#rt").onclick = () => navigate("/app/placement?start=1", { replace: true });
    return;
  }
  loading(page);
  const test = await api("/placement", { method: "POST" });
  const answers = store.get(`xk_place_${test.attempt_id}`, Array(test.total).fill(null));
  let i = Math.max(0, answers.findIndex((a) => a === null));
  if (i < 0) i = test.total - 1;
  const draw = () => {
    const q = test.questions[i];
    page.innerHTML = `<div style="max-width:720px;margin:0 auto">
      <div class="page-head"><div><h1>${esc(t("place_title"))}</h1><p>${esc(t("qof", { i: i + 1, n: test.total }))} · ${esc(t("diff")[q.difficulty])}</p></div></div>
      <div class="steps">${test.questions.map((_, k) => `<i class="${answers[k] !== null ? "done" : k === i ? "now" : ""}"></i>`).join("")}</div>
      <section class="qcard"><div class="qtext jp">${esc(q.q)}</div>
        <div role="radiogroup" aria-label="${esc(q.q)}">${q.options.map((o, k) => `<button class="opt ${answers[i] === k ? "sel" : ""}" role="radio" aria-checked="${answers[i] === k}" data-k="${k}"><span class="key">${k + 1}</span><span class="jp">${esc(o)}</span></button>`).join("")}</div>
        <p class="err" id="err"></p>
        <div class="row" style="margin-top:8px"><button class="btn ghost" id="prev" ${i === 0 ? "disabled" : ""}>${esc(t("prev"))}</button><span class="sp"></span>
        ${i < test.total - 1 ? `<button class="btn" id="next">${esc(t("next"))}</button>` : `<button class="btn" id="submit">${esc(t("submit_test"))}</button>`}</div>
        <p class="small muted" style="margin-top:12px">Tip: press <span class="kbd">1</span>–<span class="kbd">4</span> to choose, <span class="kbd">Enter</span> to continue.</p>
      </section></div>`;
    $$(".opt", page).forEach((b) => (b.onclick = () => { answers[i] = Number(b.dataset.k); store.set(`xk_place_${test.attempt_id}`, answers); draw(); }));
    $("#prev").onclick = () => { i -= 1; draw(); };
    const nx = $("#next");
    if (nx) nx.onclick = () => { if (answers[i] === null) { $("#err").textContent = t("pick_one"); return; } i += 1; draw(); };
    const sb = $("#submit");
    if (sb) sb.onclick = async () => {
      const missing = answers.findIndex((a) => a === null);
      if (missing >= 0) { i = missing; draw(); $("#err").textContent = t("pick_one"); return; }
      sb.disabled = true;
      try {
        const res = await api(`/placement/${test.attempt_id}`, { method: "POST", body: { answers } });
        store.del(`xk_place_${test.attempt_id}`);
        auth.setUser({ ...auth.user, level: res.level });
        page.innerHTML = `<div style="max-width:620px;margin:0 auto"><section class="card" style="text-align:center;padding:36px">
          ${scoreRing(res.score / res.total)}
          <h1 style="margin-top:14px">${esc(t("place_done", { l: levelLabel(res.level) }))}</h1>
          <p class="muted" style="margin-top:6px">${esc(t("place_score", { s: res.score, n: res.total }))}${res.next_level ? " · " + esc(t("next_target", { l: res.next_level })) : ""}</p>
          <div class="bars" style="text-align:left;max-width:360px;margin:20px auto 0"><div class="small muted">${esc(t("by_level"))}</div>
          ${res.by_level.map((b) => `<div class="b"><span>JLPT ${esc(b.level)}</span>${meter(b.correct / b.total, b.correct * 3 >= b.total * 2 ? "s" : "w")}<span>${b.correct}/${b.total}</span></div>`).join("")}</div>
          <div class="row" style="justify-content:center;margin-top:22px"><a class="btn ghost" href="/app">${esc(t("go_dash"))}</a><button class="btn" id="sp">${esc(t("start_practice"))}</button></div></section></div>`;
        $("#sp").onclick = (e) => startSession({ kind: "practice" }, e.currentTarget);
      } catch (e) { toast(e.message, true); sb.disabled = false; }
    };
  };
  const onKey = (e) => {
    if (e.target.matches("input, textarea, select")) return;
    if (["1", "2", "3", "4"].includes(e.key) && test.questions[i].options[Number(e.key) - 1] !== undefined) {
      answers[i] = Number(e.key) - 1; store.set(`xk_place_${test.attempt_id}`, answers); draw();
    } else if (e.key === "Enter") { ($("#next") || $("#submit"))?.click(); }
  };
  document.addEventListener("keydown", onKey);
  current.cleanup = () => document.removeEventListener("keydown", onKey);
  draw();
}

// ======================================================================= topics
export async function learnPage() {
  const page = shell({ nav: nav(), title: t("learn") });
  loading(page);
  const topics = await api("/topics?kind=practice");
  const lvl = (auth.user || {}).level;
  const card = (tp) => {
    const m = tp.mastery || {};
    const mine = tp.jlpt_level && (tp.jlpt_level === lvl || tp.jlpt_level === nextLevel(lvl));
    return `<article class="topic"><div class="row between"><h3>${esc(tp.title)}</h3>${tp.jlpt_level ? `<span class="badge ${mine ? "" : "plain"}">JLPT ${esc(tp.jlpt_level)}</span>` : `<span class="badge plain">${esc(t("questions_n", { n: tp.questions }))}</span>`}</div>
      <div class="jp-row">${tp.vocab.slice(0, 4).map((v) => esc(v.jp)).join("、")}</div>
      <div><div class="row between small"><span class="muted">${esc(t("mastery"))}</span><span>${m.avg === null || m.avg === undefined ? esc(t("nodata")) : pct(m.avg)}</span></div>${meter(m.avg || 0)}</div>
      <div class="foot"><button class="btn sm" data-topic="${esc(tp.id)}">${icon("play")}${esc(t("start"))}</button>${mine ? `<span class="small muted">${esc(t("your_level"))}</span>` : ""}</div></article>`;
  };
  const care = topics.filter((x) => x.track !== "jlpt"), jlpt = topics.filter((x) => x.track === "jlpt");
  page.innerHTML = `<div class="page-head"><div><h1>${esc(t("topics_title"))}</h1><p>${esc(t("topics_sub"))}</p></div><button class="btn" id="ai">${icon("spark")}${esc(t("ai_choose"))}</button></div>
    <div class="card-head" style="margin-top:4px"><div><h2>${esc(t("track_caregiving"))}</h2><p>${esc(t("track_caregiving_sub"))}</p></div></div>
    <div class="grid g3">${care.map(card).join("")}</div>
    ${jlpt.length ? `<div class="card-head" style="margin-top:28px"><div><h2>${esc(t("track_jlpt"))}</h2><p>${esc(t("track_jlpt_sub"))}${lvl ? " · " + esc(t("your_level")) + ": " + esc(levelLabel(lvl)) : ""}</p></div></div>
    <div class="grid g3">${jlpt.map(card).join("")}</div>` : ""}`;
  $("#ai").onclick = (e) => startSession({ kind: "practice" }, e.currentTarget);
  $$("[data-topic]", page).forEach((b) => (b.onclick = () => startSession({ kind: "practice", topic_id: b.dataset.topic }, b)));
}

export async function interviewPage() {
  const page = shell({ nav: nav(), title: t("iv_title") });
  loading(page);
  const [topics, hist] = await Promise.all([api("/topics?kind=interview"), api("/me/sessions")]);
  const ivs = hist.filter((h) => h.kind === "interview");
  page.innerHTML = `<div class="page-head"><div><h1>${esc(t("iv_title"))}</h1><p>${esc(t("iv_sub"))}</p></div></div>
    <div class="grid g2">${topics.map((tp) => `<article class="topic"><h3>${esc(tp.title)}</h3><p class="muted">${esc(tp.summary)}</p>
      <div class="jp-row">${tp.vocab.map((v) => `${esc(v.jp)} (${esc(v.reading)})`).join("　")}</div>
      <div class="foot"><span class="badge plain">${esc(t("questions_n", { n: tp.questions }))}</span><span class="sp"></span><button class="btn" data-topic="${esc(tp.id)}">${icon("mic")}${esc(t("iv_start"))}</button></div></article>`).join("")}</div>
    <section class="card" style="margin-top:16px"><div class="card-head"><h2>${esc(t("sessions_all"))}</h2></div>
    ${ivs.length ? sessionsTable(ivs) : `<p class="muted">${esc(t("none_yet"))}</p>`}</section>`;
  $$("[data-topic]", page).forEach((b) => (b.onclick = () => startSession({ kind: "interview", topic_id: b.dataset.topic }, b)));
  bindRows(page);
}

function sessionsTable(rows) {
  return `<div class="table-wrap"><table class="t"><thead><tr><th>${esc(t("topic"))}</th><th>${esc(t("date"))}</th><th>${esc(t("status"))}</th><th class="num">${esc(t("answers"))}</th><th class="num">${esc(t("score"))}</th></tr></thead><tbody>
    ${rows.map((r) => `<tr class="click" data-href="/app/session/${r.id}" tabindex="0"><td>${esc(r.title)}${r.kind === "interview" ? ` <span class="badge">${esc(t("interview"))}</span>` : ""}${r.passed === true ? ` <span class="badge ok">${esc(t("passed"))}</span>` : ""}</td>
    <td class="nowrap">${fmtDate(r.created_at)}</td><td>${statusBadge(r.status)}</td><td class="num">${r.answered}/${r.total}</td><td class="num">${pct(r.avg_score)}</td></tr>`).join("")}</tbody></table></div>`;
}
function bindRows(root) {
  $$("tr[data-href]", root).forEach((tr) => {
    tr.onclick = () => navigate(tr.dataset.href);
    tr.onkeydown = (e) => { if (e.key === "Enter") navigate(tr.dataset.href); };
  });
}

// ======================================================================= practice / interview room
export async function sessionPage({ params }) {
  const page = shell({ nav: nav(), title: "…", back: "/app" });
  loading(page);
  let s = await api(`/sessions/${params.id}`);
  let trace = lastTrace && lastTrace.events && String(params.id) ? lastTrace : null;
  lastTrace = null;
  let feedback = null; // result of the last answer, shown before moving on
  let shownAt = performance.now();
  let rec = null;
  const isIv = s.kind === "interview";
  const backTo = isIv ? "/app/interview" : "/app/learn";
  shell({ nav: nav(), title: s.topic.title, crumb: isIv ? t("interview") : t("learn"), back: backTo,
    actions: s.status === "active" ? `<button class="btn ghost sm" id="leave">${esc(t("leave"))}</button>` : "" });

  const draw = () => {
    const q = s.question;
    const left = feedback ? feedbackHTML(feedback, s) : s.status === "active" && q ? questionHTML(q, s, isIv) : doneHTML(s, isIv);
    page.innerHTML = `<div class="room"><div>
        <div class="steps" aria-hidden="true">${Array.from({ length: s.total }, (_, k) => `<i class="${k < s.answered ? "done" : k === s.answered && s.status === "active" ? "now" : ""}"></i>`).join("")}</div>
        ${left}
        ${s.history.length ? `<section class="card"><div class="card-head"><h2>${esc(t("history"))}</h2><span class="muted small">${s.answered}/${s.total}</span></div>
          ${s.history.slice().reverse().map((h) => `<div class="hist-item" style="border-color:var(--${h.score >= 0.8 ? "strong" : h.score >= 0.6 ? "mid" : "weak"})">
            <div class="row between"><b class="jp">${esc(h.question)}</b><span class="badge ${h.score >= 0.8 ? "ok" : h.score >= 0.6 ? "warn" : "bad"}">${pct(h.score)}</span></div>
            <div class="small muted" style="margin-top:4px">${esc(h.answer)}</div><div class="small" style="margin-top:4px">${esc(h.feedback)}</div></div>`).join("")}</section>` : ""}
      </div>
      <aside>
        <section class="card"><h2 style="margin-bottom:8px">${esc(t("vocab"))}</h2>
          <table class="vocab"><tbody>${s.topic.vocab.map((v) => `<tr><td>${esc(v.jp)}<div class="small muted" style="font-weight:400">${esc(v.reading || "")}</div></td><td>${esc(lang() === "ne" ? v.ne || v.en : v.en)}</td></tr>`).join("")}</tbody></table></section>
        <section class="card"><div class="card-head"><div><h2>${esc(t("agents"))}</h2><p>${esc(t("agents_sub"))}</p></div></div>
          ${trace ? traceHTML(trace, { anim: true }) : `<p class="muted small">–</p>`}</section>
        ${s.decision && s.decision.candidates ? `<section class="card"><details><summary style="cursor:pointer;font-weight:600">${esc(t("rec_why"))}</summary><div style="margin-top:10px">${whyTable(s.decision)}</div>
          ${s.decision.memories && s.decision.memories.length ? `<p class="small muted" style="margin-top:10px">Smriti recalled: ${s.decision.memories.map((m) => esc(m.kind)).join(", ")}</p>` : ""}</details></section>` : ""}
      </aside></div>`;
    if (s.status !== "active") $("#actslot").innerHTML = "";
    bind();
  };

  const bind = () => {
    const lv = $("#leave");
    if (lv) lv.onclick = async () => {
      if (!(await confirmBox(t("leave_q"), { ok: t("leave") }))) return;
      await api(`/sessions/${s.session_id}/abandon`, { method: "POST" });
      goBack(backTo);
    };
    const nq = $("#nextq");
    if (nq) { nq.onclick = () => { feedback = null; shownAt = performance.now(); draw(); $("#ans")?.focus(); }; nq.focus(); }
    $$("[data-again]").forEach((b) => (b.onclick = () => startSession(isIv ? { kind: "interview", topic_id: s.topic.id } : { kind: "practice" }, b)));
    const form = $("#af");
    if (!form) return;
    const ta = $("#ans");
    const draft = `xk_draft_${s.session_id}_${s.question.id}`;
    ta.value = store.get(draft, "");
    ta.oninput = () => store.set(draft, ta.value);
    ta.onkeydown = (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) form.requestSubmit(); };
    form.onsubmit = async (e) => {
      e.preventDefault();
      const text = ta.value.trim();
      if (!text) { $("#err").textContent = t("type_ans"); return; }
      $("#send").disabled = true;
      $("#err").innerHTML = `<span class="muted">${esc(t("checking"))}</span>`;
      try {
        const res = await api(`/sessions/${s.session_id}/answer`, { method: "POST", body: { answer: text, latency_ms: Math.round(performance.now() - shownAt) } });
        store.del(draft);
        trace = res.trace;
        feedback = { ...res.result, eligibility: res.eligibility };
        s = res;
        draw();
      } catch (err) {
        $("#err").textContent = err.message;
        $("#send").disabled = false;
        if (err.status === 429) trace = null;
      }
    };
    const mic = $("#mic");
    if (mic) mic.onclick = () => {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) { toast(t("nomic"), true); return; }
      if (rec) { rec.stop(); return; }
      rec = new SR();
      rec.lang = isIv ? "ja-JP" : { en: "en-US", ne: "ne-NP", ja: "ja-JP" }[lang()];
      rec.interimResults = false;
      rec.onresult = (ev) => { ta.value = (ta.value + " " + ev.results[0][0].transcript).trim(); ta.oninput(); };
      rec.onend = () => { rec = null; mic.innerHTML = `${icon("mic")}${esc(t("speak"))}`; };
      rec.start();
      mic.innerHTML = `${icon("x")}${esc(t("stop"))}`;
    };
  };
  current.cleanup = () => { if (rec) rec.stop(); };
  draw();
  $("#ans")?.focus();
}

function questionHTML(q, s, isIv) {
  const showJa = lang() !== "ja" && q.prompt_ja && q.prompt_ja !== q.prompt && !isIv;
  return `<section class="qcard ${isIv ? "proctor" : ""}">
    <div class="qmeta"><span class="badge">${esc(t("qof", { i: q.index, n: q.total }))}</span><span class="badge plain">${esc(sk(q.skill))}</span><span class="badge plain">${esc(t("diff")[q.difficulty])}</span></div>
    <div class="qtext jp">${esc(q.prompt)}</div>
    ${showJa ? `<div class="qsub jp">${esc(q.prompt_ja)}</div>` : ""}
    <form id="af" class="answer-box"><label class="sr" for="ans">${esc(t("type_ans"))}</label>
      <textarea id="ans" placeholder="${esc(t("type_ans"))}" maxlength="2000"></textarea>
      <p class="err" id="err" role="status"></p>
      <div class="row"><button type="button" class="btn ghost" id="mic">${icon("mic")}${esc(t("speak"))}</button><span class="sp"></span>
      <span class="small muted">Ctrl + Enter</span><button class="btn" id="send">${esc(t("send"))}</button></div>
    </form></section>`;
}

function feedbackHTML(f, s) {
  const b = band(f.score);
  return `<section class="qcard"><div class="feedback ${b}" style="margin-top:0">
    <div class="row" style="align-items:flex-start;flex-wrap:nowrap">${scoreRing(f.score)}<div class="sp"><div class="row"><b>${esc(sk(f.skill))}</b><span class="badge plain">${esc(f.grader)}</span>
      ${f.memory_note ? `<span class="badge ${f.memory_note === "improved" ? "ok" : "warn"}">Smriti: ${esc(f.memory_note)}</span>` : ""}</div>
      <p style="margin-top:6px">${esc(f.feedback)}</p></div></div>
    ${f.model_answer ? `<div class="probe"><b>${esc(t("model"))}</b><p class="jp" style="margin-top:4px">${esc(f.model_answer)}</p></div>` : ""}
    <div class="probe"><b>${esc(t("think"))}</b><p style="margin-top:4px">${esc(f.probe)}</p></div></div>
    <div class="row" style="margin-top:16px"><span class="sp"></span><button class="btn" id="nextq">${esc(s.status === "active" ? t("next_q") : t("done_title"))}</button></div></section>`;
}

function doneHTML(s, isIv) {
  return `<section class="qcard" style="text-align:center;padding:34px">
    ${scoreRing(s.avg_score || 0)}
    <h1 style="margin-top:12px">${esc(t("done_title"))}</h1>
    <p class="muted" style="margin-top:6px">${esc(t("done_avg", { p: pct(s.avg_score) }))}</p>
    ${isIv && s.passed !== null ? `<p style="margin-top:10px"><span class="badge ${s.passed ? "ok" : "bad"}">${s.passed ? esc(t("passed")) : esc(t("notpassed", { p: "70%" }))}</span></p>` : ""}
    <div class="row" style="justify-content:center;margin-top:20px"><a class="btn ghost" href="/app">${esc(t("go_dash"))}</a><button class="btn" data-again>${esc(isIv ? t("iv_start") : t("again"))}</button></div></section>`;
}

// ======================================================================= progress
export async function progressPage() {
  const page = shell({ nav: nav(), title: t("progress") });
  loading(page);
  const [heat, hist, mems] = await Promise.all([api("/me/heatmap"), api("/me/sessions"), api("/me/memories")]);
  page.innerHTML = `<div class="page-head"><div><h1>${esc(t("progress"))}</h1><p>${esc(t("heat_sub"))}</p></div></div>
    <div class="split"><div>
      <section class="card"><div class="card-head"><h2>${esc(t("heat"))}</h2><span class="muted small">${heat.answers} ${esc(t("answers"))} · ${pct(heat.overall)}</span></div>${heatmapHTML(heat)}</section>
      <section class="card"><div class="card-head"><h2>${esc(t("sessions_all"))}</h2></div>${hist.length ? sessionsTable(hist) : `<p class="muted">${esc(t("none_yet"))}</p>`}</section>
    </div><div>
      <section class="card"><div class="card-head"><h2>${esc(t("mastery"))}</h2></div><div class="bars">
        ${heat.topics.map((tp) => { const a = heat.topic_avg[tp.id]; return `<div class="b"><span>${esc(tp.title)}</span>${meter(a.avg || 0)}<span>${pct(a.avg)}</span></div>`; }).join("")}</div></section>
      <section class="card"><div class="card-head"><div><h2>${esc(t("memories"))}</h2><p>${esc(t("memories_sub"))}</p></div></div>
        ${mems.length ? `<div class="stack">${mems.slice(0, 14).map((m) => `<div class="hist-item" style="border-color:var(--${m.kind === "struggle" ? "weak" : "strong"})">
          <div class="row between"><span class="badge ${m.kind === "struggle" ? "bad" : "ok"}">${esc(m.kind === "struggle" ? t("struggle") : t("masteryk"))}</span><span class="small muted">${fmtDate(m.created_at)}</span></div>
          <div class="small" style="margin-top:4px">${esc(m.text.replace(/^\[\w+\]\s*/, ""))}</div></div>`).join("")}</div>` : `<p class="muted">${esc(t("none_yet"))}</p>`}
      </section></div></div>`;
  bindRows(page);
}

// ======================================================================= certificate
export async function certificatePage() {
  const page = shell({ nav: nav(), title: t("certificate") });
  loading(page);
  const d = await api("/me/dashboard");
  const c = d.certificate;
  page.innerHTML = `<div class="page-head"><div><h1>${esc(t("cert_title"))}</h1><p>${esc(t("cert_sub"))}</p></div></div>
    <div class="split"><div>${c && !c.revoked ? certHTML(d.user, c) : `<section class="card"><div class="empty"><h3>${esc(d.eligibility.eligible ? t("cert_claim") : t("cert_need"))}</h3>
      <button class="btn lg" id="claim" style="margin-top:12px" ${d.eligibility.eligible ? "" : "disabled"}>${icon("award")}${esc(t("cert_claim"))}</button></div></section>`}</div>
    <section class="card"><div class="card-head"><h2>${esc(t("readiness"))}</h2></div>${checksHTML(d.eligibility.checks)}</section></div>`;
  const cl = $("#claim");
  if (cl) cl.onclick = async () => {
    cl.disabled = true;
    try { await api("/me/certificate", { method: "POST" }); certificatePage(); } catch (e) { toast(e.message, true); cl.disabled = false; }
  };
}
function certHTML(user, c) {
  const url = `${location.origin}/verify/${c.code}`;
  return `<section class="cert"><div class="seal" aria-hidden="true">合格</div>
    <div class="muted">XploraKōdo · Kaigo readiness</div><h2>${esc(t("cert_title"))}</h2>
    <div class="who">${esc(user.name)}</div><p class="muted">${esc(user.level || "")} · ${fmtDate(c.issued_at, false)}</p>
    <div class="row" style="margin-top:24px;align-items:flex-end"><img class="qr" src="/api/verify/${encodeURIComponent(c.code)}/qr.svg" alt="QR code linking to the verification page">
      <div><div class="small muted">${esc(t("cert_verify"))}</div><a href="/verify/${esc(c.code)}">${esc(url)}</a><div class="mono" style="margin-top:6px">${esc(c.code)}</div>
      <button class="btn ghost sm" style="margin-top:10px" onclick="window.print()">Print</button></div></div></section>`;
}

export async function verifyPage({ params }) {
  $("#root").innerHTML = `<div class="auth-form" style="min-height:100vh"><div class="box" style="max-width:560px" id="vb"><div class="loading"><div class="spinner"></div></div></div></div>`;
  document.title = "Verify certificate · XploraKōdo";
  try {
    const v = await api(`/verify/${encodeURIComponent(params.code)}`);
    $("#vb").innerHTML = `<a class="brand" href="/" style="color:var(--ink);padding:0;margin-bottom:20px"><span class="brand-mark" style="background:var(--kon-ink);color:#fff">介</span><span><b style="color:var(--ink)">XploraKōdo</b><span>Certificate verification</span></span></a>
      <section class="card"><div class="row between"><h2>${esc(v.name)}</h2><span class="badge ${v.valid ? "ok" : "bad"}">${v.valid ? "Valid" : v.revoked ? "Revoked" : "Invalid signature"}</span></div>
      <p class="muted" style="margin-top:4px">${esc(v.org || "Independent learner")} · Level ${esc(v.level || "–")} · issued ${fmtDate(v.issued_at, false)}</p>
      <div class="bars" style="margin-top:16px">${Object.entries(v.scores.topics || {}).map(([k, val]) => `<div class="b"><span>${esc(k)}</span>${meter(val || 0)}<span>${pct(val)}</span></div>`).join("")}
      <div class="b"><span><b>Interview</b></span>${meter(v.scores.interview || 0)}<span>${pct(v.scores.interview)}</span></div></div>
      <p class="small muted" style="margin-top:14px">Code <span class="mono">${esc(v.code)}</span> · signature ${v.signature_valid ? "verified" : "does not match"}</p></section></div>`;
  } catch (e) {
    $("#vb").innerHTML = `<section class="card empty"><h3>Certificate not found</h3><p>${esc(e.message)}</p></section>`;
  }
}

// ======================================================================= profile
export async function profilePage() {
  const page = shell({ nav: nav(), title: t("profile") });
  const u = await api("/auth/me");
  page.innerHTML = `<div class="page-head"><div><h1>${esc(t("profile"))}</h1><p>${esc(u.email)}</p></div></div>
    <div class="grid g2"><section class="card"><form id="pf">
      <div class="field"><label class="f" for="nm">${esc(t("name"))}</label><input id="nm" type="text" value="${esc(u.name)}" maxlength="80"></div>
      <div class="field"><label class="f" for="lg">${esc(t("lang"))}</label><select id="lg">${LANGS.map(([k, v]) => `<option value="${k}" ${k === u.lang ? "selected" : ""}>${v}</option>`).join("")}</select></div>
      <button class="btn">${esc(t("save"))}</button></form></section>
    <section class="card"><form id="pw">
      <div class="field"><label class="f" for="c1">${esc(t("pw_cur"))}</label><input id="c1" type="password" autocomplete="current-password"></div>
      <div class="field"><label class="f" for="c2">${esc(t("pw_new"))}</label><input id="c2" type="password" autocomplete="new-password" minlength="8"></div>
      <p class="err" id="perr"></p><button class="btn ghost">${esc(t("pw_change"))}</button></form></section></div>`;
  $("#pf").onsubmit = async (e) => {
    e.preventDefault();
    try {
      const nu = await api("/me", { method: "PUT", body: { name: $("#nm").value, lang: $("#lg").value } });
      auth.setUser(nu); store.set("xk_lang", nu.lang); toast(t("saved")); navigate(location.pathname, { replace: true });
    } catch (err) { toast(err.message, true); }
  };
  $("#pw").onsubmit = async (e) => {
    e.preventDefault();
    $("#perr").textContent = "";
    try { await api("/me/password", { method: "POST", body: { current: $("#c1").value, new: $("#c2").value } }); toast(t("pw_done")); e.target.reset(); }
    catch (err) { $("#perr").textContent = err.message; }
  };
}
export { overlay };
