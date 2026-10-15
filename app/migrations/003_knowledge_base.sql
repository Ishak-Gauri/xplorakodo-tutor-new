-- Five-level knowledge base, ingestion runs, model registry, Ask Sensei chat, Course Factory drafts.
CREATE TABLE IF NOT EXISTS kb_documents (
  id          SERIAL PRIMARY KEY,
  source      TEXT NOT NULL,                 -- jlpt_vocab | kanjidic | grammar | curriculum | tatoeba | wikipedia | kaggle:<slug>
  ext_id      TEXT NOT NULL,
  kind        TEXT NOT NULL,                 -- vocab | kanji | grammar | sentence | article | lesson | handbook
  level       TEXT,                          -- N5..N1, or NULL for general reference
  title       TEXT NOT NULL,
  text        TEXT NOT NULL,
  license     TEXT NOT NULL,
  url         TEXT,
  meta        JSONB NOT NULL DEFAULT '{}'::jsonb,
  embedding   vector(256) NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source, ext_id)
);
CREATE INDEX IF NOT EXISTS idx_kb_level_kind ON kb_documents(level, kind);
CREATE INDEX IF NOT EXISTS idx_kb_title ON kb_documents(title);
CREATE INDEX IF NOT EXISTS idx_kb_hnsw ON kb_documents USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS kb_ingest_runs (
  id           SERIAL PRIMARY KEY,
  source       TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','done','error')),
  added        INT NOT NULL DEFAULT 0,
  message      TEXT NOT NULL DEFAULT '',
  started_by   INT REFERENCES users(id) ON DELETE SET NULL,
  started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ml_models (
  id          SERIAL PRIMARY KEY,
  name        TEXT NOT NULL,
  version     INT NOT NULL,
  data        BYTEA NOT NULL,
  metrics     JSONB NOT NULL DEFAULT '{}'::jsonb,
  active      BOOLEAN NOT NULL DEFAULT false,
  trained_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (name, version)
);

CREATE TABLE IF NOT EXISTS chat_messages (
  id          SERIAL PRIMARY KEY,
  user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role        TEXT NOT NULL CHECK (role IN ('user','assistant')),
  content     TEXT NOT NULL,
  citations   JSONB NOT NULL DEFAULT '[]'::jsonb,
  level       TEXT,
  run_id      INT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_messages(user_id, id);

-- Questions made by the Course Factory start as drafts until an admin approves them.
ALTER TABLE questions ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'curated';
ALTER TABLE questions ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'published';
ALTER TABLE questions ADD COLUMN IF NOT EXISTS sources JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE turns ADD COLUMN IF NOT EXISTS answer_level TEXT;
