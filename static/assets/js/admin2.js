// Admin: knowledge base, JLPT level model, Course Factory.
import { $, $$, ago, api, confirmBox, current, esc, fmtDate, icon, loading, navigate, pct, shell, toast, traceHTML } from "./core.js";
import { adminNav as nav } from "./admin.js";
import { levelResultHTML } from "./learn.js";

const LEVELS = ["N5", "N4", "N3", "N2", "N1"];
const KAGGLE = ["celineboutinon/jlpt-master-vocabulary-library-n5-n1", "robinpourtaud/jlpt-words-by-level", "balankdharan7/jlpt-n4-japanese-english-vocabulary-and-more"];
const statusBadge = (s) => `<span class="badge ${s === "done" ? "ok" : s === "error" ? "bad" : ""}">${esc(s)}</span>`;

// ======================================================================= knowledge base
const SOURCES = [
  ["bundled", "JLPT vocabulary, kanji and grammar", "7.9k words, 2.2k kanji and 50 grammar notes for N5–N1, shipped with the app (MIT / CC BY-SA). Re-run to refresh embeddings.", ""],
  ["curriculum", "Course content", "Lesson model answers, vocabulary and handbook notes from the tutor's own topics.", ""],
  ["tatoeba", "Tatoeba example sentences", "Downloads Japanese sentences (and English translations), levels each one with the trained Leveler and keeps a balanced sample per level. CC BY 2.0 FR.", "per_level"],
  ["wikipedia", "Wikipedia articles", "Articles on the JLPT, Japanese grammar, keigo, kanji and caregiving in Japan (EN + JA), split into chunks. CC BY-SA 4.0.", ""],
  ["kaggle", "Kaggle datasets", "Reads CSV and JSON files: word / reading / meaning / level columns (N5 or 5→1), romaji, and example sentences. Words already in the JLPT lists are merged, not duplicated. Uses kagglehub; set KAGGLE_USERNAME and KAGGLE_KEY if a download asks for login.", "datasets"],
  ["nepali", "Add Nepali meanings", "Translates English meanings of vocabulary and kanji into Nepali with the LLM, easiest level first (up to 2,000 per run). Needs OPENAI_API_KEY.", ""],
  ["retrain", "Retrain the Leveler", "Retrains the JLPT level classifier on the bundled lists plus ingested Tatoeba and Kaggle rows, then activates the new version.", ""],
];

