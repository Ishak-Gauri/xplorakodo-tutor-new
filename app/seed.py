"""Seed the database from data/*.json, build the RAG knowledge base, create the admin.

Runs on every startup and is idempotent: it only inserts rows that are missing, so
questions edited in the admin console are never overwritten.

    python -m app.seed            # seed now
    python -m app.seed --reembed  # recompute every embedding (after switching EMBEDDING_PROVIDER)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .db import J, Database, vec
from .security import hash_password

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

HANDBOOK = [
    ("basic_nursing", "Vital signs (バイタルサイン) in Japanese care: 体温 body temperature, 血圧 blood pressure, 脈拍 pulse, 呼吸 breathing. Always record the value and time, and report anything unusual to the nurse (看護師)."),
    ("basic_nursing", "Caregivers in Japan do not give medicine (薬) on their own judgement. Check with the nurse, confirm the resident's name, and record it."),
    ("elder_care", "Polite request forms: ～てください (please do), ～ましょうか (shall I / shall we), お～ください (more honorific). Commands like 手伝え or 気をつけろ sound rude to residents."),
    ("elder_care", "Dementia (認知症) care: stay calm, answer repeated questions kindly every time, never scold, and protect the resident's dignity (尊厳)."),
    ("hygiene", "Hand hygiene (手洗い・手指消毒): before and after contact with a resident, before meals, after the toilet and after removing gloves (手袋). Use masks and aprons to prevent infection."),
    ("hygiene", "Before bathing (入浴): check the resident's condition (体調, vital signs) and the water temperature (お湯の温度). Avoid sudden temperature changes (ヒートショック)."),
    ("emergency_protocol", "Emergency numbers in Japan: 119 for ambulance (救急車) and fire (火事); 110 for police. After a fall (転倒): do not move the person, check consciousness and breathing, call for help, then write an incident report with time, place and condition."),
    ("emergency_protocol", "Earthquake (地震): protect residents' heads, stay away from windows, do not run outside while shaking, then follow the evacuation plan (避難場所)."),
    ("communication", "ほうれんそう = 報告 (report), 連絡 (contact / inform), 相談 (consult). Report mistakes quickly and honestly. Use です・ます forms with supervisors (分かりました, not 分かった)."),
    ("communication", "Personal information (個人情報) is protected. Refer questions from families about medical details to the nurse or supervisor."),
    ("daily_living", "脱健着患: when dressing a resident with a weak side, put clothes on the weak (affected) side first and take them off from the strong side first."),
    ("jlpt_n5", "JLPT has five levels: N5 (beginner) to N1 (advanced). N5 covers basic particles (は, を, に, へ), ます-form verbs, past tense ～ました and negative ～ません, numbers and about 100 kanji."),
    ("jlpt_n4", "JLPT N4 grammar: ～たことがあります (experience), ～てはいけません (prohibition), potential form (食べられます), ～そう (looks like), ～ので (reason). Caregiving visas usually expect about N4."),
    ("jlpt_n3", "JLPT N3 grammar: ～ようにする (try to / habit), ～たら (if/when), ～ことにする (decide), ～わけではない (it is not that), ～のに (even though, unexpected result)."),
    ("jlpt_n2", "JLPT N2 business Japanese: 検討する (consider), 把握 (grasp), 対応 (handling), ～ざるを得ない (have no choice but), ～にもかかわらず (despite), ～に関して (regarding)."),
    ("jlpt_n1", "JLPT N1 advanced expressions: 懸念 (concern), 顕著 (remarkable), 是正 (correction), ～を踏まえて (based on), ～ずにはいられない (cannot help), ～をよそに (ignoring), ～かねない (there is a risk that)."),
    ("daily_living", "自立支援 (support for independence): let residents do what they can, help only where needed, and watch over them (見守り) for safety. Protect privacy during toileting (排泄)."),
]


def _load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def question_text(q: dict) -> str:
    return " ".join([q["prompt"].get("en", ""), q["prompt"].get("ja", ""), q.get("model_answer", {}).get("en", "")])


def seed_content(db: Database, embedder) -> dict:
    """Batched with executemany (psycopg pipelines it), so a remote database such as Neon
    needs a few round trips instead of hundreds."""
    lessons, placement, interview = _load("lessons.json"), _load("placement.json"), _load("interview.json")
    all_topics = [(t, "practice") for t in lessons["topics"]] + [(t, "interview") for t in interview["topics"]]
    topic_rows = [(t["id"], kind, J(t["title"]), J(t.get("summary", {})), J(t.get("vocab", [])), pos,
                   t.get("track", "interview" if kind == "interview" else "caregiving"), t.get("jlpt_level"))
                  for pos, (t, kind) in enumerate(all_topics)]
    question_rows = [(q["id"], t["id"], q["skill"], q.get("difficulty", 1), J(q["prompt"]), J(q["keywords"]),
                      J(q.get("model_answer", {})), J(q.get("probe", {}))) for t, _ in all_topics for q in t["questions"]]
    placement_rows = [(it["id"], J(it["q"]), J(it["options"]), it["answer"], it.get("difficulty", 1)) for it in placement["items"]]
    with db.tx() as conn, conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO topics(id, kind, title, summary, vocab, position, track, jlpt_level) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET track = EXCLUDED.track, "
            "jlpt_level = EXCLUDED.jlpt_level, position = EXCLUDED.position", topic_rows)
        cur.executemany(
            "INSERT INTO questions(id, topic_id, skill, difficulty, prompt, keywords, model_answer, probe) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING", question_rows)
        cur.executemany(
            "INSERT INTO placement_items(ext_id, q, options, answer, difficulty) VALUES (%s,%s,%s,%s,%s) "
            "ON CONFLICT (ext_id) DO UPDATE SET q = EXCLUDED.q, options = EXCLUDED.options, "
            "answer = EXCLUDED.answer, difficulty = EXCLUDED.difficulty", placement_rows)

    # Embeddings for questions that do not have one yet (new seed rows or admin edits).
    missing = db.all("SELECT id, prompt, model_answer FROM questions WHERE embedding IS NULL")
    if missing:
        vectors = embedder.embed_many([question_text(q) for q in missing])
        with db.tx() as conn, conn.cursor() as cur:
            cur.executemany("UPDATE questions SET embedding = %s::vector WHERE id = %s",
                            [(vec(v), q["id"]) for q, v in zip(missing, vectors)])

    # The knowledge base (bundled levels + curriculum) is loaded by app.kb.ingest.bootstrap_if_empty.
    return {"topics": len(topic_rows), "questions": len(question_rows), "embedded": len(missing)}


def seed_users(db: Database, settings) -> None:
    db.run("INSERT INTO organizations(name) VALUES ('XploraKodo Academy') ON CONFLICT (name) DO NOTHING")
    org_id = db.scalar("SELECT id FROM organizations WHERE name = 'XploraKodo Academy'")
    if not db.one("SELECT id FROM users WHERE email = %s", (settings.admin_email,)):
        db.run("INSERT INTO users(email, password_hash, name, role, org_id) VALUES (%s,%s,%s,'admin',%s)",
               (settings.admin_email, hash_password(settings.admin_password), settings.admin_name, org_id))
    if settings.seed_demo and not db.one("SELECT id FROM users WHERE email = 'demo@xplorakodo.com'"):
        db.run("INSERT INTO users(email, password_hash, name, role, org_id, lang) VALUES (%s,%s,%s,'student',%s,'en')",
               ("demo@xplorakodo.com", hash_password("demo1234"), "Demo Student", org_id))


def reembed(db: Database, embedder) -> None:
    db.run("UPDATE questions SET embedding = NULL")
    for m in db.all("SELECT id, text FROM memories"):
        db.run("UPDATE memories SET embedding = %s::vector WHERE id = %s", (vec(embedder.embed(m["text"])), m["id"]))
    db.run("UPDATE kb_documents SET text = text")  # kb vectors are rebuilt by re-running ingestion


if __name__ == "__main__":
    from .config import get_settings
    from .embeddings import make_embedder

    s = get_settings()
    database = Database(s.database_url)
    database.migrate()
    emb = make_embedder(s.embedding_provider)
    if "--reembed" in sys.argv:
        reembed(database, emb)
    print(seed_content(database, emb))
    seed_users(database, s)
    print("seeded")
