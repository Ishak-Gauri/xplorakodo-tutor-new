# XploraKōdo Tutor v3.1: an agentic JLPT + caregiving tutor

A trilingual (English / नेपाली / 日本語) tutor for Nepali learners preparing for the JLPT (N5–N1) and for caregiving
work in Japan. Built to the AI Agent & Full-Stack TOR: **LangGraph** multi-agent workflows, **LangSmith** tracing and
evals, **OpenAI** as the LLM, a **five-level knowledge base** in **PostgreSQL + pgvector**, a **trained JLPT level
model**, FastAPI, and a responsive web app with a full admin console.

## What it does

| For students | For admins |
|---|---|
| JLPT placement test (N5 → N1), different questions for every student | KPIs, activity, cohort heatmap, hardest questions |
| Practice sessions picked by the AIQ router from your weak spots | Students: search, add, suspend, reset password, drill-down |
| **Ask Sensei**: RAG chat that answers at your level, with sources | **Knowledge base**: coverage by level, ingest Tatoeba / Wikipedia / Kaggle |
| **Library**: N5–N1 vocabulary, kanji, grammar, sentences, articles | **Level model**: metrics, confusion matrix, versions, try it, retrain |
| "Check the level of any Japanese text" (trained Leveler) | **Course factory**: agents write new questions → you approve |
| Interview proctor, progress heatmap, learning memory | Question bank (drafts / published), agent-run explorer, audit log |
| QR-verifiable certificate | Settings: kill switch, budgets, router weights, LangSmith status |

## Architecture

```
Browser (vanilla ES-module SPA, responsive, real URLs + Back)
   │  JWT
FastAPI ── LangGraph graphs ───────────────────────────────────────────────┐
   │        start_session : Guardian → AIQ Router(topic) → Smriti → AIQ Router(pool) → Supervisor
   │        answer        : Guardian → Leveler → AIQ Router(grader) → Smriti → Retriever → Tutor
   │                        → Guardian(meter) → Progress → Smriti(store) → AIQ Router(next) → Certifier
   │        ask           : Guardian → Leveler → Smriti → Retriever → AIQ Router(model) → Sensei → Guardian(meter)
   │        factory       : Retriever → Generator → Leveler(validate) → QA Agent → save drafts
   │                                                                          │ traces
   ├── OpenAI (wrap_openai)  ── only where the AIQ router allows ──────────► LangSmith
   ├── Leveler: numpy JLPT classifier + N5–N1 lexicon
   └── PostgreSQL + pgvector: users, sessions, turns, memories (HNSW), kb_documents (HNSW),
       agent_runs/events, ml_models (versioned weights), chat, certificates, audit
```

* **Deterministic routing, LLM as a callable asset.** The AIQ router picks topics, questions and whether a step may
  use the LLM by maximising `L = NB(t) − Σ λk·Ck(t)` (gain from weak spots, novelty and spaced review vs. cost,
  repetition and level-fit penalties). The full decision table is stored and shown in the UI.
* **Every run is observable twice:** in LangSmith (nested LangGraph trace with OpenAI calls, retrievals and Leveler
  calls) and in the app's own "Agent runs" page backed by Postgres.
* **Graceful degradation:** with no OpenAI key every flow still works with the deterministic grader, template
  question generation and extractive RAG answers.

## The five-level knowledge base

| Source | What | Licence | How |
|---|---|---|---|
| JLPT vocabulary lists | 7,896 words, N5–N1 | MIT (lists from tanos.co.uk, CC BY) | bundled |
| KANJIDIC | 2,211 JLPT kanji (+ frequency/strokes for 13k) | CC BY-SA 4.0 | bundled |
| Grammar notes | 50 patterns, 10 per level, with examples | CC BY 4.0 (original) | bundled |
| Course content | lesson answers, vocab, handbook | own | bundled |
| **Tatoeba** | Japanese sentences (+ English), levelled by the Leveler, balanced per level | CC BY 2.0 FR | Admin → Knowledge base → Ingest |
| **Wikipedia** | JLPT, grammar, keigo, kanji, caregiving in Japan (EN + JA) | CC BY-SA 4.0 | Admin → Ingest |
| **Kaggle** | celineboutinon JLPT master list (CC BY-SA), robinpourtaud JLPT words (CC BY-NC), balankdharan7 N4 + example sentences (CC BY-NC-SA); any other CSV/JSON with word / reading / meaning / level | per dataset | Admin → Ingest (kagglehub) |
| **Nepali meanings** | English meanings of vocab + kanji translated to Nepali, easiest level first | machine translation | Admin → Ingest → Add Nepali meanings (OpenAI) |

