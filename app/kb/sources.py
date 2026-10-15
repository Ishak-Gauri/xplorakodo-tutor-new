"""Knowledge-base sources. Each returns a list of documents:
{source, ext_id, kind, level, title, text, license, url, meta}.

bundled     JLPT vocabulary + kanji lists and grammar notes shipped in data/kb (no network needed)
curriculum  the tutor's own lessons (model answers) and handbook notes
tatoeba     Japanese example sentences (+ English when available), levelled by the Leveler   [internet]
wikipedia   articles about Japanese, the JLPT and caregiving in Japan (EN + JA)              [internet]
kaggle      any Kaggle dataset with Japanese words / sentences and JLPT levels (needs a key) [internet]
"""
from __future__ import annotations

import base64
import bz2
import csv
import gzip
import io
import json
import os
import random
import re
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent.parent / "data"
UA = "XploraKodoTutor/3.1 (education project; contact: admin@xplorakodo.com)"
LEVELS = ["N5", "N4", "N3", "N2", "N1"]
_JA = re.compile(r"[぀-ヿ一-鿿]")


def _get(url: str, timeout: int = 60, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# ------------------------------------------------------------------ bundled
def bundled() -> list[dict]:
    docs = []
    for name in ("vocab", "kanji"):
        with gzip.open(DATA / "kb" / f"{name}.jsonl.gz", "rt", encoding="utf-8") as f:
            docs += [json.loads(line) for line in f]
    for g in json.loads((DATA / "kb" / "grammar.json").read_text(encoding="utf-8")):
        docs.append({"source": "grammar", "ext_id": g["id"], "kind": "grammar", "level": g["level"], "title": g["pattern"],
                     "text": f"{g['pattern']}: {g['en']} 例: {g['ja']} ({g['ja_en']})",
                     "license": "CC BY 4.0 (XploraKodo original notes)", "url": None,
                     "meta": {"ne": g["ne"], "example": g["ja"], "example_en": g["ja_en"]}})
    return docs


# ------------------------------------------------------------------ curriculum
def curriculum(handbook: list[tuple[str, str]]) -> list[dict]:
    docs = []
    for name in ("lessons.json", "interview.json"):
        for t in json.loads((DATA / name).read_text(encoding="utf-8"))["topics"]:
            level = t.get("jlpt_level")
            for v in t.get("vocab", []):
                docs.append({"source": "curriculum", "ext_id": f"vocab:{t['id']}:{v['jp']}", "kind": "lesson", "level": level,
                             "title": v["jp"], "text": f"{v['jp']} ({v.get('reading', '')}) = {v['en']} / {v.get('ne', '')}",
                             "license": "XploraKodo course content", "meta": {"topic_id": t["id"]}})
            for q in t["questions"]:
                ma = q.get("model_answer", {})
                docs.append({"source": "curriculum", "ext_id": f"answer:{q['id']}", "kind": "lesson", "level": level,
                             "title": q["prompt"].get("en", "")[:120],
                             "text": f"Q: {q['prompt'].get('en', '')} A: {ma.get('en', '')} {ma.get('ja', '')}",
                             "license": "XploraKodo course content", "meta": {"topic_id": t["id"], "question_id": q["id"]}})
    for i, (tid, text) in enumerate(handbook):
        level = {"jlpt_n5": "N5", "jlpt_n4": "N4", "jlpt_n3": "N3", "jlpt_n2": "N2", "jlpt_n1": "N1"}.get(tid)
        docs.append({"source": "curriculum", "ext_id": f"handbook:{i}", "kind": "handbook", "level": level,
                     "title": text[:80], "text": text, "license": "XploraKodo course content", "meta": {"topic_id": tid}})
    return docs


# ------------------------------------------------------------------ tatoeba
TATOEBA = "https://downloads.tatoeba.org/exports/per_language"


def _tsv_bz2(url: str):
    raw = bz2.decompress(_get(url, timeout=300))
    for line in raw.decode("utf-8", errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            yield parts


def tatoeba(estimator, per_level: int = 1500, with_english: bool = True, seed: int = 3, log=print) -> list[dict]:
    """Japanese sentences from Tatoeba (CC BY 2.0 FR), levelled by the hybrid Leveler, balanced per level."""
    log("downloading Tatoeba Japanese sentences...")
    sentences = [(p[0], p[2]) for p in _tsv_bz2(f"{TATOEBA}/jpn/jpn_sentences.tsv.bz2") if 5 <= len(p[2]) <= 60]
    log(f"{len(sentences)} Japanese sentences")
    english: dict[str, str] = {}
    if with_english:
        try:
            links = {}
            raw = bz2.decompress(_get(f"{TATOEBA}/jpn/jpn-eng_links.tsv.bz2", timeout=300)).decode()
            for line in raw.splitlines():
                a, _, b = line.partition("\t")
                links.setdefault(a, b.strip())
            log(f"{len(links)} jpn-eng links; downloading English sentences...")
            wanted = set(links.values())
            eng = {p[0]: p[2] for p in _tsv_bz2(f"{TATOEBA}/eng/eng_sentences.tsv.bz2") if p[0] in wanted}
            english = {j: eng[e] for j, e in links.items() if e in eng}
            log(f"{len(english)} sentences have an English translation")
        except Exception as e:  # the links file is optional
            log(f"English translations skipped: {e}")
    rng = random.Random(seed)
    rng.shuffle(sentences)
    # Prefer sentences with a translation, then fill each level up to `per_level`.
    sentences.sort(key=lambda s: s[0] not in english)
    buckets: dict[str, list[dict]] = {lv: [] for lv in LEVELS}
    for sid, ja in sentences:
        if all(len(b) >= per_level for b in buckets.values()):
            break
        r = estimator.estimate(ja)
        lv = r["level"]
        if not lv or len(buckets[lv]) >= per_level or r.get("coverage", 0) < 0.5:
            continue
        en = english.get(sid)
        buckets[lv].append({"source": "tatoeba", "ext_id": sid, "kind": "sentence", "level": lv, "title": ja[:80],
                            "text": f"{ja}" + (f" — {en}" if en else ""), "license": "CC BY 2.0 FR (Tatoeba)",
                            "url": f"https://tatoeba.org/en/sentences/show/{sid}",
                            "meta": {"ja": ja, "en": en, "confidence": r["confidence"],
                                     "hardest": [h["text"] for h in r["hardest"][:3]]}})
    out = [d for lv in LEVELS for d in buckets[lv]]
    log("per level: " + ", ".join(f"{lv} {len(buckets[lv])}" for lv in LEVELS))
    return out


# ------------------------------------------------------------------ wikipedia
WIKI_TITLES = {
    "en": ["Japanese-Language Proficiency Test", "Japanese grammar", "Japanese particles", "Honorific speech in Japanese",
           "Japanese verb conjugation", "Kanji", "Hiragana", "Katakana", "Japanese writing system",
           "Caregiver", "Aging of Japan", "Long-term care", "Specified Skilled Worker", "Nepalis in Japan"],
    "ja": ["日本語能力試験", "日本語の文法", "敬語", "助詞", "漢字", "介護福祉士", "介護", "特定技能", "高齢化社会",
           "在日ネパール人"],
}


def _chunks(text: str, size: int = 700) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n{2,}|\n(?==)", text) if len(p.strip()) > 40]
    out, cur = [], ""
    for p in paras:
        if p.startswith("=="):
            continue
        if len(cur) + len(p) > size and cur:
            out.append(cur)
            cur = ""
        cur = (cur + "\n" + p).strip()
    if cur:
        out.append(cur)
    return out


def wikipedia(estimator, titles: dict[str, list[str]] | None = None, max_chunks: int = 12, log=print) -> list[dict]:
    """Plain-text extracts via the MediaWiki API (CC BY-SA 4.0). Japanese chunks are levelled by the Leveler."""
    docs = []
    for lang, names in (titles or WIKI_TITLES).items():
        for title in names:
            params = urllib.parse.urlencode({"action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1,
                                             "titles": title, "format": "json", "formatversion": 2})
            try:
                data = json.loads(_get(f"https://{lang}.wikipedia.org/w/api.php?{params}"))
                page = data["query"]["pages"][0]
                text = page.get("extract") or ""
            except Exception as e:
                log(f"  {lang}:{title} failed: {e}")
                continue
            if not text:
                log(f"  {lang}:{title} not found")
                continue
            url = f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(page['title'].replace(' ', '_'))}"
            for i, chunk in enumerate(_chunks(text)[:max_chunks]):
                level = estimator.estimate(chunk)["level"] if lang == "ja" else None
                docs.append({"source": "wikipedia", "ext_id": f"{lang}:{page['title']}:{i}", "kind": "article", "level": level,
                             "title": f"{page['title']} ({lang})", "text": chunk, "license": "CC BY-SA 4.0 (Wikipedia)",
                             "url": url, "meta": {"lang": lang, "chunk": i}})
            log(f"  {lang}:{page['title']} -> {min(max_chunks, len(_chunks(text)))} chunks")
    return docs


# ------------------------------------------------------------------ kaggle
# Recommended datasets (checked October 2026):
#   celineboutinon/jlpt-master-vocabulary-library-n5-n1   CC BY-SA 4.0     8k+ words, numeric level 5..1, romaji
#   robinpourtaud/jlpt-words-by-level                     CC BY-NC 4.0     Original / Furigana / English / JLPT Level
#   balankdharan7/jlpt-n4-japanese-english-vocabulary-and-more  CC BY-NC-SA 4.0  N4 words + example sentences (CSV + JSON)
# NC = non-commercial: fine for study/research; get the author's permission before commercial use.
KAGGLE_DEFAULTS = ["celineboutinon/jlpt-master-vocabulary-library-n5-n1", "robinpourtaud/jlpt-words-by-level",
                   "balankdharan7/jlpt-n4-japanese-english-vocabulary-and-more"]
WORD_COLS = ("expression", "word", "original", "vocab", "vocabulary", "kanji", "japanese", "term", "jp", "headword", "pattern", "grammar")
READ_COLS = ("reading", "furigana", "kana", "hiragana", "yomi")
MEAN_COLS = ("meaning", "english", "definition", "definitions", "translation", "gloss", "meanings", "en")
LEVEL_COLS = ("jlpt_level", "jlpt level", "jlptlevel", "jlpt", "level", "tags", "tag")
ROMAJI_COLS = ("romaji", "romanization", "romanji")
JA_KEYS = ("japanese", "ja", "jp", "jpn", "sentence", "text", "example", "ja_sentence", "japanese_sentence")
EN_KEYS = ("english", "en", "eng", "translation", "meaning", "en_sentence", "english_sentence")


def _pick(cols, names):
    low = {str(c).lower().strip(): c for c in cols}
    for n in names:  # exact names first
        if n in low:
            return low[n]
    for n in names:  # then partial (but never a *_difficulty / *_id helper column)
        for lc, c in low.items():
            if n in lc and not lc.endswith(("difficulty", "_id", "frequency")):
                return c
    return None


def parse_level(value) -> str | None:
    """'N5', 'n5', 'JLPT N5', 'jlpt-n5', 5, '5', 5.0 -> 'N5'."""
    if value is None:
        return None
    s = str(value).strip()
    m = re.search(r"(?<![A-Za-z])[Nn]\s*-?\s*([1-5])(?![0-9])", s)
    if m:
        return f"N{m.group(1)}"
    m = re.fullmatch(r"([1-5])(\.0)?", s)
    return f"N{m.group(1)}" if m else None


def _kaggle_license(slug: str) -> str:
    try:
        data = json.loads(_get(f"https://www.kaggle.com/api/v1/datasets/view/{slug}", timeout=30))
        return data.get("licenseName") or "see dataset page"
    except Exception:
        return "see dataset page"


def _kaggle_files(slug: str, log=print) -> list[tuple[str, bytes]]:
    """Files of a Kaggle dataset: kagglehub when installed (works for public datasets), else the REST API."""
    try:
        import kagglehub  # pip install kagglehub

        root = Path(kagglehub.dataset_download(slug))
        log(f"  downloaded with kagglehub to {root}")
        return [(str(p.relative_to(root)), p.read_bytes()) for p in sorted(root.rglob("*")) if p.is_file()]
    except ImportError:
        pass
    except Exception as e:
        log(f"  kagglehub failed ({str(e)[:120]}), trying the REST API")
    headers = {}
    user, key = os.getenv("KAGGLE_USERNAME"), os.getenv("KAGGLE_KEY")
    if user and key:
        headers["Authorization"] = "Basic " + base64.b64encode(f"{user}:{key}".encode()).decode()
    blob = _get(f"https://www.kaggle.com/api/v1/datasets/download/{slug}", timeout=300, headers=headers)
    zf = zipfile.ZipFile(io.BytesIO(blob))
    return [(n, zf.read(n)) for n in zf.namelist() if not n.endswith("/")]


def _records(name: str, data: bytes) -> list[dict]:
    low = name.lower()
    text = data.decode("utf-8-sig", errors="replace")
    if low.endswith((".csv", ".tsv")):
        return list(csv.DictReader(io.StringIO(text), delimiter="\t" if low.endswith(".tsv") else ","))
    if low.endswith(".jsonl"):
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if low.endswith(".json"):
        obj = json.loads(text)
        if isinstance(obj, dict):  # {"vocabulary": [...], "grammar": [...]} or {"N5": [...]}
            rows = []
            for k, v in obj.items():
                if isinstance(v, list):
                    for r in v:
                        if isinstance(r, dict):
                            rows.append({"_group": k, **r})
            return rows
        return [r for r in obj if isinstance(r, dict)]
    return []


def _examples(row: dict) -> list[tuple[str, str]]:
    """Example sentences hidden in a record: list fields, nested dicts, or example_ja/example_en columns."""
    out = []
    for key, val in row.items():
        k = str(key).lower()
        if not any(w in k for w in ("example", "sentence")):
            continue
        items = val if isinstance(val, list) else [val]
        for it in items:
            if isinstance(it, dict):
                ja = next((str(it[x]) for x in it if str(x).lower() in JA_KEYS and _JA.search(str(it[x]))), "")
                en = next((str(it[x]) for x in it if str(x).lower() in EN_KEYS and not _JA.search(str(it[x]))), "")
                if ja:
                    out.append((ja.strip(), en.strip()))
            elif isinstance(it, str) and _JA.search(it) and len(it) > 3:
                en_key = next((c for c in row if str(c).lower() in (k.replace("ja", "en"), k.replace("jp", "en"),
                                                                    k.replace("japanese", "english"))), None)
                out.append((it.strip(), str(row.get(en_key) or "").strip() if en_key and en_key != key else ""))
    return out


def kaggle(datasets: list[str], estimator, max_rows: int = 30000, log=print) -> list[dict]:
    """Map Kaggle JLPT datasets to knowledge-base documents (vocabulary, grammar, example sentences)."""
    docs = []
    for slug in [d.strip() for d in datasets if d.strip()]:
        lic = _kaggle_license(slug)
        log(f"kaggle:{slug} - licence: {lic}")
        files = _kaggle_files(slug, log)
        n_before = len(docs)
        for name, data in files:
            all_rows = _records(name, data)
            groups: dict[str, list[tuple[int, dict]]] = {}
            for i, r in enumerate(all_rows[:max_rows]):  # JSON files can mix vocabulary, grammar, ... sections
                groups.setdefault(str(r.get("_group", "")), []).append((i, r))
            for gname, rows_ in groups.items():
                cols = list({k for _, r in rows_[:50] for k in r.keys()})
                wc, rc, mc = _pick(cols, WORD_COLS), _pick(cols, READ_COLS), _pick(cols, MEAN_COLS)
                lc, roc = _pick(cols, LEVEL_COLS), _pick(cols, ROMAJI_COLS)
                log(f"  {name}{'/' + gname if gname else ''}: {len(rows_)} rows; word={wc} reading={rc} meaning={mc} level={lc}")
                if not wc:
                    continue
                for i, row in rows_:
                    word = str(row.get(wc) or "").strip()
                    if not word or not _JA.search(word):
                        continue
                    level = parse_level(row.get(lc)) if lc else None
                    if not level:  # e.g. "N4 vocabulary" datasets put the level in the file/group name
                        level = parse_level(row.get("_group")) or parse_level(name) or parse_level(slug)
                    from_dataset = bool(level)
                    if not level:
                        level = estimator.estimate(word)["level"]
                    reading = str(row.get(rc) or "").strip() if rc else ""
                    meaning = row.get(mc) if mc else ""
                    meaning = "; ".join(map(str, meaning)) if isinstance(meaning, list) else str(meaning or "").strip()
                    romaji = str(row.get(roc) or "").strip() if roc else ""
                    group = str(row.get("_group") or "").lower()
                    kind = "grammar" if "grammar" in group or "grammar" in name.lower() else \
                        "sentence" if len(word) > 12 else "vocab"
                    base = {"license": f"{lic} (Kaggle: {slug})", "url": f"https://www.kaggle.com/datasets/{slug}"}
                    docs.append({"source": f"kaggle:{slug}", "ext_id": f"{name}:{i}", "kind": kind, "level": level, "title": word[:80],
                                 "text": word + (f"（{reading}）" if reading and reading != word else "") + (f": {meaning}" if meaning else ""),
                                 "meta": {"reading": reading, "meaning": meaning, "romaji": romaji, "ja": word,
                                          "level_from": "dataset" if from_dataset else "leveler"}, **base})
                    for j, (ja, en) in enumerate(_examples(row)[:3]):
                        lv = estimator.estimate(ja)["level"] or level
                        docs.append({"source": f"kaggle:{slug}", "ext_id": f"{name}:{i}:ex{j}", "kind": "sentence", "level": lv,
                                     "title": ja[:80], "text": ja + (f" — {en}" if en else ""),
                                     "meta": {"ja": ja, "en": en, "word": word, "level_from": "leveler"}, **base})
        log(f"  kaggle:{slug} -> {len(docs) - n_before} documents")
    return docs