export async function kbPage() {
  const page = shell({ nav: nav(), title: "Knowledge base" });
  loading(page);
  const draw = async () => {
    const [stats, runs, obs] = await Promise.all([api("/kb/stats"), api("/admin/kb/runs"), api("/admin/observability")]);
    const grid = {};
    stats.rows.forEach((r) => { grid[r.level] = grid[r.level] || {}; grid[r.level][r.kind] = (grid[r.level][r.kind] || 0) + r.n; });
    const kinds = [...new Set(stats.rows.map((r) => r.kind))].sort();
    const levels = [...LEVELS, "general"].filter((l) => grid[l]);
    const sources = {};
    stats.rows.forEach((r) => { sources[r.source] = (sources[r.source] || 0) + r.n; });
    const running = runs.some((r) => r.status === "running");
    if (!$("#kbwrap")) {
      page.innerHTML = `<div class="page-head"><div><h1>Knowledge base</h1><p>Five-level corpus in PostgreSQL + pgvector (${esc(obs.embedder)} embeddings). Every document keeps its source and licence; retrieval filters by the student's level.</p></div></div><div id="kbwrap"></div>`;
    }
    $("#kbwrap").innerHTML = `
      <div class="grid g4" style="margin-bottom:16px">
        <div class="stat"><div class="k">Documents</div><div class="v">${stats.total.toLocaleString()}</div><div class="d">${Object.keys(sources).length} sources</div></div>
        ${LEVELS.slice(0, 3).map((l) => `<div class="stat"><div class="k">JLPT ${l}</div><div class="v">${Object.values(grid[l] || {}).reduce((a, b) => a + b, 0).toLocaleString()}</div><div class="d">documents</div></div>`).join("")}
      </div>
      <div class="split"><div>
        <section class="card"><div class="card-head"><h2>Coverage by level</h2></div>
          <div class="table-wrap"><table class="t"><thead><tr><th>Level</th>${kinds.map((k) => `<th class="num">${esc(k)}</th>`).join("")}<th class="num">Total</th></tr></thead><tbody>
          ${levels.map((l) => `<tr><td><b>${esc(l)}</b></td>${kinds.map((k) => `<td class="num">${(grid[l][k] || 0).toLocaleString()}</td>`).join("")}<td class="num"><b>${Object.values(grid[l]).reduce((a, b) => a + b, 0).toLocaleString()}</b></td></tr>`).join("")}
          </tbody></table></div>
          <p class="small muted" style="margin-top:10px">${stats.nepali.toLocaleString()} words and kanji have a Nepali meaning.</p></section>
        <section class="card"><div class="card-head"><h2>Sources and licences</h2></div><div class="table-wrap"><table class="t"><thead><tr><th>Source</th><th>Licence</th><th class="num">Documents</th></tr></thead><tbody>
          ${stats.licenses.map((l) => `<tr><td>${esc(l.source)}</td><td class="small">${esc(l.license)}${l.noncommercial ? ` <span class="badge bad">non-commercial</span>` : ""}</td><td class="num">${l.n.toLocaleString()}</td></tr>`).join("")}</tbody></table></div></section>
        <section class="card"><div class="card-head"><h2>Ingestion jobs</h2>${running ? `<span class="badge">running</span>` : ""}</div>
          ${runs.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>#</th><th>Source</th><th>Status</th><th class="num">Added</th><th>Started</th><th>Log</th></tr></thead><tbody>
          ${runs.map((r) => `<tr><td class="mono">${r.id}</td><td>${esc(r.source)}</td><td>${statusBadge(r.status)}</td><td class="num">${(r.added || 0).toLocaleString()}</td><td class="nowrap">${ago(r.started_at)}</td>
            <td><details class="raw"><summary>view</summary><pre>${esc(r.message || "")}</pre></details></td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">No jobs yet.</p>`}</section>
      </div><div>
        ${SOURCES.map(([key, title, desc, opt]) => `<section class="card"><h3>${esc(title)}</h3><p class="small muted" style="margin:6px 0 10px">${esc(desc)}</p>
          ${opt === "per_level" ? `<div class="field"><label class="f small" for="o_${key}">Sentences per level</label><input id="o_${key}" type="number" value="1500" min="50" max="10000"></div>` : ""}
          ${opt === "datasets" ? `<div class="field"><label class="f small" for="o_${key}">Datasets (owner/slug, comma separated)</label><textarea id="o_${key}" style="min-height:70px" class="mono">${KAGGLE.join(",\n")}</textarea>
            <p class="hint">celineboutinon (CC BY-SA 4.0) is fine for commercial use. robinpourtaud (CC BY-NC) and balankdharan7 (CC BY-NC-SA) are non-commercial: they are imported and flagged, and left out of model training unless ALLOW_NC_TRAINING=true.</p></div>` : ""}
          <button class="btn sm ${key === "retrain" ? "" : "ghost"}" data-src="${key}" ${running ? "disabled" : ""}>${key === "retrain" ? "Retrain model" : "Ingest"}</button></section>`).join("")}
      </div></div>`;
    $$("[data-src]").forEach((b) => (b.onclick = async () => {
      const src = b.dataset.src;
      const body = { source: src };
      if (src === "tatoeba") body.per_level = Number($(`#o_${src}`).value);
      if (src === "kaggle") { body.datasets = $(`#o_${src}`).value.replace(/\s+/g, ""); if (!body.datasets) { toast("Enter at least one Kaggle dataset.", true); return; } }
      try { await api("/admin/kb/ingest", { method: "POST", body }); toast(`Started ${src}`); setTimeout(draw, 800); } catch (e) { toast(e.message, true); }
    }));
    return running;
  };
  await draw();
  const timer = setInterval(async () => { if (!document.hidden) { try { await draw(); } catch { /* ignore */ } } }, 4000);
  current.cleanup = () => clearInterval(timer);
}