All documents carry `level`, `kind`, `source`, `licence` and `url`, are embedded into `vector(256)` and searched with an
HNSW index filtered to the student's level (their level + one above). See `data/kb/ATTRIBUTION.md`. Copyrighted
textbooks are deliberately not included.

## The trained model (Leveler)

A multinomial logistic-regression (softmax) classifier over hashed character 1–3-grams plus KANJIDIC frequency /
stroke / grade features, trained with mini-batch Adam in numpy, combined at inference with an N5–N1 lexicon
(greedy longest match). Held-out results on the bundled data:

| | Score |
|---|---|
| Single word/kanji, exact level | 40% (majority baseline 38%), macro-F1 0.36 |
| Single word/kanji, within one level | 70% |
| Sentences (JLPT model answers), exact | 48% |
| Sentences, within one level | 78% |

Levelling isolated words is genuinely hard (the official lists themselves overlap). The model improves when you ingest
Tatoeba/Kaggle data and click **Retrain** (Admin → Knowledge base); each version is stored in `ml_models` with its
metrics and can be activated or rolled back. Used by: answer levelling, Ask Sensei, Tatoeba/Wikipedia/Kaggle
levelling, and Course Factory validation.

## Run locally

```bash
docker compose up -d db            # PostgreSQL 16 + pgvector (or use a Neon connection string)
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # set DATABASE_URL, JWT_SECRET, ADMIN_PASSWORD, OPENAI_API_KEY, LANGSMITH_*
uvicorn app.main:app --reload
```

The first start loads ~10k knowledge-base documents in the background (watch for `[kb:…] finished`).
Demo student: `demo@xplorakodo.com` / `demo1234`. Admin: `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

```bash
python -m app.kb.ingest tatoeba wikipedia          # or use the admin page
python -m app.kb.ingest kaggle                     # the three default JLPT datasets (or --datasets owner/slug,...)
python -m app.kb.ingest nepali                     # add Nepali meanings with OpenAI
python -m app.kb.ingest retrain                    # retrain the Leveler on everything ingested
python -m app.ml.train                             # retrain the bundled model file from data/kb
TEST_DATABASE_URL=postgresql://xk:xk@localhost:5432/xplorakodo_test pytest   # 41 tests, real Postgres, no network
python -m evals.run_evals                          # 39 golden grading cases (offline)
python -m evals.langsmith_eval                     # LangSmith datasets + experiments (needs LANGSMITH_API_KEY)
```

## Code map

| Path | Contents |
|---|---|
| `app/agents/graph.py` | LangGraph wrapper: nodes, edges, error routing, per-node trace, Postgres + LangSmith |
| `app/agents/*.py` | Guardian, AIQ Router, Smriti (memory), Retriever, Leveler, Tutor/Proctor, Progress, Certifier |
| `app/service.py` | start_session + answer graphs, placement, dashboard |
| `app/flows.py` | Ask Sensei and Course Factory graphs |
| `app/kb/` | knowledge-base store (level-aware pgvector search) and the source ingesters |
| `app/ml/` | Leveler model, training/evaluation, model registry |
| `app/llm.py`, `app/observability.py` | OpenAI / Anthropic / mock providers; LangSmith setup |
| `app/migrations/` | `001` core schema, `002` JLPT levels, `003` knowledge base, models, chat, drafts |
| `static/assets/js/` | `core.js` (router, API, i18n), `student.js`, `learn.js` (Ask, Library), `admin.js`, `admin2.js` |
| `tests/`, `evals/` | API + unit + flow tests (offline fakes for OpenAI and the internet); golden evals; LangSmith evals |

## Known limits
* Nepali and Japanese strings (UI, grammar notes, questions) were written with AI help; have native speakers review them.
* The Leveler is a lightweight classifier, not a large model; treat its level as an estimate (shown with confidence).
* Wikipedia/Tatoeba/Kaggle are fetched at runtime from the server you run; check each Kaggle dataset's licence.
* Voice input uses the browser's Web Speech API (best in Chrome).
