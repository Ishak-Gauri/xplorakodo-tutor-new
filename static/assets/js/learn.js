// Student: Ask Sensei (level-aware RAG chat) and the Library (five-level knowledge base).
import { $, $$, api, auth, esc, fmtDate, icon, lang, loading, shell, t, toast, traceHTML, confirmBox } from "./core.js";

const D = {
  en: { ask: "Ask Sensei", ask_sub: "Ask anything about Japanese, the JLPT or caregiving. Answers use the knowledge base at your level and show their sources.",
    ph: "e.g. What is the difference between は and が?  /  How do I use ～てもいいですか?", send: "Ask", thinking: "Sensei is looking it up…", clear: "Clear chat",
    clear_q: "Delete this conversation?", empty: "Start with a question. Try one of these:", sources: "Sources", follow: "Think about it", your_levels: "Answering at levels",
    library: "Library", lib_sub: "Every JLPT level in one place: vocabulary, kanji, grammar, example sentences and articles, each with its source and licence.",
    all: "All", search: "Search", semantic: "Meaning search", results: "{n} items", none: "Nothing found. Try another word or level.",
    check: "Check the level of any Japanese text", check_ph: "Paste a Japanese sentence…", check_btn: "Check level", estimated: "Estimated level",
    hardest: "Hardest words", prev: "Previous", next: "Next",
    kinds: { vocab: "Vocabulary", kanji: "Kanji", grammar: "Grammar", sentence: "Sentences", article: "Articles", lesson: "Lessons", handbook: "Handbook" },
    samples: ["What does 経験 mean? Give an example.", "Explain ～たことがあります with a caregiving example.", "How do I politely ask a resident to sit down?", "Which kanji should I learn first for N5?"] },
  ne: { ask: "सेन्सेईलाई सोध्नुहोस्", ask_sub: "जापानी, JLPT वा केयरगिभिङबारे जे पनि सोध्नुहोस्। उत्तर तपाईंको स्तरको ज्ञानकोषबाट आउँछ र स्रोत देखाउँछ।",
    ph: "जस्तै: は र が मा के फरक छ?", send: "सोध्नुहोस्", thinking: "सेन्सेई खोज्दै हुनुहुन्छ…", clear: "च्याट मेटाउनुहोस्",
    clear_q: "यो कुराकानी मेटाउने?", empty: "प्रश्नबाट सुरु गर्नुहोस्। यी प्रयास गर्नुहोस्:", sources: "स्रोतहरू", follow: "सोचेर हेर्नुहोस्", your_levels: "उत्तरको स्तर",
    library: "पुस्तकालय", lib_sub: "सबै JLPT स्तर एकै ठाउँमा: शब्द, कान्जी, व्याकरण, उदाहरण वाक्य र लेख, स्रोत र लाइसेन्ससहित।",
    all: "सबै", search: "खोज्नुहोस्", semantic: "अर्थअनुसार खोज", results: "{n} वटा", none: "केही भेटिएन। अर्को शब्द वा स्तर प्रयास गर्नुहोस्।",
    check: "कुनै पनि जापानी पाठको स्तर जाँच्नुहोस्", check_ph: "जापानी वाक्य टाँस्नुहोस्…", check_btn: "स्तर जाँच्नुहोस्", estimated: "अनुमानित स्तर",
    hardest: "कठिन शब्दहरू", prev: "अघिल्लो", next: "अर्को",
    kinds: { vocab: "शब्दावली", kanji: "कान्जी", grammar: "व्याकरण", sentence: "वाक्य", article: "लेख", lesson: "पाठ", handbook: "पुस्तिका" },
    samples: ["経験 को अर्थ के हो? उदाहरण दिनुहोस्।", "～たことがあります केयरगिभिङ उदाहरणसहित बुझाउनुहोस्।", "बासिन्दालाई नम्र रूपमा बस्न कसरी भन्ने?", "N5 का लागि पहिले कुन कान्जी सिक्ने?"] },
  ja: { ask: "先生に質問", ask_sub: "日本語・JLPT・介護について何でも聞いてください。あなたのレベルの資料から答え、出典を示します。",
    ph: "例：「は」と「が」の違いは？", send: "質問する", thinking: "先生が調べています…", clear: "チャットを消す",
    clear_q: "この会話を削除しますか？", empty: "質問から始めましょう。例：", sources: "出典", follow: "考えてみましょう", your_levels: "回答レベル",
    library: "ライブラリー", lib_sub: "JLPTの全レベルの語彙・漢字・文法・例文・記事を、出典とライセンス付きで。",
    all: "すべて", search: "検索", semantic: "意味で検索", results: "{n}件", none: "見つかりません。別のことばやレベルで試してください。",
    check: "日本語のレベルをチェック", check_ph: "日本語の文を貼り付けてください…", check_btn: "レベルを判定", estimated: "推定レベル",
    hardest: "むずかしい語", prev: "前へ", next: "次へ",
    kinds: { vocab: "語彙", kanji: "漢字", grammar: "文法", sentence: "例文", article: "記事", lesson: "レッスン", handbook: "ハンドブック" },
    samples: ["「経験」の意味と例文を教えて。", "「～たことがあります」を介護の例で説明して。", "入居者に座ってもらう丁寧な言い方は？", "N5ではどの漢字から覚えるべき？"] },
};
const tt = (k, v = {}) => { const d = D[lang()] || D.en; const s = k.split(".").reduce((o, x) => (o ? o[x] : undefined), d) ?? k.split(".").reduce((o, x) => (o ? o[x] : undefined), D.en); return typeof s === "string" ? s.replace(/\{(\w+)\}/g, (_, x) => v[x] ?? "") : s; };

