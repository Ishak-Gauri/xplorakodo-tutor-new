-- XploraKodo Tutor: PostgreSQL + pgvector schema.
-- Applied automatically on startup by app/db.py (tracked in schema_migrations).
CREATE EXTENSION IF NOT EXISTS vector;

-- Tenants / cohorts (a language institute, a manpower company, a batch).
CREATE TABLE IF NOT EXISTS organizations (
  id          SERIAL PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id             SERIAL PRIMARY KEY,
  org_id         INT REFERENCES organizations(id) ON DELETE SET NULL,
  email          TEXT NOT NULL UNIQUE,
  password_hash  TEXT NOT NULL,
  name           TEXT NOT NULL,
  role           TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student','admin')),
  status         TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended')),
  lang           TEXT NOT NULL DEFAULT 'en' CHECK (lang IN ('en','ne','ja')),
  track          TEXT NOT NULL DEFAULT 'caregiving',
  level          TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- Curriculum. kind = practice (Kaigo Sensei) or interview (Interview Proctor scenario).
CREATE TABLE IF NOT EXISTS topics (
  id          TEXT PRIMARY KEY,
  kind        TEXT NOT NULL DEFAULT 'practice' CHECK (kind IN ('practice','interview')),
  title       JSONB NOT NULL,
  summary     JSONB NOT NULL DEFAULT '{}'::jsonb,
  vocab       JSONB NOT NULL DEFAULT '[]'::jsonb,
  position    INT NOT NULL DEFAULT 0,
  active      BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS questions (
  id            TEXT PRIMARY KEY,
  topic_id      TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  skill         TEXT NOT NULL,
  difficulty    SMALLINT NOT NULL DEFAULT 1 CHECK (difficulty BETWEEN 1 AND 3),
  prompt        JSONB NOT NULL,
  keywords      JSONB NOT NULL DEFAULT '[]'::jsonb,
  model_answer  JSONB NOT NULL DEFAULT '{}'::jsonb,
  probe         JSONB NOT NULL DEFAULT '{}'::jsonb,
  active        BOOLEAN NOT NULL DEFAULT true,
  embedding     vector(256),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_questions_topic ON questions(topic_id) WHERE active;

CREATE TABLE IF NOT EXISTS placement_items (
  id          SERIAL PRIMARY KEY,
  ext_id      TEXT UNIQUE,
  q           JSONB NOT NULL,
  options     JSONB NOT NULL,
  answer      SMALLINT NOT NULL,
  difficulty  SMALLINT NOT NULL DEFAULT 1,
  active      BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS placement_attempts (
  id          SERIAL PRIMARY KEY,
  user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  item_ids    INT[] NOT NULL,
  answers     INT[],
  score       INT,
  total       INT NOT NULL,
  level       TEXT,
  status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done')),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_placement_user ON placement_attempts(user_id);

-- A practice or interview session. question_ids is the pool chosen for THIS user.
CREATE TABLE IF NOT EXISTS sessions (
  id            SERIAL PRIMARY KEY,
  user_id       INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL DEFAULT 'practice' CHECK (kind IN ('practice','interview')),
  topic_id      TEXT NOT NULL REFERENCES topics(id),
  status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','done','abandoned')),
  question_ids  TEXT[] NOT NULL,
  decision      JSONB NOT NULL DEFAULT '{}'::jsonb,
  avg_score     REAL,
  passed        BOOLEAN,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, created_at DESC);

-- One row per question asked. answer/score are NULL until the student answers.
CREATE TABLE IF NOT EXISTS turns (
  id           SERIAL PRIMARY KEY,
  session_id   INT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  user_id      INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  question_id  TEXT NOT NULL REFERENCES questions(id),
  idx          INT NOT NULL,
  answer       TEXT,
  score        REAL,
  feedback     TEXT,
  probe        TEXT,
  grader       TEXT,
  flags        JSONB NOT NULL DEFAULT '[]'::jsonb,
  latency_ms   INT,
  asked_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  answered_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_turns_user_q ON turns(user_id, question_id);
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, idx);

-- Smriti: lifetime learning memory, searched by cosine similarity.
CREATE TABLE IF NOT EXISTS memories (
  id           SERIAL PRIMARY KEY,
  user_id      INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL CHECK (kind IN ('struggle','mastery','note')),
  topic_id     TEXT,
  skill        TEXT,
  question_id  TEXT,
  score        REAL,
  text         TEXT NOT NULL,
  embedding    vector(256) NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_hnsw ON memories USING hnsw (embedding vector_cosine_ops);

-- RAG knowledge base: vocab, model answers and handbook notes, chunked and embedded.
CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id         SERIAL PRIMARY KEY,
  topic_id   TEXT,
  source     TEXT NOT NULL,
  text       TEXT NOT NULL,
  embedding  vector(256) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_hnsw ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);

-- Agent observability: one run per graph execution, one event per node.
CREATE TABLE IF NOT EXISTS agent_runs (
  id           SERIAL PRIMARY KEY,
  graph        TEXT NOT NULL,
  user_id      INT REFERENCES users(id) ON DELETE SET NULL,
  session_id   INT REFERENCES sessions(id) ON DELETE SET NULL,
  status       TEXT NOT NULL,
  tokens       INT NOT NULL DEFAULT 0,
  duration_ms  INT NOT NULL DEFAULT 0,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_runs_created ON agent_runs(created_at DESC);

CREATE TABLE IF NOT EXISTS agent_events (
  id           SERIAL PRIMARY KEY,
  run_id       INT NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  seq          INT NOT NULL,
  agent        TEXT NOT NULL,
  node         TEXT NOT NULL,
  status       TEXT NOT NULL,
  summary      TEXT NOT NULL DEFAULT '',
  detail       JSONB NOT NULL DEFAULT '{}'::jsonb,
  duration_ms  INT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_events_run ON agent_events(run_id, seq);

-- Cost-guard ledger (persistent, survives restarts).
CREATE TABLE IF NOT EXISTS token_usage (
  user_id  INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  day      DATE NOT NULL DEFAULT CURRENT_DATE,
  tokens   INT NOT NULL DEFAULT 0,
  calls    INT NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, day)
);

CREATE TABLE IF NOT EXISTS settings (
  key         TEXT PRIMARY KEY,
  value       JSONB NOT NULL,
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS certificates (
  id          SERIAL PRIMARY KEY,
  code        TEXT NOT NULL UNIQUE,
  user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  level       TEXT,
  scores      JSONB NOT NULL,
  signature   TEXT NOT NULL,
  revoked     BOOLEAN NOT NULL DEFAULT false,
  issued_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
  id          SERIAL PRIMARY KEY,
  actor_id    INT REFERENCES users(id) ON DELETE SET NULL,
  action      TEXT NOT NULL,
  target      TEXT,
  detail      JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
