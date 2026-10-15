// Core: API client, auth store, router with real URLs (browser back works), i18n, UI helpers.

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const pct = (v) => (v === null || v === undefined ? "–" : `${Math.round(v * 100)}%`);
export const band = (v) => (v === null || v === undefined ? "" : v >= 0.8 ? "s" : v >= 0.6 ? "m" : "w");
export const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* ignore */ } },
};
export function fmtDate(iso, withTime = true) {
  if (!iso) return "–";
  const d = new Date(iso);
  return withTime ? d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : d.toLocaleDateString(undefined, { dateStyle: "medium" });
}
export function ago(iso) {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

// ------------------------------------------------------------------ auth
export const auth = {
  get token() { return store.get("xk_token", null); },
  get user() { return store.get("xk_user", null); },
  set(token, user) { store.set("xk_token", token); store.set("xk_user", user); },
  setUser(user) { store.set("xk_user", user); },
  clear() { store.del("xk_token"); store.del("xk_user"); },
};

// ------------------------------------------------------------------ api
export class ApiError extends Error {
  constructor(status, detail, code) { super(detail); this.status = status; this.code = code; }
}
export async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`;
  let res;
  try {
    res = await fetch(`/api${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, t("neterr"));
  }
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    if (res.status === 401 && auth.token && !path.startsWith("/auth/")) {
      auth.clear();
      navigate(`/login?next=${encodeURIComponent(location.pathname)}`, { replace: true });
    }
    throw new ApiError(res.status, (data && data.detail) || `Request failed (${res.status})`, data && data.code);
  }
  return data;
}