const nav = () => [
  { href: "/app", icon: "home", label: t("dashboard"), exact: true },
  { href: "/app/learn", icon: "book", label: t("learn") },
  { href: "/app/ask", icon: "spark", label: tt("ask") },
  { href: "/app/library", icon: "db", label: tt("library") },
  { href: "/app/interview", icon: "mic", label: t("interview") },
  { href: "/app/progress", icon: "chart", label: t("progress") },
  { href: "/app/certificate", icon: "award", label: t("certificate") },
  { href: "/app/profile", icon: "user", label: t("profile") },
];
export const studentNav = nav;

export function md(text) {
  // tiny, safe markdown: escape first, then bold, code, lists, citations, line breaks
  let h = esc(text || "");
  h = h.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  h = h.replace(/\[(\d{1,2})\]/g, '<sup class="cite">[$1]</sup>');
  const lines = h.split(/\n/);
  let out = "", inList = false;
  for (const ln of lines) {
    const m = ln.match(/^\s*[-*•]\s+(.*)/) || ln.match(/^\s*\d+\.\s+(.*)/);
    if (m) { if (!inList) { out += "<ul>"; inList = true; } out += `<li>${m[1]}</li>`; continue; }
    if (inList) { out += "</ul>"; inList = false; }
    out += ln.trim() ? `<p>${ln}</p>` : "";
  }
  return out + (inList ? "</ul>" : "");
}

const levelBadge = (lv) => `<span class="badge ${lv ? "" : "plain"}">${esc(lv || "general")}</span>`;

