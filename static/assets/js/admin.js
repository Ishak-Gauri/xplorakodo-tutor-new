// Admin console: overview, students, question bank, agent runs, certificates, institutes, settings, audit.
import {
  $, $$, ago, api, band, confirmBox, current, esc, fmtDate, heatmapHTML, icon, loading, meter, navigate, overlay,
  pct, shell, toast, traceHTML,
} from "./core.js";

const nav = () => [
  { group: "Operate" },
  { href: "/admin", icon: "home", label: "Overview", exact: true },
  { href: "/admin/students", icon: "users", label: "Students" },
  { href: "/admin/questions", icon: "list", label: "Question bank" },
  { href: "/admin/certificates", icon: "award", label: "Certificates" },
  { group: "AI" },
  { href: "/admin/kb", icon: "db", label: "Knowledge base" },
  { href: "/admin/model", icon: "chart", label: "Level model" },
  { href: "/admin/factory", icon: "spark", label: "Course factory" },
  { group: "Observe" },
  { href: "/admin/agents", icon: "cpu", label: "Agent runs" },
  { href: "/admin/audit", icon: "file", label: "Audit log" },
  { group: "Configure" },
  { href: "/admin/orgs", icon: "building", label: "Institutes" },
  { href: "/admin/settings", icon: "gear", label: "Settings" },
];
export const adminNav = () => nav();
const SKILLS = ["vocabulary", "grammar", "comprehension", "recall"];
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);
const scoreBadge = (v) => (v === null || v === undefined ? `<span class="muted">–</span>` :
  `<span class="badge ${band(v) === "s" ? "ok" : band(v) === "m" ? "warn" : "bad"}">${pct(v)}</span>`);
const statusBadge = (s) => `<span class="badge ${s === "ok" || s === "active" || s === "done" ? "ok" : s === "blocked" || s === "suspended" ? "bad" : s === "error" ? "bad" : "plain"}">${esc(s)}</span>`;
function rowsLink(root) {
  $$("tr[data-href]", root).forEach((tr) => {
    tr.onclick = () => navigate(tr.dataset.href);
    tr.onkeydown = (e) => { if (e.key === "Enter") navigate(tr.dataset.href); };
  });
}