// ------------------------------------------------------------------ i18n (student UI)
const I18N = {
  en: {
    neterr: "Cannot reach the server. Check your connection and try again.",
    dashboard: "Dashboard", learn: "Practice", interview: "Interview proctor", progress: "My progress", certificate: "Certificate", profile: "Profile", logout: "Log out", back: "Back",
    hello: "Welcome back, {n}", hello_sub: "Your AI tutor plans each session from your weak spots, your memory of past answers and today's budget.",
    level: "Level", avg: "Average score", streak: "Day streak", answers: "Answers", days: "{n} days", notplaced: "Not placed",
    take_place: "Take the placement test", place_first: "Take the 15-question JLPT placement test (N5 to N1) so Kaigo Sensei can pick questions at your level.", next_target: "Next target: JLPT {l}", top_level: "Top level reached", track_caregiving: "Caregiving Japanese", track_caregiving_sub: "Japanese and skills for care work. These topics count toward your certificate.", track_jlpt: "JLPT N5 to N1", track_jlpt_sub: "Exam-style vocabulary, grammar, kanji and reading for each JLPT level.", your_level: "Your level", by_level: "Result by level",
    rec_title: "Next session", rec_go: "Start this session", rec_why: "Why this topic?", pick_own: "Choose a topic myself",
    reason_weak_spot: "This is a weak spot. Fixing it gives you the biggest gain.", reason_new_material: "You have not practised this yet.", reason_review_due: "Time to review this so you do not forget it.",
    cont: "Continue", cont_session: "You have a session in progress", heat: "Skill heatmap", heat_sub: "Every cell is one topic and skill. Colour shows your average score.",
    weak: "Weak", ok: "Getting there", good: "Strong", nodata: "Not practised", recent: "Recent sessions", none_yet: "No sessions yet.",
    readiness: "Certificate readiness", view_cert: "Open certificate", topics_title: "Practice topics", topics_sub: "Pick a topic, or let the AI router choose the one that helps you most right now.",
    ai_choose: "Let AI choose", start: "Start", questions_n: "{n} questions", mastery: "Mastery",
    place_title: "Placement test", qof: "Question {i} of {n}", next: "Next", prev: "Previous", submit_test: "Submit test", pick_one: "Pick one answer to continue.",
    place_done: "Your level is {l}", place_score: "{s} of {n} correct", go_dash: "Go to dashboard", start_practice: "Start practising", retake: "Retake test",
    type_ans: "Type your answer in English, Nepali or Japanese…", send: "Send answer", checking: "Agents are checking your answer…", speak: "Speak", stop: "Stop",
    nomic: "Voice input is not supported in this browser. Try Chrome.", think: "Think about it", model: "Model answer", next_q: "Next question",
    vocab: "Key words", history: "This session", agents: "Agent activity", agents_sub: "What each agent did for your last step.",
    done_title: "Session complete", done_avg: "Average score {p}", again: "Practise again", leave: "Leave session", leave_q: "Leave this session? Your answers so far are saved.",
    passed: "Interview passed", notpassed: "Not passed yet. You need {p}.", iv_title: "Interview proctor", iv_sub: "Mock visa and employer interviews. Answer as you would in the real room: in Japanese if you can, with です・ます.",
    iv_start: "Start interview", memories: "Learning memory", memories_sub: "Every answer is stored as a memory with an embedding. The tutor recalls similar past struggles before grading you.",
    struggle: "Struggle", masteryk: "Mastery", sessions_all: "Session history", topic: "Topic", score: "Score", date: "Date", status: "Status",
    cert_title: "Readiness certificate", cert_sub: "Pass every check to receive a signed certificate employers can verify by QR code.",
    cert_claim: "Issue my certificate", cert_need: "Complete the remaining checks to unlock your certificate.", cert_verify: "Verification link",
    save: "Save changes", saved: "Saved", name: "Name", lang: "Language", pw_cur: "Current password", pw_new: "New password", pw_change: "Change password", pw_done: "Password changed",
    budget_blocked: "Practice is paused", sk: { vocabulary: "Vocabulary", grammar: "Grammar", comprehension: "Comprehension", recall: "Recall", self_intro: "Self-introduction", motivation: "Motivation", japanese: "Japanese", scenario: "Scenario", culture: "Workplace culture" },
    diff: ["", "N5", "N4", "N3", "N2", "N1"], st: { active: "In progress", done: "Done", abandoned: "Left" },
  },
  ne: {
    neterr: "सर्भरसँग जोडिन सकेन। इन्टरनेट जाँचेर फेरि प्रयास गर्नुहोस्।",
    dashboard: "ड्यासबोर्ड", learn: "अभ्यास", interview: "अन्तर्वार्ता अभ्यास", progress: "मेरो प्रगति", certificate: "प्रमाणपत्र", profile: "प्रोफाइल", logout: "लग आउट", back: "पछाडि",
    hello: "फेरि स्वागत छ, {n}", hello_sub: "तपाईंको कमजोर क्षेत्र, पुराना उत्तरको सम्झना र आजको बजेट हेरेर AI ट्यूटरले हरेक सत्र तयार गर्छ।",
    level: "स्तर", avg: "औसत अङ्क", streak: "लगातार दिन", answers: "उत्तरहरू", days: "{n} दिन", notplaced: "स्तर परीक्षा बाँकी",
    take_place: "स्तर परीक्षा दिनुहोस्", place_first: "१५ प्रश्नको JLPT स्तर परीक्षा (N5 देखि N1) दिनुहोस्, ताकि कैगो सेन्सेईले तपाईंको स्तरअनुसार प्रश्न छान्न सकून्।", next_target: "अर्को लक्ष्य: JLPT {l}", top_level: "उच्चतम स्तर पुगियो", track_caregiving: "केयरगिभिङ जापानी", track_caregiving_sub: "हेरचाह कामका लागि जापानी र सीप। यी विषय प्रमाणपत्रमा गनिन्छन्।", track_jlpt: "JLPT N5 देखि N1", track_jlpt_sub: "हरेक JLPT स्तरका लागि परीक्षाजस्तै शब्द, व्याकरण, कान्जी र पढाइ।", your_level: "तपाईंको स्तर", by_level: "स्तरअनुसार नतिजा",
    rec_title: "अर्को सत्र", rec_go: "यो सत्र सुरु गर्नुहोस्", rec_why: "यो विषय किन?", pick_own: "आफैं विषय छान्नुहोस्",
    reason_weak_spot: "यो कमजोर क्षेत्र हो। यसलाई सुधार्दा सबैभन्दा धेरै फाइदा हुन्छ।", reason_new_material: "तपाईंले यो अझै अभ्यास गर्नुभएको छैन।", reason_review_due: "बिर्सिनु अघि दोहोर्याउने समय भयो।",
    cont: "जारी राख्नुहोस्", cont_session: "तपाईंको एउटा सत्र चलिरहेको छ", heat: "सीप हिटम्याप", heat_sub: "हरेक कोठा एउटा विषय र सीप हो। रङले औसत अङ्क देखाउँछ।",
    weak: "कमजोर", ok: "सुधार हुँदै", good: "राम्रो", nodata: "अभ्यास बाँकी", recent: "हालका सत्रहरू", none_yet: "अहिलेसम्म कुनै सत्र छैन।",
    readiness: "प्रमाणपत्र तयारी", view_cert: "प्रमाणपत्र खोल्नुहोस्", topics_title: "अभ्यास विषयहरू", topics_sub: "विषय छान्नुहोस्, वा अहिले सबैभन्दा उपयोगी विषय AI राउटरलाई छान्न दिनुहोस्।",
    ai_choose: "AI लाई छान्न दिनुहोस्", start: "सुरु", questions_n: "{n} प्रश्न", mastery: "दक्षता",
    place_title: "स्तर परीक्षा", qof: "प्रश्न {i} / {n}", next: "अर्को", prev: "अघिल्लो", submit_test: "परीक्षा बुझाउनुहोस्", pick_one: "अगाडि बढ्न एउटा उत्तर छान्नुहोस्।",
    place_done: "तपाईंको स्तर {l} हो", place_score: "{n} मध्ये {s} सही", go_dash: "ड्यासबोर्डमा जानुहोस्", start_practice: "अभ्यास सुरु गर्नुहोस्", retake: "फेरि परीक्षा दिनुहोस्",
    type_ans: "अङ्ग्रेजी, नेपाली वा जापानीमा उत्तर लेख्नुहोस्…", send: "उत्तर पठाउनुहोस्", checking: "एजेन्टहरूले उत्तर जाँच्दै छन्…", speak: "बोल्नुहोस्", stop: "रोक्नुहोस्",
    nomic: "यो ब्राउजरमा आवाज इनपुट चल्दैन। Chrome प्रयोग गर्नुहोस्।", think: "सोचेर हेर्नुहोस्", model: "नमुना उत्तर", next_q: "अर्को प्रश्न",
    vocab: "मुख्य शब्दहरू", history: "यो सत्र", agents: "एजेन्ट गतिविधि", agents_sub: "तपाईंको अन्तिम चरणमा हरेक एजेन्टले के गर्‍यो।",
    done_title: "सत्र पूरा भयो", done_avg: "औसत अङ्क {p}", again: "फेरि अभ्यास गर्नुहोस्", leave: "सत्र छोड्नुहोस्", leave_q: "सत्र छोड्ने? अहिलेसम्मका उत्तर सुरक्षित छन्।",
    passed: "अन्तर्वार्ता पास", notpassed: "अझै पास भएन। {p} चाहिन्छ।", iv_title: "अन्तर्वार्ता अभ्यास", iv_sub: "नक्कली भिसा र रोजगारदाता अन्तर्वार्ता। वास्तविक कोठामा जस्तै उत्तर दिनुहोस्: सकेसम्म です・ます सहित जापानीमा।",
    iv_start: "अन्तर्वार्ता सुरु", memories: "सिकाइ सम्झना", memories_sub: "हरेक उत्तर embedding सहित सम्झनाका रूपमा सुरक्षित हुन्छ। जाँच्नुअघि ट्यूटरले मिल्दाजुल्दा पुराना कठिनाइ सम्झन्छ।",
    struggle: "कठिनाइ", masteryk: "दक्षता", sessions_all: "सत्र इतिहास", topic: "विषय", score: "अङ्क", date: "मिति", status: "स्थिति",
    cert_title: "तयारी प्रमाणपत्र", cert_sub: "सबै जाँच पास गरेपछि रोजगारदाताले QR बाट प्रमाणित गर्न सक्ने हस्ताक्षरित प्रमाणपत्र पाउनुहुन्छ।",
    cert_claim: "मेरो प्रमाणपत्र जारी गर्नुहोस्", cert_need: "प्रमाणपत्र खोल्न बाँकी जाँचहरू पूरा गर्नुहोस्।", cert_verify: "प्रमाणीकरण लिङ्क",
    save: "परिवर्तन सुरक्षित गर्नुहोस्", saved: "सुरक्षित भयो", name: "नाम", lang: "भाषा", pw_cur: "हालको पासवर्ड", pw_new: "नयाँ पासवर्ड", pw_change: "पासवर्ड बदल्नुहोस्", pw_done: "पासवर्ड बदलियो",
    budget_blocked: "अभ्यास रोकिएको छ", sk: { vocabulary: "शब्दावली", grammar: "व्याकरण", comprehension: "बुझाइ", recall: "सम्झना", self_intro: "आत्मपरिचय", motivation: "उद्देश्य", japanese: "जापानी", scenario: "परिस्थिति", culture: "कार्यसंस्कृति" },
    diff: ["", "N5", "N4", "N3", "N2", "N1"], st: { active: "चलिरहेको", done: "पूरा", abandoned: "छोडियो" },
  },
  ja: {
    neterr: "サーバーに接続できません。通信を確認して、もう一度お試しください。",
    dashboard: "ダッシュボード", learn: "練習", interview: "面接練習", progress: "学習の記録", certificate: "修了証", profile: "プロフィール", logout: "ログアウト", back: "戻る",
    hello: "おかえりなさい、{n}さん", hello_sub: "AIチューターが、苦手な分野・過去の回答の記憶・今日の予算をもとに毎回のセッションを組み立てます。",
    level: "レベル", avg: "平均点", streak: "連続日数", answers: "回答数", days: "{n}日", notplaced: "未判定",
    take_place: "レベルチェックを受ける", place_first: "15問のJLPTレベルチェック（N5〜N1）を受けると、介護先生があなたのレベルに合った問題を選びます。", next_target: "次の目標：JLPT {l}", top_level: "最高レベルに到達", track_caregiving: "介護の日本語", track_caregiving_sub: "介護の仕事のための日本語とスキル。修了証の条件になります。", track_jlpt: "JLPT N5〜N1", track_jlpt_sub: "各レベルの語彙・文法・漢字・読解を試験形式で練習します。", your_level: "あなたのレベル", by_level: "レベル別の結果",
    rec_title: "次のセッション", rec_go: "このセッションを始める", rec_why: "なぜこのテーマ？", pick_own: "自分でテーマを選ぶ",
    reason_weak_spot: "苦手な分野です。ここを伸ばすのがいちばん効果的です。", reason_new_material: "まだ練習していないテーマです。", reason_review_due: "忘れないうちに復習しましょう。",
    cont: "続ける", cont_session: "途中のセッションがあります", heat: "スキルヒートマップ", heat_sub: "1マスが1つのテーマとスキルです。色は平均点を表します。",
    weak: "苦手", ok: "もう少し", good: "得意", nodata: "未練習", recent: "最近のセッション", none_yet: "まだセッションがありません。",
    readiness: "修了証までの条件", view_cert: "修了証を開く", topics_title: "練習テーマ", topics_sub: "テーマを選ぶか、今いちばん役立つテーマをAIルーターに選ばせましょう。",
    ai_choose: "AIに選んでもらう", start: "始める", questions_n: "{n}問", mastery: "習熟度",
    place_title: "レベルチェック", qof: "問題 {i} / {n}", next: "次へ", prev: "前へ", submit_test: "提出する", pick_one: "答えを1つ選んでください。",
    place_done: "あなたのレベルは {l} です", place_score: "{n}問中{s}問正解", go_dash: "ダッシュボードへ", start_practice: "練習を始める", retake: "もう一度受ける",
    type_ans: "英語・ネパール語・日本語で答えを入力…", send: "回答を送る", checking: "エージェントが回答を確認しています…", speak: "話す", stop: "止める",
    nomic: "このブラウザでは音声入力が使えません。Chromeをお試しください。", think: "考えてみましょう", model: "模範解答", next_q: "次の問題",
    vocab: "キーワード", history: "このセッション", agents: "エージェントの動き", agents_sub: "直前のステップで各エージェントが行ったこと。",
    done_title: "セッション完了", done_avg: "平均点 {p}", again: "もう一度練習", leave: "セッションを終了", leave_q: "終了しますか？ここまでの回答は保存されています。",
    passed: "面接合格", notpassed: "まだ合格ではありません。{p} が必要です。", iv_title: "面接練習", iv_sub: "ビザ面接・採用面接の模擬練習です。本番のように、できれば です・ます の日本語で答えましょう。",
    iv_start: "面接を始める", memories: "学習メモリー", memories_sub: "すべての回答はベクトル付きの記憶として保存されます。採点の前に、似た過去のつまずきを思い出します。",
    struggle: "つまずき", masteryk: "習得", sessions_all: "セッション履歴", topic: "テーマ", score: "得点", date: "日付", status: "状態",
    cert_title: "修了証", cert_sub: "すべての条件を満たすと、雇用主がQRコードで確認できる署名付き修了証が発行されます。",
    cert_claim: "修了証を発行する", cert_need: "残りの条件を満たすと修了証を受け取れます。", cert_verify: "確認用リンク",
    save: "保存する", saved: "保存しました", name: "名前", lang: "言語", pw_cur: "現在のパスワード", pw_new: "新しいパスワード", pw_change: "パスワードを変更", pw_done: "パスワードを変更しました",
    budget_blocked: "練習は一時停止中です", sk: { vocabulary: "語彙", grammar: "文法", comprehension: "読解", recall: "記憶", self_intro: "自己紹介", motivation: "志望動機", japanese: "日本語", scenario: "場面対応", culture: "職場文化" },
    diff: ["", "N5", "N4", "N3", "N2", "N1"], st: { active: "進行中", done: "完了", abandoned: "中断" },
  },
};
export const LANGS = [["en", "English"], ["ne", "नेपाली"], ["ja", "日本語"]];
export function lang() { return (auth.user && auth.user.lang) || store.get("xk_lang", "en"); }
export function t(key, vars = {}) {
  const dict = I18N[lang()] || I18N.en;
  let s = key.split(".").reduce((o, k) => (o ? o[k] : undefined), dict);
  if (s === undefined) s = key.split(".").reduce((o, k) => (o ? o[k] : undefined), I18N.en);
  if (s === undefined) return key;
  return typeof s === "string" ? s.replace(/\{(\w+)\}/g, (_, x) => vars[x] ?? "") : s;
}

