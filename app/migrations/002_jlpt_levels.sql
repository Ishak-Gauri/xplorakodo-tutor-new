-- JLPT N5–N1: difficulty 1..5 maps to N5..N1; topics belong to a track (caregiving | jlpt).
ALTER TABLE questions DROP CONSTRAINT IF EXISTS questions_difficulty_check;
ALTER TABLE questions ADD CONSTRAINT questions_difficulty_check CHECK (difficulty BETWEEN 1 AND 5);
ALTER TABLE topics ADD COLUMN IF NOT EXISTS track TEXT NOT NULL DEFAULT 'caregiving';
ALTER TABLE topics ADD COLUMN IF NOT EXISTS jlpt_level TEXT;
