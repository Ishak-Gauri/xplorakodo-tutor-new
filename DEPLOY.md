# Deploy to Render with PostgreSQL + pgvector

Your v2 runs at `https://xplorakodo-tutor.onrender.com` as a Python web service. v3 needs one more thing: a
PostgreSQL database. The app creates the `vector` extension and all tables itself on start.

## 1. Pick a database

| Option | Cost | Keeps data? | Notes |
|---|---|---|---|
| **Neon** (neon.tech) | free tier | yes | pgvector supported. Copy the connection string (with `?sslmode=require`). |
| **Supabase** | free tier | yes | pgvector supported. Use the "Session pooler" connection string. |
| **Render Postgres – free** | free | **expires after 30 days** | Fine for a demo; the Blueprint creates it for you. |
| **Render Postgres – paid** | from a few $/month | yes | Same region as the web service; best latency. |

## 2a. Update your existing Render service (keeps the same URL)

1. Push this code to the same GitHub repo/branch the service uses:
   ```powershell
   git add .
   git commit -m "v3: PostgreSQL + pgvector, auth, agent graph, new UI"
   git push
   ```
2. In Render → your service → **Environment**, add:

   | Key | Value |
   |---|---|
   | `DATABASE_URL` | the connection string from step 1 |
   | `JWT_SECRET` | a long random string (Render can generate one) |
   | `ADMIN_EMAIL` | your admin email |
   | `ADMIN_PASSWORD` | a strong password |
   | `PUBLIC_BASE_URL` | `https://xplorakodo-tutor.onrender.com` |
   | `SEED_DEMO` | `true` for a demo, `false` for real students |

3. Check **Settings → Start Command** is
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'`
   and **Health Check Path** is `/api/health`.
4. **Manual Deploy → Deploy latest commit.** When it is live, open `/api/health`; you should see
   `{"ok":true,"db":"postgresql","pgvector":"0.x.x",...}`.
   The first build installs LangGraph, LangSmith, OpenAI and numpy, so it takes a few minutes.
5. Sign in at `/login` with the admin email and password. The admin account is only created if that email does not
   exist yet. Change it any time in **Admin → Settings → Your admin password**.

## 2b. Or create everything fresh from the Blueprint
Render → **New → Blueprint** → pick the repo. `render.yaml` creates the web service and a free Postgres database,
wires `DATABASE_URL`, and generates `JWT_SECRET`. Set `ADMIN_PASSWORD` when Render asks.

## 3. AI keys (OpenAI, LangSmith, Kaggle)
Add these in Render → Environment (they are already listed in `render.yaml`):

| Key | Value |
|---|---|
| `LLM_PROVIDER` | `openai` |
| `OPENAI_API_KEY` | your OpenAI key |
| `OPENAI_MODEL` | `gpt-4o-mini` (or any current chat model with JSON mode) |
| `LANGSMITH_TRACING` | `true` |
| `LANGSMITH_API_KEY` | from smith.langchain.com → Settings → API keys |
| `LANGSMITH_PROJECT` | `xplorakodo-tutor` |
| `KAGGLE_USERNAME`, `KAGGLE_KEY` | only if you ingest Kaggle datasets |

Without `OPENAI_API_KEY` the app still runs in offline mode. Keep **Admin → Settings → Daily token budget** low on a
public link; the router switches to the free deterministic mode when a student's budget runs low, and the kill switch
stops everything at once.

## 4. Fill the knowledge base
The bundled N5–N1 vocabulary, kanji and grammar load automatically in the background after the first start
(10k documents; on Neon this takes a minute or two). Then, in **Admin → Knowledge base**, click **Ingest** for
Tatoeba and Wikipedia (and Kaggle with your dataset names), and finally **Retrain model**.

## Free-plan behaviour
* The web service sleeps after 15 minutes idle; the first request can take up to a minute.
* With v3 the data lives in PostgreSQL, so students, scores, memories and certificates survive restarts and redeploys
  (as long as the database itself does: see the 30-day note for Render's free Postgres).

## Any Docker host
```bash
docker build -t xk .
docker run -p 8000:8000 -e DATABASE_URL=... -e JWT_SECRET=... -e ADMIN_PASSWORD=... xk
```