function citeHTML(c) {
  return `<div class="cite-card"><div class="row between"><b class="jp">${esc(c.title)}</b><span class="row" style="gap:6px">${levelBadge(c.level)}<span class="badge plain">${esc(c.kind)}</span></span></div>
    <div class="small jp" style="margin-top:4px">${esc(c.text)}</div>
    <div class="small muted" style="margin-top:4px">[${c.n}] ${esc(c.source)} · ${c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.license)}</a>` : esc(c.license)}</div></div>`;
}

// ======================================================================= Ask Sensei
export async function askPage() {
  const page = shell({ nav: nav(), title: tt("ask") });
  loading(page);
  const hist = await api("/ask/history");
  let lastTrace = null;
  const draw = (msgs) => {
    page.innerHTML = `<div class="room"><div>
      <div class="page-head"><div><h1>${esc(tt("ask"))}</h1><p>${esc(tt("ask_sub"))}</p></div>${msgs.length ? `<button class="btn ghost sm" id="clr">${esc(tt("clear"))}</button>` : ""}</div>
      <section class="card chat" id="chat">${msgs.length ? msgs.map(msgHTML).join("") : `<div class="empty" style="padding:20px"><p>${esc(tt("empty"))}</p>
        <div class="stack" style="margin-top:12px">${tt("samples").map((x) => `<button class="opt sample jp" data-q="${esc(x)}">${esc(x)}</button>`).join("")}</div></div>`}
        <div id="pending"></div></section>
      <form id="askf" class="card" style="margin-top:12px"><label class="sr" for="q">${esc(tt("ph"))}</label>
        <textarea id="q" class="jp" placeholder="${esc(tt("ph"))}" maxlength="1500" style="min-height:80px"></textarea>
        <div class="row" style="margin-top:10px"><span class="small muted">Ctrl + Enter</span><span class="sp"></span><button class="btn" id="go">${icon("spark")}${esc(tt("send"))}</button></div></form>
    </div><aside>
      <section class="card"><div class="card-head"><div><h2>${esc(t("agents"))}</h2><p>${esc(t("agents_sub"))}</p></div></div>${lastTrace ? traceHTML(lastTrace, { anim: true }) : `<p class="muted small">–</p>`}</section>
    </aside></div>`;
    const chat = $("#chat");
    chat.scrollTop = chat.scrollHeight;
    $$(".sample").forEach((b) => (b.onclick = () => { $("#q").value = b.dataset.q; $("#askf").requestSubmit(); }));
    const clr = $("#clr");
    if (clr) clr.onclick = async () => { if (await confirmBox(tt("clear_q"), { ok: tt("clear"), danger: true })) { await api("/ask/history", { method: "DELETE" }); draw([]); } };
    $("#q").onkeydown = (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("#askf").requestSubmit(); };
    $("#askf").onsubmit = async (e) => {
      e.preventDefault();
      const q = $("#q").value.trim();
      if (!q) return;
      $("#go").disabled = true;
      $("#pending").innerHTML = `<div class="msg user"><div class="bubble jp">${esc(q)}</div></div><div class="msg bot"><div class="bubble muted">${esc(tt("thinking"))}</div></div>`;
      chat.scrollTop = chat.scrollHeight;
      try {
        const r = await api("/ask", { method: "POST", body: { message: q } });
        lastTrace = r.trace;
        msgs.push({ role: "user", content: q }, { role: "assistant", content: r.answer, citations: r.citations, follow_up: r.follow_up, levels: r.levels });
        draw(msgs);
      } catch (err) { toast(err.message, true); $("#pending").innerHTML = ""; $("#go").disabled = false; }
    };
  };
  draw(hist);
}

function msgHTML(m) {
  if (m.role === "user") return `<div class="msg user"><div class="bubble jp">${esc(m.content)}</div></div>`;
  const cites = m.citations || [];
  return `<div class="msg bot"><div class="bubble"><div class="md jp">${md(m.content)}</div>
    ${m.follow_up ? `<div class="probe"><b>${esc(tt("follow"))}</b><p>${esc(m.follow_up)}</p></div>` : ""}
    ${cites.length ? `<details class="cites"><summary>${esc(tt("sources"))} (${cites.length})${m.levels ? ` · ${esc(tt("your_levels"))} ${esc(m.levels[0])}–${esc(m.levels[m.levels.length - 1])}` : ""}</summary>${cites.map(citeHTML).join("")}</details>` : ""}
  </div></div>`;
}

// ======================================================================= Library
export async function libraryPage({ query }) {
  const page = shell({ nav: nav(), title: tt("library") });
  const st = { level: query.level || "", kind: query.kind || "", q: query.q || "", page: Number(query.page || 1), mode: query.mode || "text" };
  const kinds = ["vocab", "kanji", "grammar", "sentence", "article"];
  const sync = () => history.replaceState(history.state, "", `/app/library?${new URLSearchParams(Object.entries(st).filter(([, v]) => v && v !== 1 && v !== "text"))}`);
  const load = async () => {
    sync();
    const box = $("#lib");
    box.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;
    try {
      let items, total;
      if (st.mode === "meaning" && st.q) {
        items = await api(`/kb/search?${new URLSearchParams({ q: st.q, ...(st.level ? { level: st.level } : {}) })}`);
        if (st.kind) items = items.filter((x) => x.kind === st.kind);
        total = items.length;
      } else {
        const r = await api(`/kb/browse?${new URLSearchParams({ ...(st.level ? { level: st.level } : {}), ...(st.kind ? { kind: st.kind } : {}), q: st.q, page: st.page })}`);
        items = r.items; total = r.total;
      }
      const pages = Math.max(1, Math.ceil(total / 30));
      box.innerHTML = items.length ? `<p class="small muted" style="margin-bottom:8px">${esc(tt("results", { n: total.toLocaleString() }))}</p>
        <div class="grid g3">${items.map((d) => `<article class="topic lib-item"><div class="row between"><h3 class="jp" style="font-size:${d.kind === "kanji" ? "1.8rem" : "1.05rem"}">${esc(d.title)}</h3>
          <span class="row" style="gap:6px">${levelBadge(d.level)}<span class="badge plain">${esc(tt(`kinds.${d.kind}`) || d.kind)}</span></span></div>
          <p class="small jp">${esc(d.text.length > 260 ? d.text.slice(0, 260) + "…" : d.text)}</p>
          ${d.meta && d.meta.en && d.kind === "sentence" ? "" : ""}
          <div class="small muted" style="margin-top:auto">${esc(d.source)} · ${d.url ? `<a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.license)}</a>` : esc(d.license)}</div></article>`).join("")}</div>
        ${st.mode !== "meaning" && pages > 1 ? `<div class="row" style="margin-top:14px"><span class="small muted">${st.page} / ${pages}</span><span class="sp"></span>
          <button class="btn ghost sm" id="pp" ${st.page <= 1 ? "disabled" : ""}>${esc(tt("prev"))}</button><button class="btn ghost sm" id="np" ${st.page >= pages ? "disabled" : ""}>${esc(tt("next"))}</button></div>` : ""}`
        : `<div class="card empty"><p>${esc(tt("none"))}</p></div>`;
      const pp = $("#pp"), np = $("#np");
      if (pp) pp.onclick = () => { st.page -= 1; load(); };
      if (np) np.onclick = () => { st.page += 1; load(); };
    } catch (e) { box.innerHTML = `<div class="card empty"><p>${esc(e.message)}</p></div>`; }
  };
  page.innerHTML = `<div class="page-head"><div><h1>${esc(tt("library"))}</h1><p>${esc(tt("lib_sub"))}</p></div></div>
    <div class="row" style="margin-bottom:10px"><div class="seg" id="lv">${["", "N5", "N4", "N3", "N2", "N1"].map((l) => `<button data-l="${l}" class="${l === st.level ? "on" : ""}">${l || esc(tt("all"))}</button>`).join("")}</div>
      <div class="seg" id="kd">${["", ...kinds].map((k) => `<button data-k="${k}" class="${k === st.kind ? "on" : ""}">${k ? esc(tt(`kinds.${k}`)) : esc(tt("all"))}</button>`).join("")}</div></div>
    <form class="row" id="sf" style="margin-bottom:14px"><input type="search" id="sq" class="inline jp" style="flex:1;min-width:200px" value="${esc(st.q)}" placeholder="${esc(tt("search"))}…" aria-label="${esc(tt("search"))}">
      <label class="switch small"><input type="checkbox" id="sm" ${st.mode === "meaning" ? "checked" : ""} style="accent-color:var(--kon)"><span>${esc(tt("semantic"))}</span></label>
      <button class="btn ghost">${esc(tt("search"))}</button></form>
    <div class="split"><div id="lib"></div>
    <section class="card"><h2 style="margin-bottom:10px">${esc(tt("check"))}</h2><textarea id="lt" class="jp" placeholder="${esc(tt("check_ph"))}" style="min-height:80px"></textarea>
      <button class="btn" id="lb" style="margin-top:10px">${esc(tt("check_btn"))}</button><div id="lr" style="margin-top:12px"></div></section></div>`;
  $("#sm").style.background = "";
  $$("[data-l]").forEach((b) => (b.onclick = () => { st.level = b.dataset.l; st.page = 1; $$("[data-l]").forEach((x) => x.classList.toggle("on", x === b)); load(); }));
  $$("[data-k]").forEach((b) => (b.onclick = () => { st.kind = b.dataset.k; st.page = 1; $$("[data-k]").forEach((x) => x.classList.toggle("on", x === b)); load(); }));
  $("#sf").onsubmit = (e) => { e.preventDefault(); st.q = $("#sq").value.trim(); st.mode = $("#sm").checked ? "meaning" : "text"; st.page = 1; load(); };
  $("#lb").onclick = async () => {
    const text = $("#lt").value.trim();
    if (!text) return;
    try { $("#lr").innerHTML = levelResultHTML(await api("/level", { method: "POST", body: { text } })); } catch (e) { toast(e.message, true); }
  };
  await load();
}

export function levelResultHTML(r) {
  if (!r.level) return `<p class="muted">No Japanese found.</p>`;
  const probs = r.probs || {};
  return `<div class="row"><span class="muted small">${esc(tt("estimated"))}</span><span class="badge" style="font-size:1rem">JLPT ${esc(r.level)}</span><span class="small muted">${Math.round(r.confidence * 100)}% · ${esc(r.method)}</span></div>
    <div class="bars" style="margin-top:10px">${Object.entries(probs).map(([k, v]) => `<div class="b"><span>${k}</span><div class="meter"><i style="width:${Math.round(v * 100)}%"></i></div><span>${Math.round(v * 100)}%</span></div>`).join("")}</div>
    ${r.hardest && r.hardest.length ? `<p class="small" style="margin-top:10px"><span class="muted">${esc(tt("hardest"))}:</span> ${r.hardest.map((h) => `<span class="jp">${esc(h.text)}</span> <span class="badge plain">${esc(h.level)}</span>`).join(" ")}</p>` : ""}`;
}