// ======================================================================= overview
function activityChart(rows) {
  const W = 640, H = 200, pad = { l: 34, r: 34, t: 12, b: 26 };
  const max = Math.max(4, ...rows.map((r) => r.answers));
  const bw = (W - pad.l - pad.r) / rows.length;
  const y = (v) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const ys = (v) => pad.t + (H - pad.t - pad.b) * (1 - v);
  const pts = rows.map((r, i) => (r.avg === null ? null : [pad.l + bw * i + bw / 2, ys(r.avg)])).filter(Boolean);
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Answers per day and average score, last 14 days">
    ${[0, 0.5, 1].map((f) => `<line class="grid-l" x1="${pad.l}" x2="${W - pad.r}" y1="${ys(f)}" y2="${ys(f)}"/><text x="${pad.l - 6}" y="${ys(f) + 4}" text-anchor="end">${Math.round(max * f)}</text><text x="${W - pad.r + 6}" y="${ys(f) + 4}">${Math.round(f * 100)}%</text>`).join("")}
    ${rows.map((r, i) => `<rect x="${pad.l + bw * i + bw * 0.18}" y="${y(r.answers)}" width="${bw * 0.64}" height="${H - pad.b - y(r.answers)}" rx="3" fill="var(--kon)" opacity=".85"><title>${r.day}: ${r.answers} answers, avg ${pct(r.avg)}</title></rect>
      ${i % 2 === 0 ? `<text x="${pad.l + bw * i + bw / 2}" y="${H - 8}" text-anchor="middle">${r.day.slice(5, 10)}</text>` : ""}`).join("")}
    ${pts.length > 1 ? `<polyline fill="none" stroke="var(--mid)" stroke-width="2.5" points="${pts.map((p) => p.join(",")).join(" ")}"/>` : ""}
    ${pts.map((p) => `<circle cx="${p[0]}" cy="${p[1]}" r="3.5" fill="var(--mid)"/>`).join("")}
  </svg><div class="legend"><span><i style="background:var(--kon)"></i>Answers per day</span><span><i style="background:var(--mid)"></i>Average score</span></div>`;
}

export async function overviewPage() {
  const page = shell({ nav: nav(), title: "Overview" });
  loading(page);
  const [o, obs] = await Promise.all([api("/admin/overview"), api("/admin/observability")]);
  const k = o.kpis, cfg = o.settings;
  const lvMax = Math.max(1, ...o.levels.map((l) => l.n));
  page.innerHTML = `
    <div class="page-head"><div><h1>Platform overview</h1><p>Live from PostgreSQL. Grader: <b>${esc(o.llm)}</b> · embeddings: <b>${esc(o.embedder)}</b> (pgvector, 256 dims).</p></div>
      <div class="row"><a class="btn ghost" href="/admin/agents">${icon("cpu")}Agent runs</a><a class="btn" href="/admin/students">${icon("users")}Students</a></div></div>
    ${cfg.kill_switch ? `<div class="banner bad">${icon("shield")}<div class="sp"><b>Kill switch is on.</b> Every tutor and interview call is paused.</div><a class="btn sm danger" href="/admin/settings">Open settings</a></div>` : ""}
    <div class="grid g4" style="margin-bottom:16px">
      <div class="stat"><div class="k">Students</div><div class="v">${k.students}</div><div class="d">${k.active_7d} active in the last 7 days</div></div>
      <div class="stat"><div class="k">Average score</div><div class="v">${pct(k.avg_score)}</div><div class="d">${k.answers.toLocaleString()} graded answers</div></div>
      <div class="stat"><div class="k">Tokens today</div><div class="v">${k.tokens_today.toLocaleString()}</div><div class="d">${k.sessions_today} sessions today</div></div>
      <div class="stat"><div class="k">Certificates</div><div class="v">${k.certificates}</div><div class="d">${k.memories.toLocaleString()} memories in pgvector</div></div>
    </div>
    <div class="split">
      <div>
        <section class="card"><div class="card-head"><h2>Activity, last 14 days</h2></div>${activityChart(o.activity)}</section>
        <section class="card"><div class="card-head"><div><h2>Cohort skill heatmap</h2><p>Average of every practice answer, all students.</p></div></div>${heatmapHTML(o.cohort, { admin: true })}</section>
        <section class="card"><div class="card-head"><div><h2>Hardest questions</h2><p>Lowest average score. Review the wording or keywords.</p></div><a class="small" href="/admin/questions">Question bank</a></div>
          ${o.hardest.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>ID</th><th>Question</th><th class="num">Answers</th><th class="num">Avg</th></tr></thead><tbody>
          ${o.hardest.map((h) => `<tr class="click" data-href="/admin/questions?q=${encodeURIComponent(h.id)}" tabindex="0"><td class="mono">${esc(h.id)}</td><td>${esc(h.prompt)}</td><td class="num">${h.n}</td><td class="num">${scoreBadge(h.avg)}</td></tr>`).join("")}
          </tbody></table></div>` : `<p class="muted">No answers yet.</p>`}</section>
      </div>
      <div>
        <section class="card"><div class="card-head"><h2>AI stack</h2></div><div class="stack small">
          <div class="row between"><span>Agent engine</span><b>LangGraph</b></div>
          <div class="row between"><span>LLM</span><b>${esc(obs.llm)}${obs.llm_model ? " · " + esc(obs.llm_model) : ""}</b></div>
          <div class="row between"><span>LangSmith tracing</span>${obs.langsmith.enabled ? `<a class="badge ok" href="${esc(obs.langsmith.url)}" target="_blank" rel="noopener">on · ${esc(obs.langsmith.project)}</a>` : `<span class="badge plain">off</span>`}</div>
          <div class="row between"><span>Knowledge base</span><a href="/admin/kb"><b>${Number(obs.kb_documents).toLocaleString()} docs</b></a></div>
          <div class="row between"><span>Level model</span><a href="/admin/model"><b>${esc(obs.leveler)}</b></a></div></div></section>
        <section class="card"><div class="card-head"><h2>Agent health, 7 days</h2><span class="small muted">${k.blocked_24h} blocked runs in 24 h · ${k.run_ms ?? "–"} ms avg</span></div>
          ${o.agents.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>Agent</th><th class="num">Steps</th><th class="num">Avg ms</th><th class="num">Issues</th></tr></thead><tbody>
          ${o.agents.map((a) => `<tr><td>${esc(a.agent)}</td><td class="num">${a.n}</td><td class="num">${a.ms}</td><td class="num">${a.issues ? `<span class="badge bad">${a.issues}</span>` : "0"}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">No runs yet.</p>`}
        </section>
        <section class="card"><div class="card-head"><h2>Placement levels</h2></div><div class="bars">
          ${o.levels.map((l) => `<div class="b"><span>${esc(l.level)}</span>${meter(l.n / lvMax, "")}<span>${l.n}</span></div>`).join("") || `<p class="muted">No students yet.</p>`}</div></section>
        <section class="card"><div class="card-head"><h2>Graders used</h2></div><div class="bars">
          ${o.graders.map((g) => `<div class="b"><span>${esc(g.grader)}</span>${meter(g.n / Math.max(1, ...o.graders.map((x) => x.n)), "")}<span>${g.n}</span></div>`).join("") || `<p class="muted">No answers yet.</p>`}</div></section>
        <section class="card"><div class="card-head"><h2>Guardrails</h2><a class="small" href="/admin/settings">Edit</a></div>
          <div class="stack small"><div class="row between"><span>Daily budget per student</span><b>${Number(cfg.daily_token_budget).toLocaleString()} tokens</b></div>
          <div class="row between"><span>Questions per session</span><b>${cfg.session_questions}</b></div>
          <div class="row between"><span>Interview pass mark</span><b>${pct(cfg.interview_pass)}</b></div>
          <div class="row between"><span>Certificate mastery</span><b>${pct(cfg.cert_min_mastery)}</b></div></div></section>
      </div>
    </div>`;
  rowsLink(page);
}

// ======================================================================= students
export async function studentsPage({ query }) {
  const page = shell({ nav: nav(), title: "Students" });
  loading(page);
  const orgs = await api("/admin/orgs");
  const q = query.q || "", org = query.org || "", level = query.level || "", p = Number(query.page || 1);
  const data = await api(`/admin/students?q=${encodeURIComponent(q)}&page=${p}${org ? `&org_id=${org}` : ""}${level ? `&level=${encodeURIComponent(level)}` : ""}`);
  const pages = Math.max(1, Math.ceil(data.total / data.size));
  const qs = (over) => { const u = new URLSearchParams({ q, org, level, page: p, ...over }); [...u.keys()].forEach((key) => { if (!u.get(key)) u.delete(key); }); return `/admin/students?${u}`; };
  page.innerHTML = `<div class="page-head"><div><h1>Students</h1><p>${data.total} students. Click a row for their heatmap, sessions, memory and actions.</p></div><button class="btn" id="add">${icon("plus")}Add student</button></div>
    <form class="row" id="flt" style="margin-bottom:14px">
      <input type="search" id="q" class="inline" style="min-width:240px;flex:1" placeholder="Search name or email" value="${esc(q)}" aria-label="Search">
      <select id="org" class="inline" aria-label="Institute"><option value="">All institutes</option>${orgs.map((o) => `<option value="${o.id}" ${String(o.id) === org ? "selected" : ""}>${esc(o.name)}</option>`).join("")}</select>
      <select id="lv" class="inline" aria-label="Level"><option value="">All levels</option>${["Pre-N5", "N5", "N4", "N3", "N2", "N1", "Not placed"].map((l) => `<option ${l === level ? "selected" : ""}>${l}</option>`).join("")}</select>
      <button class="btn ghost">Filter</button></form>
    ${data.items.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>Name</th><th>Institute</th><th>Level</th><th class="num">Answers</th><th class="num">Avg</th><th>Last active</th><th>Status</th></tr></thead><tbody>
      ${data.items.map((s) => `<tr class="click" tabindex="0" data-href="/admin/students/${s.id}"><td><b>${esc(s.name)}</b><div class="small muted">${esc(s.email)}</div></td><td>${esc(s.org || "–")}</td>
        <td>${s.level ? `<span class="badge">${esc(s.level)}</span>` : `<span class="badge plain">Not placed</span>`}${s.certified ? ` <span class="badge ok">Certified</span>` : ""}</td>
        <td class="num">${s.answers}</td><td class="num">${scoreBadge(s.avg)}</td><td class="nowrap">${ago(s.last_active)}</td><td>${statusBadge(s.status)}</td></tr>`).join("")}</tbody></table></div>
      <div class="row" style="margin-top:12px"><span class="muted small">Page ${p} of ${pages}</span><span class="sp"></span>
      ${p > 1 ? `<a class="btn ghost sm" href="${qs({ page: p - 1 })}">Previous</a>` : ""}${p < pages ? `<a class="btn ghost sm" href="${qs({ page: p + 1 })}">Next</a>` : ""}</div>`
      : `<div class="card empty"><h3>No students match</h3><p>Clear the filters or add a student.</p></div>`}`;
  $("#flt").onsubmit = (e) => { e.preventDefault(); navigate(`/admin/students?${new URLSearchParams({ q: $("#q").value, org: $("#org").value, level: $("#lv").value })}`, { replace: true }); };
  $("#add").onclick = () => {
    const m = overlay(`<h2>Add student</h2><p class="muted small" style="margin:4px 0 16px">They can sign in right away with this email and password.</p>
      <form id="nf"><div class="field"><label class="f" for="a1">Full name</label><input id="a1" type="text" required></div>
      <div class="field"><label class="f" for="a2">Email</label><input id="a2" type="email" required></div>
      <div class="field"><label class="f" for="a3">Temporary password</label><input id="a3" type="text" minlength="8" required></div>
      <div class="grid g2"><div class="field"><label class="f" for="a4">Language</label><select id="a4"><option value="en">English</option><option value="ne">नेपाली</option><option value="ja">日本語</option></select></div>
      <div class="field"><label class="f" for="a5">Institute</label><select id="a5"><option value="">None</option>${orgs.map((o) => `<option value="${o.id}">${esc(o.name)}</option>`).join("")}</select></div></div>
      <p class="err" id="ae"></p><div class="row" style="justify-content:flex-end"><button type="button" class="btn ghost" data-close>Cancel</button><button class="btn">Add student</button></div></form>`, { kind: "modal" });
    $("#nf", m.el).onsubmit = async (e) => {
      e.preventDefault();
      try {
        const u = await api("/admin/students", { method: "POST", body: { name: $("#a1").value, email: $("#a2").value, password: $("#a3").value, lang: $("#a4").value, org_id: $("#a5").value ? Number($("#a5").value) : null } });
        m.close(); toast(`Added ${u.name}`); navigate(`/admin/students/${u.id}`);
      } catch (err) { $("#ae").textContent = err.message; }
    };
  };
  rowsLink(page);
}

export async function studentDetailPage({ params }) {
  const page = shell({ nav: nav(), title: "Student", crumb: "Students", back: "/admin/students" });
  loading(page);
  const [d, orgs] = await Promise.all([api(`/admin/students/${params.id}`), api("/admin/orgs")]);
  const u = d.user, dash = d.dashboard;
  shell({ nav: nav(), title: u.name, crumb: "Students", back: "/admin/students" });
  let tab = "overview";
  const draw = () => {
    page.innerHTML = `<div class="page-head"><div><h1>${esc(u.name)}</h1><p>${esc(u.email)} · ${esc(u.org || "No institute")} · joined ${fmtDate(u.created_at, false)} · last login ${ago(u.last_login_at)}</p></div>
      <div class="row">${statusBadge(u.status)}<button class="btn ghost sm" id="reset">Reset password</button>
      <button class="btn sm ${u.status === "active" ? "danger" : ""}" id="susp">${u.status === "active" ? "Suspend" : "Reactivate"}</button></div></div>
      <div class="grid g4" style="margin-bottom:16px">
        <div class="stat"><div class="k">Level</div><div class="v">${esc(u.level || "Not placed")}</div></div>
        <div class="stat"><div class="k">Average score</div><div class="v">${pct(dash.stats.avg)}</div>${meter(dash.stats.avg)}</div>
        <div class="stat"><div class="k">Answers</div><div class="v">${dash.stats.answers}</div><div class="d">${dash.stats.sessions} sessions · streak ${dash.stats.streak}</div></div>
        <div class="stat"><div class="k">Avg response time</div><div class="v">${dash.stats.latency_ms ? (dash.stats.latency_ms / 1000).toFixed(1) + " s" : "–"}</div><div class="d">${dash.stats.tokens_today.toLocaleString()} tokens today</div></div>
      </div>
      <div class="tabs" role="tablist">${["overview", "sessions", "memory", "account"].map((x) => `<button role="tab" class="${tab === x ? "on" : ""}" data-tab="${x}">${cap(x)}</button>`).join("")}</div>
      <div id="tabbody"></div>`;
    const body = $("#tabbody");
    if (tab === "overview") {
      body.innerHTML = `<div class="split"><section class="card"><div class="card-head"><h2>Skill heatmap</h2></div>${heatmapHTML(dash.heatmap, { admin: true })}</section>
        <div><section class="card"><div class="card-head"><h2>Certificate readiness</h2>${dash.eligibility.eligible ? `<span class="badge ok">Eligible</span>` : ""}</div>
        ${dash.eligibility.checks.map((c) => `<div class="check ${c.ok ? "ok" : "no"}">${icon(c.ok ? "check" : "circle")}<div><b>${esc(c.label || cap(c.key))}</b><div class="small muted">${esc(c.detail)}</div></div></div>`).join("")}
        ${dash.certificate ? `<p style="margin-top:10px"><a href="/verify/${esc(dash.certificate.code)}">${esc(dash.certificate.code)}</a> ${dash.certificate.revoked ? `<span class="badge bad">revoked</span>` : ""}</p>` : ""}</section>
        ${dash.recommendation && dash.recommendation.title ? `<section class="card"><div class="card-head"><h2>Router's next pick</h2></div><p><b>${esc(dash.recommendation.title)}</b> <span class="muted">(${esc(dash.recommendation.reason)})</span></p></section>` : ""}</div></div>`;
    } else if (tab === "sessions") {
      body.innerHTML = d.sessions.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>#</th><th>Topic</th><th>Kind</th><th>Started</th><th>Status</th><th class="num">Answered</th><th class="num">Avg</th></tr></thead><tbody>
        ${d.sessions.map((s) => `<tr class="click" tabindex="0" data-href="/admin/sessions/${s.id}"><td class="mono">${s.id}</td><td>${esc(s.title)}</td><td>${esc(s.kind)}${s.passed === true ? ` <span class="badge ok">passed</span>` : s.passed === false ? ` <span class="badge bad">failed</span>` : ""}</td><td class="nowrap">${fmtDate(s.created_at)}</td><td>${statusBadge(s.status)}</td><td class="num">${s.answered}/${s.total}</td><td class="num">${scoreBadge(s.avg_score)}</td></tr>`).join("")}</tbody></table></div>
        <h2 style="margin:20px 0 10px">Placement attempts</h2>${d.placements.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>Date</th><th>Status</th><th class="num">Score</th><th>Level</th></tr></thead><tbody>
        ${d.placements.map((p) => `<tr><td>${fmtDate(p.created_at)}</td><td>${statusBadge(p.status)}</td><td class="num">${p.score ?? "–"}/${p.total}</td><td>${esc(p.level || "–")}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">None.</p>`}`
        : `<div class="card empty"><h3>No sessions yet</h3><p>This student has not practised.</p></div>`;
      rowsLink(body);
    } else if (tab === "memory") {
      body.innerHTML = `<p class="muted" style="margin-bottom:12px">Smriti memories (pgvector). The tutor recalls the closest ones before grading this student.</p>` +
        (d.memories.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>When</th><th>Kind</th><th>Topic · skill</th><th>Memory</th><th class="num">Score</th></tr></thead><tbody>
        ${d.memories.map((m) => `<tr><td class="nowrap">${fmtDate(m.created_at)}</td><td><span class="badge ${m.kind === "struggle" ? "bad" : "ok"}">${esc(m.kind)}</span></td><td class="nowrap">${esc(m.topic_id)} · ${esc(m.skill)}</td><td class="small">${esc(m.text)}</td><td class="num">${pct(m.score)}</td></tr>`).join("")}</tbody></table></div>`
        : `<div class="card empty"><h3>No memories yet</h3></div>`);
    } else {
      body.innerHTML = `<div class="grid g2"><section class="card"><h2 style="margin-bottom:12px">Assignment</h2>
        <div class="field"><label class="f" for="o1">Institute</label><select id="o1"><option value="0">None</option>${orgs.map((o) => `<option value="${o.id}" ${o.id === u.org_id ? "selected" : ""}>${esc(o.name)}</option>`).join("")}</select></div>
        <div class="field"><label class="f" for="o2">Level override</label><select id="o2"><option value="">Keep (${esc(u.level || "not placed")})</option>${["Pre-N5", "N5", "N4", "N3", "N2", "N1"].map((l) => `<option>${l}</option>`).join("")}</select></div>
        <button class="btn" id="saveacct">Save</button></section>
        <section class="card"><h2 style="margin-bottom:12px">Token usage</h2>${d.usage.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>Day</th><th class="num">Tokens</th><th class="num">Calls</th></tr></thead><tbody>${d.usage.map((x) => `<tr><td>${esc(String(x.day).slice(0, 10))}</td><td class="num">${x.tokens.toLocaleString()}</td><td class="num">${x.calls}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">No usage.</p>`}</section></div>`;
      $("#saveacct").onclick = async () => {
        try {
          await api(`/admin/students/${u.id}`, { method: "PATCH", body: { org_id: Number($("#o1").value), level: $("#o2").value || null } });
          toast("Saved"); studentDetailPage({ params });
        } catch (e) { toast(e.message, true); }
      };
    }
    $$("[data-tab]").forEach((b) => (b.onclick = () => { tab = b.dataset.tab; draw(); }));
    $("#susp").onclick = async () => {
      const to = u.status === "active" ? "suspended" : "active";
      if (!(await confirmBox(to === "suspended" ? `Suspend ${u.name}? They will be signed out and the tutor will refuse their requests.` : `Reactivate ${u.name}?`, { ok: to === "suspended" ? "Suspend" : "Reactivate", danger: to === "suspended" }))) return;
      try { await api(`/admin/students/${u.id}`, { method: "PATCH", body: { status: to } }); toast(to === "suspended" ? "Suspended" : "Reactivated"); studentDetailPage({ params }); } catch (e) { toast(e.message, true); }
    };
    $("#reset").onclick = () => {
      const m = overlay(`<h2>Reset password</h2><p class="muted small" style="margin:4px 0 14px">Give the new password to ${esc(u.name)} directly.</p>
        <form id="rf"><div class="field"><label class="f" for="np">New password</label><input id="np" type="text" minlength="8" required></div><p class="err" id="re"></p>
        <div class="row" style="justify-content:flex-end"><button type="button" class="btn ghost" data-close>Cancel</button><button class="btn">Reset password</button></div></form>`, { kind: "modal" });
      $("#rf", m.el).onsubmit = async (e) => {
        e.preventDefault();
        try { await api(`/admin/students/${u.id}`, { method: "PATCH", body: { password: $("#np").value } }); m.close(); toast("Password reset"); } catch (err) { $("#re").textContent = err.message; }
      };
    };
  };
  draw();
}

export async function sessionDetailPage({ params }) {
  const page = shell({ nav: nav(), title: `Session #${params.id}`, crumb: "Students", back: "/admin/students" });
  loading(page);
  const [s, runs] = await Promise.all([api(`/admin/sessions/${params.id}`), api(`/admin/runs?limit=60`)]);
  const mine = runs.filter((r) => r.session_id === Number(params.id));
  page.innerHTML = `<div class="page-head"><div><h1>${esc(s.topic.title)}</h1><p>${esc(s.kind)} session · ${fmtDate(s.created_at)} · ${s.answered}/${s.total} answered · average ${pct(s.avg_score)}</p></div>${statusBadge(s.status)}</div>
    <div class="split"><section class="card"><div class="card-head"><h2>Transcript</h2></div>
      ${s.history.length ? s.history.map((h) => `<div class="hist-item" style="border-color:var(--${h.score >= 0.8 ? "strong" : h.score >= 0.6 ? "mid" : "weak"});margin-bottom:14px">
        <div class="row between"><b class="jp">${h.index}. ${esc(h.question)}</b>${scoreBadge(h.score)}</div>
        <div style="margin-top:6px"><span class="muted small">Answer:</span> ${esc(h.answer)}</div>
        <div class="small" style="margin-top:4px"><span class="muted">Feedback:</span> ${esc(h.feedback)}</div>
        <div class="small muted" style="margin-top:4px">${esc(h.skill)} · ${esc(h.grader)} · ${h.latency_ms ? (h.latency_ms / 1000).toFixed(1) + " s" : "–"}${h.flags && h.flags.length ? ` · <span class="badge bad">${esc(h.flags.join(", "))}</span>` : ""}</div></div>`).join("") : `<p class="muted">No answers yet.</p>`}
    </section><div>
      <section class="card"><div class="card-head"><h2>Agent runs</h2></div>${mine.length ? `<div class="stack">${mine.map((r) => `<a href="/admin/agents/${r.id}" class="row" style="text-decoration:none;color:inherit"><span class="mono">#${r.id}</span><span class="sp">${esc(r.graph)}</span>${statusBadge(r.status)}<span class="small muted">${r.duration_ms} ms</span></a>`).join("")}</div>` : `<p class="muted">–</p>`}</section>
      ${s.decision && s.decision.candidates ? `<section class="card"><div class="card-head"><h2>Router decision</h2><span class="badge plain">${esc(s.decision.chosen_by || "router")}</span></div>
        <div class="table-wrap"><table class="t why"><thead><tr><th>Topic</th><th class="num">NB</th><th class="num">L</th></tr></thead><tbody>
        ${s.decision.candidates.map((c) => `<tr class="${c.topic_id === s.decision.topic_id ? "pick" : ""}"><td>${esc((s.decision.titles || {})[c.topic_id] || c.topic_id)}</td><td class="num">${c.nb}</td><td class="num">${c.L}</td></tr>`).join("")}</tbody></table></div></section>` : ""}
    </div></div>`;
}

// ======================================================================= question bank
export async function questionsPage({ query }) {
  const page = shell({ nav: nav(), title: "Question bank" });
  loading(page);
  const topics = await api("/admin/topics");
  let filter = { topic: query.topic || "", q: query.q || "", status: query.status || "" };
  const tTitle = Object.fromEntries(topics.map((x) => [x.id, x.title]));
  const load = async () => {
    const qs = await api(`/admin/questions?${new URLSearchParams({ ...(filter.topic ? { topic_id: filter.topic } : {}), ...(filter.status ? { status: filter.status } : {}), q: filter.q })}`);
    $("#qlist").innerHTML = qs.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>ID</th><th>Topic</th><th>Skill</th><th>Prompt (English)</th><th>Level</th><th class="num">Answers</th><th class="num">Avg</th><th>State</th></tr></thead><tbody>
      ${qs.map((q) => `<tr class="click" tabindex="0" data-q="${esc(q.id)}"><td class="mono">${esc(q.id)}</td><td class="nowrap">${esc(tTitle[q.topic_id] || q.topic_id)}</td><td>${esc(q.skill)}</td><td>${esc(q.prompt.en)}</td><td>N${6 - q.difficulty}</td><td class="num">${q.answers}</td><td class="num">${scoreBadge(q.avg)}</td><td>${q.status === "draft" ? `<span class="badge warn">draft</span>` : q.active ? `<span class="badge ok">active</span>` : `<span class="badge plain">hidden</span>`}${q.origin === "factory" ? ` <span class="badge plain">factory</span>` : ""}</td></tr>`).join("")}</tbody></table></div>
      <p class="small muted" style="margin-top:8px">${qs.length} questions. Each student gets a different subset per session, chosen by the AIQ router.</p>`
      : `<div class="card empty"><h3>No questions match</h3><p>Change the filter or add a question.</p></div>`;
    $$("[data-q]").forEach((tr) => {
      const open = () => editor(qs.find((x) => x.id === tr.dataset.q));
      tr.onclick = open; tr.onkeydown = (e) => { if (e.key === "Enter") open(); };
    });
  };
  const editor = (q) => {
    const isNew = !q;
    q = q || { id: "", topic_id: filter.topic || topics[0].id, skill: "vocabulary", difficulty: 1, prompt: {}, keywords: [[]], model_answer: {}, probe: {}, active: true };
    const tri = (name, label, v, area = false) => `<fieldset style="border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin:0 0 14px"><legend class="f" style="padding:0 6px">${label}</legend>
      ${["en", "ne", "ja"].map((l) => `<div class="field" style="margin-bottom:8px"><label class="small muted" for="${name}_${l}">${{ en: "English", ne: "Nepali", ja: "Japanese" }[l]}</label>
      ${area ? `<textarea id="${name}_${l}" style="min-height:60px">${esc(v[l] || "")}</textarea>` : `<input id="${name}_${l}" type="text" value="${esc(v[l] || "")}">`}</div>`).join("")}</fieldset>`;
    const m = overlay(`<div class="row between" style="margin-bottom:16px"><h2>${isNew ? "New question" : `Edit ${esc(q.id)}`}</h2><button class="icon-btn" data-close aria-label="Close">${icon("x")}</button></div>
      <form id="qf">
        <div class="grid g3"><div class="field"><label class="f" for="qt">Topic</label><select id="qt">${topics.map((x) => `<option value="${x.id}" ${x.id === q.topic_id ? "selected" : ""}>${esc(x.title)}${x.kind === "interview" ? " (interview)" : ""}</option>`).join("")}</select></div>
        <div class="field"><label class="f" for="qs">Skill</label><input id="qs" type="text" list="skills" value="${esc(q.skill)}"><datalist id="skills">${[...SKILLS, "self_intro", "motivation", "japanese", "scenario", "culture"].map((s) => `<option value="${s}">`).join("")}</datalist></div>
        <div class="field"><label class="f" for="qd">Difficulty</label><select id="qd">${[1, 2, 3, 4, 5].map((d) => `<option value="${d}" ${d === q.difficulty ? "selected" : ""}>${d} · JLPT ${["", "N5", "N4", "N3", "N2", "N1"][d]}</option>`).join("")}</select></div></div>
        ${isNew ? `<div class="field"><label class="f" for="qid">ID (optional)</label><input id="qid" type="text" placeholder="auto"><p class="hint">Lowercase letters, numbers and _ only.</p></div>` : ""}
        ${tri("p", "Prompt", q.prompt, true)}
        <div class="field"><label class="f" for="kw">Keyword groups</label><textarea id="kw" style="min-height:90px">${esc(q.keywords.map((g) => g.join(", ")).join("\n"))}</textarea>
          <p class="hint">One line per idea the answer must contain; comma-separated alternatives in any language. Score = share of lines matched. The deterministic grader and the evals use these; the LLM uses the model answer.</p></div>
        ${tri("m", "Model answer", q.model_answer, true)}
        ${tri("r", "Socratic follow-up", q.probe)}
        <label class="switch" style="margin-bottom:16px"><input type="checkbox" id="qa" ${q.active ? "checked" : ""} style="--x:0"><span>Active (students can get it)</span></label>
        <p class="err" id="qe"></p>
        <div class="row"><button class="btn">${isNew ? "Create question" : "Save changes"}</button><span class="sp"></span>
          ${!isNew && q.status === "draft" ? `<button type="button" class="btn ghost" id="qpub">Publish draft</button><button type="button" class="btn danger" id="qdel">Delete draft</button>` : ""}</div>
        ${q.sources && q.sources.length ? `<p class="small muted" style="margin-top:10px">Generated from: ${q.sources.map((x) => `${esc(x.title)} (${esc(x.source)}, ${esc(x.license)})`).join("; ")}</p>` : ""}
      </form>
      ${isNew ? "" : `<section class="card" style="margin-top:18px"><h3>Test the deterministic grader</h3><div class="row" style="margin-top:10px;flex-wrap:nowrap"><input id="ta" type="text" placeholder="Type a sample answer"><button class="btn ghost" id="tb" type="button">Grade</button></div><p id="tr" class="small" style="margin-top:8px"></p></section>`}`);
    $("#qa", m.el).style.background = "";
    $("#qa", m.el).addEventListener("change", () => {});
    const collect = () => ({
      id: isNew ? ($("#qid").value.trim() || null) : undefined, topic_id: $("#qt").value, skill: $("#qs").value.trim(), difficulty: Number($("#qd").value),
      prompt: { en: $("#p_en").value, ne: $("#p_ne").value, ja: $("#p_ja").value },
      keywords: $("#kw").value.split("\n").map((l) => l.split(",").map((x) => x.trim()).filter(Boolean)).filter((g) => g.length),
      model_answer: { en: $("#m_en").value, ne: $("#m_ne").value, ja: $("#m_ja").value },
      probe: { en: $("#r_en").value, ne: $("#r_ne").value, ja: $("#r_ja").value }, active: $("#qa").checked,
    });
    $("#qf", m.el).onsubmit = async (e) => {
      e.preventDefault();
      try {
        const body = collect();
        const saved = await api(isNew ? "/admin/questions" : `/admin/questions/${q.id}`, { method: isNew ? "POST" : "PUT", body });
        m.close(); toast(isNew ? `Created ${saved.id}` : `Saved ${saved.id}`); load();
      } catch (err) { $("#qe").textContent = err.message; }
    };
    const qp = $("#qpub", m.el);
    if (qp) qp.onclick = async () => { await api(`/admin/questions/${q.id}/publish`, { method: "POST" }); m.close(); toast(`Published ${q.id}`); load(); };
    const qd = $("#qdel", m.el);
    if (qd) qd.onclick = async () => { await api(`/admin/questions/${q.id}`, { method: "DELETE" }); m.close(); toast(`Deleted ${q.id}`); load(); };
    const tb = $("#tb", m.el);
    if (tb) tb.onclick = async () => {
      try { const r = await api(`/admin/questions/${q.id}/test`, { method: "POST", body: { answer: $("#ta").value } }); $("#tr").innerHTML = `${scoreBadge(r.score)} ${esc(r.feedback)}`; }
      catch (err) { $("#tr").textContent = err.message; }
    };
  };
  page.innerHTML = `<div class="page-head"><div><h1>Question bank</h1><p>Trilingual questions stored in PostgreSQL with a pgvector embedding each. Edits re-embed automatically.</p></div><button class="btn" id="newq">${icon("plus")}New question</button></div>
    <form class="row" id="qflt" style="margin-bottom:14px"><select id="ft" class="inline" aria-label="Topic"><option value="">All topics</option>${topics.map((x) => `<option value="${x.id}" ${x.id === filter.topic ? "selected" : ""}>${esc(x.title)}</option>`).join("")}</select>
      <select id="fs" class="inline" aria-label="Status"><option value="">Any status</option><option value="published" ${filter.status === "published" ? "selected" : ""}>Published</option><option value="draft" ${filter.status === "draft" ? "selected" : ""}>Drafts</option></select>
      <input type="search" id="fq" class="inline" style="flex:1;min-width:200px" placeholder="Search id or text" value="${esc(filter.q)}" aria-label="Search"><button class="btn ghost">Filter</button></form>
    <div id="qlist"><div class="loading"><div class="spinner"></div></div></div>`;
  $("#qflt").onsubmit = (e) => {
    e.preventDefault(); filter = { topic: $("#ft").value, q: $("#fq").value, status: $("#fs").value };
    history.replaceState(history.state, "", `/admin/questions?${new URLSearchParams(filter)}`); load();
  };
  $("#newq").onclick = () => editor(null);
  await load();
}

// ======================================================================= agent runs
export async function agentsPage({ query }) {
  const page = shell({ nav: nav(), title: "Agent runs" });
  let status = query.status || "", graph = query.graph || "";
  const load = async () => {
    const runs = await api(`/admin/runs?limit=80${status ? `&status=${status}` : ""}${graph ? `&graph=${graph}` : ""}`);
    const box = $("#runs");
    if (!box) return;
    box.innerHTML = runs.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>Run</th><th>Graph</th><th>Student</th><th>Session</th><th>Status</th><th class="num">Steps</th><th class="num">Tokens</th><th class="num">Duration</th><th>When</th></tr></thead><tbody>
      ${runs.map((r) => `<tr class="click" tabindex="0" data-href="/admin/agents/${r.id}"><td class="mono">#${r.id}</td><td>${esc(r.graph)}</td><td>${esc(r.user_name || "–")}</td><td class="mono">${r.session_id ?? "–"}</td><td>${statusBadge(r.status)}</td><td class="num">${r.steps}</td><td class="num">${r.tokens}</td><td class="num">${r.duration_ms} ms</td><td class="nowrap">${ago(r.created_at)}</td></tr>`).join("")}</tbody></table></div>`
      : `<div class="card empty"><h3>No runs yet</h3><p>Runs appear here as students start sessions and answer questions.</p></div>`;
    rowsLink(box);
  };
  page.innerHTML = `<div class="page-head"><div><h1>Agent runs</h1><p>Every graph execution with each agent's step, timing and decision. Refreshes every 5 seconds.</p></div>
    <div class="row"><div class="seg" id="sg">${[["", "All"], ["ok", "OK"], ["blocked", "Blocked"], ["error", "Error"]].map(([v, l]) => `<button data-s="${v}" class="${v === status ? "on" : ""}">${l}</button>`).join("")}</div>
    <div class="seg" id="gg">${[["", "Any graph"], ["start_session", "Start"], ["answer", "Answer"]].map(([v, l]) => `<button data-g="${v}" class="${v === graph ? "on" : ""}">${l}</button>`).join("")}</div></div></div>
    <section class="card" style="margin-bottom:16px"><div class="row" style="gap:6px;flex-wrap:wrap">
      ${["Guardian", "Leveler", "AIQ Router", "Smriti", "Retriever", "Tutor", "Guardian", "Progress", "Smriti", "AIQ Router", "Certifier"].map((a, i, arr) => `<span class="badge ${i === 5 ? "" : "plain"}">${a}</span>${i < arr.length - 1 ? `<span class="muted">›</span>` : ""}`).join("")}
    </div><p class="small muted" style="margin-top:8px">Answer graph. Only the Tutor step may call an LLM, and only when the router allows it for the remaining budget.</p></section>
    <div id="runs"><div class="loading"><div class="spinner"></div></div></div>`;
  $$("[data-s]").forEach((b) => (b.onclick = () => { status = b.dataset.s; $$("[data-s]").forEach((x) => x.classList.toggle("on", x === b)); load(); }));
  $$("[data-g]").forEach((b) => (b.onclick = () => { graph = b.dataset.g; $$("[data-g]").forEach((x) => x.classList.toggle("on", x === b)); load(); }));
  await load();
  const timer = setInterval(() => { if (!document.hidden) load().catch(() => {}); }, 5000);
  current.cleanup = () => clearInterval(timer);
}

export async function runDetailPage({ params }) {
  const page = shell({ nav: nav(), title: `Run #${params.id}`, crumb: "Agent runs", back: "/admin/agents" });
  loading(page);
  const r = await api(`/admin/runs/${params.id}`);
  page.innerHTML = `<div class="page-head"><div><h1>${esc(r.graph)} run #${r.id}</h1><p>${fmtDate(r.created_at)} · ${esc(r.user_name || "–")} · ${r.duration_ms} ms · ${r.tokens} tokens</p></div>
    <div class="row">${statusBadge(r.status)}${r.session_id ? `<a class="btn ghost sm" href="/admin/sessions/${r.session_id}">Open session</a>` : ""}</div></div>
    <div class="split"><section class="card"><div class="card-head"><h2>Execution</h2></div>${traceHTML({ ...r, run_id: r.id, ms: r.duration_ms, events: r.events })}</section>
    <section class="card"><div class="card-head"><h2>Step detail</h2></div>${r.events.map((e) => `<details class="raw" style="margin-bottom:8px"><summary>${e.seq}. ${esc(e.agent)} · ${esc(e.node)}</summary><pre>${esc(JSON.stringify(e.detail, null, 2))}</pre></details>`).join("")}</section></div>`;
}

// ======================================================================= certificates
export async function certificatesPage() {
  const page = shell({ nav: nav(), title: "Certificates" });
  loading(page);
  const list = await api("/admin/certificates");
  page.innerHTML = `<div class="page-head"><div><h1>Certificates</h1><p>Signed with HMAC; anyone can check a code at /verify/&lt;code&gt;. Revoking makes the QR show “Revoked”.</p></div></div>
    ${list.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>Code</th><th>Student</th><th>Level</th><th class="num">Overall</th><th class="num">Interview</th><th>Issued</th><th>Status</th><th></th></tr></thead><tbody>
    ${list.map((c) => `<tr><td class="mono"><a href="/verify/${esc(c.code)}">${esc(c.code)}</a></td><td>${esc(c.name)}<div class="small muted">${esc(c.email)}</div></td><td>${esc(c.level || "–")}</td><td class="num">${pct(c.scores.overall)}</td><td class="num">${pct(c.scores.interview)}</td><td class="nowrap">${fmtDate(c.issued_at, false)}</td>
      <td>${c.revoked ? `<span class="badge bad">revoked</span>` : `<span class="badge ok">valid</span>`}</td><td><button class="btn ghost sm" data-code="${esc(c.code)}" data-rev="${c.revoked ? "0" : "1"}">${c.revoked ? "Restore" : "Revoke"}</button></td></tr>`).join("")}</tbody></table></div>`
    : `<div class="card empty"><h3>No certificates issued yet</h3><p>Students claim one after passing every topic and a mock interview.</p></div>`}`;
  $$("[data-code]").forEach((b) => (b.onclick = async () => {
    const rev = b.dataset.rev === "1";
    if (rev && !(await confirmBox(`Revoke ${b.dataset.code}? The verification page will show it as revoked.`, { ok: "Revoke", danger: true }))) return;
    try { await api(`/admin/certificates/${b.dataset.code}`, { method: "PATCH", body: { revoked: rev } }); toast(rev ? "Revoked" : "Restored"); certificatesPage(); } catch (e) { toast(e.message, true); }
  }));
}

// ======================================================================= institutes
export async function orgsPage() {
  const page = shell({ nav: nav(), title: "Institutes" });
  loading(page);
  const orgs = await api("/admin/orgs");
  page.innerHTML = `<div class="page-head"><div><h1>Institutes</h1><p>Language institutes, manpower companies or batches. Students pick one at sign-up; filter by it in Students.</p></div></div>
    <div class="split"><div>${orgs.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>Name</th><th class="num">Students</th><th>Created</th></tr></thead><tbody>
      ${orgs.map((o) => `<tr class="click" tabindex="0" data-href="/admin/students?org=${o.id}"><td><b>${esc(o.name)}</b></td><td class="num">${o.students}</td><td>${fmtDate(o.created_at, false)}</td></tr>`).join("")}</tbody></table></div>` : `<div class="card empty"><h3>No institutes yet</h3></div>`}</div>
    <section class="card"><h2 style="margin-bottom:12px">Add institute</h2><form id="of"><div class="field"><label class="f" for="on">Name</label><input id="on" type="text" required minlength="2"></div><p class="err" id="oe"></p><button class="btn">Add institute</button></form></section></div>`;
  rowsLink(page);
  $("#of").onsubmit = async (e) => {
    e.preventDefault();
    try { await api("/admin/orgs", { method: "POST", body: { name: $("#on").value } }); toast("Institute added"); orgsPage(); } catch (err) { $("#oe").textContent = err.message; }
  };
}

// ======================================================================= settings
export async function settingsPage() {
  const page = shell({ nav: nav(), title: "Settings" });
  loading(page);
  const [s, obs] = await Promise.all([api("/admin/settings"), api("/admin/observability")]);
  const W = [["w_gap", "Learning gap weight", "How much a low score pulls a topic forward."], ["w_novelty", "Novelty weight", "Preference for questions the student has not seen."],
    ["w_spacing", "Review-due weight", "Spaced repetition: topics not practised for a while."], ["lambda_cost", "λ cost", "Penalty for sessions that use a large share of the remaining budget."],
    ["lambda_repeat", "λ repeat", "Penalty for repeating the topic of the previous session."], ["lambda_fit", "λ level fit", "Penalty for difficulty far from the student's level."]];
  page.innerHTML = `<div class="page-head"><div><h1>Settings</h1><p>Stored in PostgreSQL and applied immediately to every agent. Changes are written to the audit log.</p></div></div>
    <div class="grid g2"><div>
      <section class="card"><div class="card-head"><div><h2>Kill switch</h2><p>Pause every tutor and interview call for all students.</p></div></div>
        <label class="switch"><input type="checkbox" id="kill" ${s.kill_switch ? "checked" : ""}><span>${s.kill_switch ? "Tutor paused" : "Tutor running"}</span></label></section>
      <section class="card"><h2 style="margin-bottom:14px">Guardrails and thresholds</h2><form id="gf">
        <div class="grid g2">
          <div class="field"><label class="f" for="s1">Daily token budget per student</label><input id="s1" type="number" min="0" step="500" value="${s.daily_token_budget}"></div>
          <div class="field"><label class="f" for="s7">LLM routing floor</label><input id="s7" type="number" min="0" max="1" step="0.05" value="${s.llm_min_budget_share}"><p class="hint">Below this share of budget left, grading uses the deterministic grader.</p></div>
          <div class="field"><label class="f" for="s2">Questions per practice session</label><input id="s2" type="number" min="1" max="10" value="${s.session_questions}"></div>
          <div class="field"><label class="f" for="s3">Questions per interview</label><input id="s3" type="number" min="1" max="10" value="${s.interview_questions}"></div>
          <div class="field"><label class="f" for="s4">Interview pass mark</label><input id="s4" type="number" min="0" max="1" step="0.05" value="${s.interview_pass}"></div>
          <div class="field"><label class="f" for="s5">Certificate: min mastery per topic</label><input id="s5" type="number" min="0" max="1" step="0.05" value="${s.cert_min_mastery}"></div>
          <div class="field"><label class="f" for="s6">Certificate: min answers per topic</label><input id="s6" type="number" min="0" max="50" value="${s.cert_min_attempts}"></div>
        </div><button class="btn">Save guardrails</button></form></section>
      <section class="card"><div class="card-head"><div><h2>LangSmith tracing</h2><p>Every LangGraph run, OpenAI call, retrieval and Leveler call is traced when enabled.</p></div>
        ${obs.langsmith.enabled ? `<span class="badge ok">on</span>` : `<span class="badge plain">off</span>`}</div>
        <p class="small">${obs.langsmith.enabled ? `Project <b>${esc(obs.langsmith.project)}</b> · <a href="${esc(obs.langsmith.url)}" target="_blank" rel="noopener">open LangSmith</a>` : `Set <code>LANGSMITH_TRACING=true</code>, <code>LANGSMITH_API_KEY</code> and optionally <code>LANGSMITH_PROJECT</code> on the server, then restart.`}</p>
        <p class="small muted" style="margin-top:6px">LLM: ${esc(obs.llm)}${obs.llm_model ? " (" + esc(obs.llm_model) + ")" : ""} · embeddings: ${esc(obs.embedder)}</p></section>
      <section class="card"><h2 style="margin-bottom:14px">Your admin password</h2><form id="apf">
        <div class="field"><label class="f" for="ap1">Current password</label><input id="ap1" type="password" autocomplete="current-password"></div>
        <div class="field"><label class="f" for="ap2">New password</label><input id="ap2" type="password" autocomplete="new-password" minlength="8"></div>
        <p class="err" id="ape"></p><button class="btn ghost">Change password</button></form></section>
    </div>
    <section class="card"><div class="card-head"><div><h2>AIQ router</h2><p>Topic choice maximises L = NB(t) − Σ λk·Ck(t). Deterministic: same inputs, same decision.</p></div></div>
      <form id="rf">${W.map(([k, l, h]) => `<div class="field"><div class="row between"><label class="f" for="w_${k}">${l}</label><b id="v_${k}">${Number(s.router[k]).toFixed(2)}</b></div>
        <input type="range" id="w_${k}" min="0" max="1" step="0.05" value="${s.router[k]}"><p class="hint">${h}</p></div>`).join("")}
      <button class="btn">Save router weights</button></form></section></div>`;
  const save = async (body, msg) => { try { await api("/admin/settings", { method: "PUT", body }); toast(msg); } catch (e) { toast(e.message, true); } };
  $("#kill").onchange = async (e) => {
    const on = e.target.checked;
    if (on && !(await confirmBox("Pause the tutor for every student?", { ok: "Pause tutor", danger: true }))) { e.target.checked = false; return; }
    await save({ kill_switch: on }, on ? "Tutor paused" : "Tutor running");
    e.target.nextElementSibling.textContent = on ? "Tutor paused" : "Tutor running";
  };
  $("#gf").onsubmit = (e) => {
    e.preventDefault();
    save({ daily_token_budget: Number($("#s1").value), session_questions: Number($("#s2").value), interview_questions: Number($("#s3").value),
      interview_pass: Number($("#s4").value), cert_min_mastery: Number($("#s5").value), cert_min_attempts: Number($("#s6").value), llm_min_budget_share: Number($("#s7").value) }, "Guardrails saved");
  };
  $("#apf").onsubmit = async (e) => {
    e.preventDefault(); $("#ape").textContent = "";
    try { await api("/me/password", { method: "POST", body: { current: $("#ap1").value, new: $("#ap2").value } }); toast("Password changed"); e.target.reset(); }
    catch (err) { $("#ape").textContent = err.message; }
  };
  W.forEach(([k]) => { $(`#w_${k}`).oninput = (e) => { $(`#v_${k}`).textContent = Number(e.target.value).toFixed(2); }; });
  $("#rf").onsubmit = (e) => { e.preventDefault(); save({ router: Object.fromEntries(W.map(([k]) => [k, Number($(`#w_${k}`).value)])) }, "Router weights saved"); };
}

// ======================================================================= audit
export async function auditPage() {
  const page = shell({ nav: nav(), title: "Audit log" });
  loading(page);
  const rows = await api("/admin/audit");
  page.innerHTML = `<div class="page-head"><div><h1>Audit log</h1><p>Every admin change: who, what and when.</p></div></div>
    ${rows.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>When</th><th>Admin</th><th>Action</th><th>Target</th><th>Detail</th></tr></thead><tbody>
    ${rows.map((a) => `<tr><td class="nowrap">${fmtDate(a.created_at)}</td><td>${esc(a.actor || "–")}</td><td><span class="badge plain">${esc(a.action)}</span></td><td class="mono">${esc(a.target || "–")}</td><td class="small mono">${esc(JSON.stringify(a.detail))}</td></tr>`).join("")}</tbody></table></div>`
    : `<div class="card empty"><h3>Nothing yet</h3><p>Admin actions will be listed here.</p></div>`}`;
}