// ======================================================================= model
export async function modelPage() {
  const page = shell({ nav: nav(), title: "Level model" });
  loading(page);
  const m = await api("/admin/model");
  const met = (m.active && m.active.metrics) || {};
  const cm = met.confusion || [];
  const maxRow = cm.map((r) => Math.max(1, r.reduce((a, b) => a + b, 0)));
  page.innerHTML = `<div class="page-head"><div><h1>JLPT level model</h1><p>Character n-gram softmax classifier (numpy) combined with the N5–N1 lexicon. Used by the Leveler agent to level student answers, Tatoeba/Wikipedia/Kaggle documents and Course Factory drafts.</p></div>
      <a class="btn" href="/admin/kb">${icon("db")}Retrain from Knowledge base</a></div>
    <div class="grid g4" style="margin-bottom:16px">
      <div class="stat"><div class="k">Active version</div><div class="v">v${m.active.version}</div><div class="d">${esc(m.active.source)} · ${m.active.trained_at ? fmtDate(m.active.trained_at) : "–"}</div></div>
      <div class="stat"><div class="k">Word-level accuracy</div><div class="v">${pct(met.accuracy)}</div><div class="d">majority baseline ${pct(met.majority_baseline)} · macro-F1 ${met.macro_f1 ?? "–"}</div></div>
      <div class="stat"><div class="k">Within one level</div><div class="v">${pct(met.within_one)}</div><div class="d">held-out ${met.n ?? "–"} items</div></div>
      <div class="stat"><div class="k">Sentence accuracy</div><div class="v">${pct(met.sentence_eval && met.sentence_eval.accuracy)}</div><div class="d">within one: ${pct(met.sentence_eval && met.sentence_eval.within_one)} (n=${met.sentence_eval ? met.sentence_eval.n : "–"})</div></div>
    </div>
    <div class="split"><div>
      <section class="card"><div class="card-head"><div><h2>Confusion matrix</h2><p>Rows: true level · columns: predicted (held-out words, kanji and sentences).</p></div></div>
        ${cm.length ? `<div style="overflow-x:auto"><table class="cm"><thead><tr><th></th>${LEVELS.map((l) => `<th>${l}</th>`).join("")}</tr></thead><tbody>
        ${cm.map((row, i) => `<tr><th>${LEVELS[i]}</th>${row.map((v, j) => `<td style="background:color-mix(in srgb, ${i === j ? "var(--strong)" : "var(--weak)"} ${Math.round((v / maxRow[i]) * 85)}%, transparent);${v / maxRow[i] > 0.45 ? "color:#fff" : ""}">${v}</td>`).join("")}</tr>`).join("")}
        </tbody></table></div>` : `<p class="muted">No metrics.</p>`}
        <p class="small muted" style="margin-top:10px">Training data: ${esc((met.sources || []).join(", "))} · ${Number(met.train_size || 0).toLocaleString()} examples · ${met.epochs ?? "–"} epochs. Single words are hard to level from characters alone; sentences use the lexicon and score higher.</p></section>
      <section class="card"><div class="card-head"><h2>Versions</h2></div>${m.versions.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>Version</th><th>Trained</th><th class="num">Accuracy</th><th class="num">Within one</th><th class="num">Examples</th><th></th></tr></thead><tbody>
        ${m.versions.map((v) => `<tr><td>v${v.version} ${v.active ? `<span class="badge ok">active</span>` : ""}</td><td>${fmtDate(v.trained_at)}</td><td class="num">${pct(Number(v.accuracy))}</td><td class="num">${pct(Number(v.within_one))}</td><td class="num">${Number(v.train_size || 0).toLocaleString()}</td>
          <td>${v.active ? "" : `<button class="btn ghost sm" data-v="${v.version}">Activate</button>`}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">Only the bundled model so far. Retrain after ingesting Tatoeba or Kaggle data.</p>`}</section>
    </div><section class="card"><h2 style="margin-bottom:10px">Try it</h2><textarea id="mt" class="jp" placeholder="日本語の文を入力…" style="min-height:90px">その発言は誤解を招きかねない。</textarea>
      <button class="btn" id="mb" style="margin-top:10px">Estimate level</button><div id="mr" style="margin-top:12px"></div></section></div>`;
  $("#mb").onclick = async () => { try { $("#mr").innerHTML = levelResultHTML(await api("/admin/model/predict", { method: "POST", body: { text: $("#mt").value } })); } catch (e) { toast(e.message, true); } };
  $$("[data-v]").forEach((b) => (b.onclick = async () => { try { await api(`/admin/model/activate/${b.dataset.v}`, { method: "POST" }); toast(`Activated v${b.dataset.v}`); modelPage(); } catch (e) { toast(e.message, true); } }));
}

// ======================================================================= course factory
export async function factoryPage() {
  const page = shell({ nav: nav(), title: "Course factory" });
  loading(page);
  const [topics, obs, drafts] = await Promise.all([api("/admin/topics"), api("/admin/observability"), api("/admin/questions?status=draft")]);
  const practice = topics.filter((t) => t.kind === "practice");
  page.innerHTML = `<div class="page-head"><div><h1>Course factory</h1><p>Agents write new questions from the knowledge base: Retriever → Generator (${esc(obs.llm)}) → Leveler check → QA (keywords, duplicates) → saved as drafts. Nothing reaches students until you publish it.</p></div></div>
    <div class="split"><div>
      <section class="card"><form id="ff" class="grid g2">
        <div class="field"><label class="f" for="ft">Topic</label><select id="ft">${practice.map((t) => `<option value="${esc(t.id)}">${esc(t.title)}</option>`).join("")}</select></div>
        <div class="field"><label class="f" for="fl">Level</label><select id="fl"><option value="">Topic default</option>${LEVELS.map((l) => `<option>${l}</option>`).join("")}</select></div>
        <div class="field"><label class="f" for="fc">How many</label><input id="fc" type="number" min="1" max="10" value="5"></div>
        <div class="field"><label class="f" for="ffo">Focus</label><select id="ffo"><option value="mixed">Mixed</option><option value="vocab">Vocabulary & kanji</option><option value="grammar">Grammar</option></select></div>
        <div><button class="btn" id="fg">${icon("spark")}Generate drafts</button></div>
      </form>${obs.llm === "mock" ? `<p class="small muted" style="margin-top:8px">No LLM key set: drafts are written from templates. Set OPENAI_API_KEY for richer, trilingual questions.</p>` : ""}</section>
      <div id="fout"></div>
      <section class="card"><div class="card-head"><h2>Drafts waiting for review</h2><a class="small" href="/admin/questions?status=draft">Open in question bank</a></div><div id="dl"></div></section>
    </div><section class="card"><div class="card-head"><h2>Last run</h2></div><div id="ftr"><p class="muted small">–</p></div></section></div>`;
  const drawDrafts = (list) => {
    $("#dl").innerHTML = list.length ? `<div class="table-wrap"><table class="t"><thead><tr><th>ID</th><th>Prompt</th><th>Level</th><th></th></tr></thead><tbody>
      ${list.map((q) => `<tr><td class="mono">${esc(q.id)}</td><td class="jp">${esc(q.prompt.en)}</td><td>N${6 - q.difficulty}</td>
        <td class="nowrap"><button class="btn sm" data-pub="${esc(q.id)}">Publish</button> <button class="btn ghost sm" data-del="${esc(q.id)}">Delete</button></td></tr>`).join("")}</tbody></table></div>`
      : `<p class="muted">No drafts.</p>`;
    $$("[data-pub]").forEach((b) => (b.onclick = async () => { await api(`/admin/questions/${b.dataset.pub}/publish`, { method: "POST" }); toast(`Published ${b.dataset.pub}`); drawDrafts(await api("/admin/questions?status=draft")); }));
    $$("[data-del]").forEach((b) => (b.onclick = async () => { if (!(await confirmBox(`Delete draft ${b.dataset.del}?`, { ok: "Delete", danger: true }))) return; await api(`/admin/questions/${b.dataset.del}`, { method: "DELETE" }); drawDrafts(await api("/admin/questions?status=draft")); }));
  };
  drawDrafts(drafts);
  $("#ff").onsubmit = async (e) => {
    e.preventDefault();
    $("#fg").disabled = true;
    $("#fout").innerHTML = `<div class="card"><div class="loading"><div class="spinner"></div></div></div>`;
    try {
      const r = await api("/admin/factory", { method: "POST", body: { topic_id: $("#ft").value, count: Number($("#fc").value), focus: $("#ffo").value, level: $("#fl").value || null } });
      $("#ftr").innerHTML = traceHTML(r.trace, { anim: true });
      $("#fout").innerHTML = `<section class="card"><div class="card-head"><h2>${r.drafts.length} new drafts at JLPT ${esc(r.level)}</h2></div>${r.drafts.map((d) => `<div class="check ${d.level_check && d.level_check.ok ? "ok" : "no"}">${icon(d.level_check && d.level_check.ok ? "check" : "circle")}<div><b class="mono">${esc(d.id)}</b> <span class="jp">${esc(d.prompt)}</span><div class="small muted">Leveler: ${esc((d.level_check || {}).estimated || "–")} for target ${esc((d.level_check || {}).target || "–")}</div></div></div>`).join("") || `<p class="muted">Nothing passed QA. Try another level or focus.</p>`}</section>`;
      drawDrafts(await api("/admin/questions?status=draft"));
    } catch (err) { $("#fout").innerHTML = ""; toast(err.message, true); }
    $("#fg").disabled = false;
  };
}