// ------------------------------------------------------------------ icons
const P = {
  home: '<path d="M3 10.5 12 3l9 7.5V21a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/>',
  book: '<path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v17H6.5A2.5 2.5 0 0 0 4 21.5zM4 21.5A2.5 2.5 0 0 1 6.5 19H20v3H6.5"/>',
  mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v4"/>',
  chart: '<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/>',
  award: '<circle cx="12" cy="9" r="6"/><path d="M8.5 14 7 22l5-3 5 3-1.5-8"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2 20c1-3.5 3.8-5.5 7-5.5s6 2 7 5.5"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M22 20c-.6-2.6-2.2-4.4-4.5-5.1"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  cpu: '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v4M15 1v4M9 19v4M15 19v4M1 9h4M1 15h4M19 9h4M19 15h4"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  shield: '<path d="M12 2 4 5v6c0 5 3.5 9.5 8 11 4.5-1.5 8-6 8-11V5z"/><path d="m9 12 2 2 4-4"/>',
  building: '<rect x="4" y="2" width="16" height="20" rx="1"/><path d="M9 22v-4h6v4M8 6h.01M12 6h.01M16 6h.01M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  back: '<path d="M15 18l-6-6 6-6"/>',
  menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  check: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  circle: '<circle cx="12" cy="12" r="9"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
  play: '<path d="M7 4v16l13-8z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  db: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h5"/>',
};
export const icon = (n) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[n] || ""}</svg>`;

// ------------------------------------------------------------------ toasts, modals
export function toast(msg, bad = false) {
  const el = document.createElement("div");
  el.className = `toast${bad ? " bad" : ""}`;
  el.textContent = msg;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), 4200);
}
export function overlay(html, { kind = "drawer", onClose } = {}) {
  const wrap = document.createElement("div");
  wrap.className = `overlay${kind === "modal" ? " center" : ""}`;
  wrap.innerHTML = `<div class="${kind}" role="dialog" aria-modal="true">${html}</div>`;
  const close = () => { wrap.remove(); document.removeEventListener("keydown", onKey); onClose && onClose(); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  wrap.addEventListener("click", (e) => { if (e.target === wrap || e.target.closest("[data-close]")) close(); });
  document.addEventListener("keydown", onKey);
  document.body.appendChild(wrap);
  const first = wrap.querySelector("input, select, textarea, button");
  first && first.focus();
  return { el: wrap.firstElementChild, close };
}
export function confirmBox(message, { ok = "Confirm", danger = false } = {}) {
  return new Promise((resolve) => {
    let answered = false;
    const m = overlay(`<p style="font-size:1rem">${esc(message)}</p><div class="row" style="justify-content:flex-end;margin-top:20px">
      <button class="btn ghost" data-close>Cancel</button><button class="btn ${danger ? "danger" : ""}" data-ok>${esc(ok)}</button></div>`,
      { kind: "modal", onClose: () => { if (!answered) resolve(false); } });
    m.el.querySelector("[data-ok]").addEventListener("click", () => { answered = true; resolve(true); m.close(); });
  });
}

// ------------------------------------------------------------------ router
const routes = [];
let depth = 0;
export function route(pattern, handler, opts = {}) {
  const keys = [];
  const rx = new RegExp("^" + pattern.replace(/:(\w+)/g, (_, k) => { keys.push(k); return "([^/]+)"; }) + "/?$");
  routes.push({ rx, keys, handler, opts });
}
export function navigate(path, { replace = false } = {}) {
  if (replace) history.replaceState({ depth }, "", path);
  else { depth += 1; history.pushState({ depth }, "", path); }
  render();
}
export function goBack(fallback) {
  // Real browser history when we navigated inside the app; otherwise go to the parent screen.
  if (depth > 0) history.back();
  else navigate(fallback || "/", { replace: true });
}
window.addEventListener("popstate", (e) => { depth = (e.state && e.state.depth) || 0; render(); });
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[href]");
  if (!a || a.target || a.hasAttribute("download") || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  const url = new URL(a.href, location.href);
  if (url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  e.preventDefault();
  navigate(url.pathname + url.search);
});

let renderToken = 0;
export const current = { cleanup: null };
export async function render() {
  const token = ++renderToken;
  if (current.cleanup) { try { current.cleanup(); } catch { /* ignore */ } current.cleanup = null; }
  $$(".overlay").forEach((o) => o.remove());
  const path = location.pathname;
  const query = Object.fromEntries(new URLSearchParams(location.search));
  for (const r of routes) {
    const m = path.match(r.rx);
    if (!m) continue;
    const params = Object.fromEntries(r.keys.map((k, i) => [k, decodeURIComponent(m[i + 1])]));
    const user = auth.user;
    if (r.opts.role && !user) return navigate(`/login?next=${encodeURIComponent(path)}`, { replace: true });
    if (r.opts.role === "admin" && user.role !== "admin") return navigate("/app", { replace: true });
    if (r.opts.role === "student" && user.role === "admin") return navigate("/admin", { replace: true });
    try {
      await r.handler({ params, query, isCurrent: () => token === renderToken });
    } catch (err) {
      if (token !== renderToken) return;
      const root = $("#page") || $("#root");
      root.innerHTML = `<div class="card empty"><h3>Something went wrong</h3><p>${esc(err.message)}</p>
        <div class="row" style="justify-content:center;margin-top:14px"><button class="btn ghost" id="retry">Try again</button></div></div>`;
      $("#retry").onclick = () => render();
    }
    window.scrollTo(0, 0);
    return;
  }
  $("#root").innerHTML = `<div class="auth-form"><div class="box"><h2>Page not found</h2><p class="sub">There is nothing at ${esc(path)}.</p><a class="btn" href="/">Go home</a></div></div>`;
}

// ------------------------------------------------------------------ theme
export function toggleTheme() {
  const now = document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const next = now === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  store.set("xk_theme", next);
}

// ------------------------------------------------------------------ app shell
export function shell({ nav, title, crumb = "", back = null, actions = "" }) {
  const user = auth.user || {};
  const isAdmin = user.role === "admin";
  const path = location.pathname;
  let shellEl = $(".shell");
  if (!shellEl || shellEl.dataset.role !== user.role || shellEl.dataset.lang !== lang()) {
    $("#root").innerHTML = `<div class="shell" data-role="${esc(user.role)}" data-lang="${esc(lang())}">
      <aside class="side" id="side">
        <a class="brand" href="${isAdmin ? "/admin" : "/app"}"><span class="brand-mark">介</span><span><b>XploraKōdo</b><span>${isAdmin ? "Admin console" : "Kaigo Sensei tutor"}</span></span></a>
        <nav class="nav" id="nav" aria-label="Main"></nav>
        <div class="side-foot"><b>${esc(user.name)}</b>${esc(user.email)}</div>
      </aside>
      <div class="main">
        <header class="top">
          <button class="icon-btn menu-btn" id="menu" aria-label="Open menu">${icon("menu")}</button>
          <span id="backslot"></span>
          <div class="title" id="ptitle"></div>
          <span id="actslot"></span>
          ${isAdmin ? "" : `<select id="langsel" class="inline" aria-label="Language">${LANGS.map(([k, v]) => `<option value="${k}" ${k === lang() ? "selected" : ""}>${v}</option>`).join("")}</select>`}
          <button class="icon-btn" id="theme" aria-label="Switch light or dark theme">${icon("sun")}</button>
          <button class="icon-btn" id="logout" aria-label="${esc(t("logout"))}" title="${esc(t("logout"))}">${icon("logout")}</button>
        </header>
        <main class="content" id="page"></main>
      </div></div>`;
    shellEl = $(".shell");
    $("#theme").onclick = toggleTheme;
    $("#menu").onclick = () => $("#side").classList.toggle("open");
    $("#logout").onclick = () => { auth.clear(); navigate("/login", { replace: true }); };
    const ls = $("#langsel");
    if (ls) ls.onchange = async () => {
      try {
        const u = await api("/me", { method: "PUT", body: { lang: ls.value } });
        auth.setUser(u); store.set("xk_lang", u.lang); render();
      } catch (e) { toast(e.message, true); }
    };
  }
  $("#side").classList.remove("open");
  $("#nav").innerHTML = nav.map((n) => n.group ? `<div class="nav-group">${esc(n.group)}</div>` :
    `<a href="${n.href}" class="${(n.exact ? path === n.href : path === n.href || path.startsWith(n.href + "/")) ? "on" : ""}">${icon(n.icon)}<span>${esc(n.label)}</span></a>`).join("");
  $("#ptitle").innerHTML = `${crumb ? `<span class="crumb">${esc(crumb)} / </span>` : ""}${esc(title)}`;
  document.title = `${title} · XploraKōdo`;
  $("#backslot").innerHTML = back ? `<button class="back" id="backbtn">${icon("back")}<span>${esc(isAdmin ? "Back" : t("back"))}</span></button>` : "";
  if (back) $("#backbtn").onclick = () => goBack(back);
  $("#actslot").innerHTML = actions;
  return $("#page");
}

export function loading(el) { el.innerHTML = `<div class="loading"><div class="spinner" role="status" aria-label="Loading"></div></div>`; }

// ------------------------------------------------------------------ shared widgets
export function heatmapHTML(h, { admin = false } = {}) {
  if (!h || !h.topics.length) return `<p class="muted">–</p>`;
  const L = (k) => (admin ? { weak: "Weak", ok: "Getting there", good: "Strong", nodata: "No data" }[k] : t(k));
  const SK = (s) => (admin ? s[0].toUpperCase() + s.slice(1) : t(`sk.${s}`));
  const color = (v) => (v >= 0.8 ? "var(--strong)" : v >= 0.6 ? "var(--mid)" : "var(--weak)");
  return `<div style="overflow-x:auto"><table class="hm"><thead><tr><th></th>${h.skills.map((s) => `<th scope="col">${esc(SK(s))}</th>`).join("")}</tr></thead><tbody>
    ${h.topics.map((tp) => `<tr><th scope="row" class="tp">${esc(tp.title)}</th>${h.skills.map((s) => {
      const c = h.cells[tp.id] && h.cells[tp.id][s];
      return c ? `<td style="background:${color(c.avg)}" title="${esc(tp.title)} · ${esc(SK(s))}: ${pct(c.avg)} (${c.n})">${pct(c.avg)}<small>n=${c.n}</small></td>`
        : `<td class="none" title="${esc(L("nodata"))}">–</td>`;
    }).join("")}</tr>`).join("")}</tbody></table></div>
    <div class="legend"><span><i style="background:var(--weak)"></i>${esc(L("weak"))} &lt;60%</span><span><i style="background:var(--mid)"></i>${esc(L("ok"))} 60–79%</span><span><i style="background:var(--strong)"></i>${esc(L("good"))} ≥80%</span><span><i style="background:var(--line-soft);border:1px dashed var(--line)"></i>${esc(L("nodata"))}</span></div>`;
}

const AGENT_ABBR = { Guardian: "G", "AIQ Router": "R", Smriti: "M", Retriever: "K", Tutor: "T", Progress: "P", Certifier: "C", Supervisor: "S", Leveler: "L", "Course Factory": "F", "QA Agent": "Q" };
export function traceHTML(trace, { anim = false } = {}) {
  if (!trace || !trace.events) return "";
  return `<ol class="trace${anim ? " anim" : ""}">${trace.events.map((e, i) => `<li class="${esc(e.status)}" style="animation-delay:${i * 60}ms">
    <span class="dot" aria-hidden="true">${AGENT_ABBR[e.agent] || "•"}</span>
    <div><div class="who">${esc(e.agent)} <code>${esc(e.node)}</code><span class="ms">${e.ms} ms</span></div><div class="what">${esc(e.summary)}</div></div></li>`).join("")}</ol>
    <p class="small muted" style="margin-top:8px">${esc(trace.graph)} run #${trace.run_id ?? "–"} · ${trace.events.length} steps · ${trace.ms} ms · ${trace.tokens} tokens</p>`;
}

export function scoreRing(v) {
  const r = 22, c = 2 * Math.PI * r, p = Math.max(0, Math.min(1, v || 0));
  const col = p >= 0.8 ? "var(--strong)" : p >= 0.6 ? "var(--mid)" : "var(--weak)";
  return `<svg class="score-ring" viewBox="0 0 54 54" role="img" aria-label="${pct(p)}"><circle cx="27" cy="27" r="${r}" fill="none" stroke="var(--line)" stroke-width="5"/>
    <circle cx="27" cy="27" r="${r}" fill="none" stroke="${col}" stroke-width="5" stroke-linecap="round" stroke-dasharray="${c * p} ${c}" transform="rotate(-90 27 27)"/>
    <text x="27" y="31" text-anchor="middle" font-size="12" font-weight="700" fill="currentColor">${Math.round(p * 100)}</text></svg>`;
}

export function meter(v, cls) {
  return `<div class="meter ${cls ?? band(v)}"><i style="width:${Math.round((v || 0) * 100)}%"></i></div>`;
}
