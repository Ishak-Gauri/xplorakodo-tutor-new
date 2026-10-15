"""Rebuild data/kb/*.jsonl.gz from the open source repos (run once; output is committed).

    git clone https://github.com/jamsinclair/open-anki-jlpt-decks
    git clone https://github.com/davidluzgouveia/kanji-data
    python scripts/build_bundled_kb.py open-anki-jlpt-decks kanji-data

Licences: vocabulary lists - open-anki-jlpt-decks (MIT), based on Jonathan Waller's JLPT resources
(tanos.co.uk, CC BY). Kanji - KANJIDIC (EDRDG, CC BY-SA 4.0) via kanji-data (MIT); WaniKani fields dropped.
"""
import csv
import gzip
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "kb"
VOCAB_LICENSE = "MIT (open-anki-jlpt-decks); list from Jonathan Waller's JLPT resources, CC BY"
KANJI_LICENSE = "CC BY-SA 4.0 (KANJIDIC, EDRDG) via kanji-data (MIT)"


def main(vocab_repo: str, kanji_repo: str) -> None:
    vocab, seen = [], {}
    for lv in ["N5", "N4", "N3", "N2", "N1"]:  # easiest first: a word keeps its easiest level
        with open(Path(vocab_repo) / "src" / f"{lv.lower()}.csv", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                expr, reading, meaning = row["expression"].strip(), row["reading"].strip(), row["meaning"].strip()
                if not expr or expr in seen:
                    continue
                seen[expr] = lv
                vocab.append({"source": "jlpt_vocab", "ext_id": f"v:{expr}", "kind": "vocab", "level": lv,
                              "title": expr, "text": f"{expr}（{reading}）: {meaning}",
                              "license": VOCAB_LICENSE, "url": "https://github.com/jamsinclair/open-anki-jlpt-decks",
                              "meta": {"reading": reading, "meaning": meaning}})
    kanji = []
    data = json.loads((Path(kanji_repo) / "kanji.json").read_text(encoding="utf-8"))
    for ch, k in data.items():
        if not k.get("jlpt_new"):
            continue
        lv = f"N{k['jlpt_new']}"
        meanings = ", ".join(k.get("meanings") or [])
        on, kun = "、".join(k.get("readings_on") or []), "、".join(k.get("readings_kun") or [])
        kanji.append({"source": "kanjidic", "ext_id": f"k:{ch}", "kind": "kanji", "level": lv, "title": ch,
                      "text": f"漢字 {ch}: {meanings}. 音読み {on or '-'}; 訓読み {kun or '-'}; {k.get('strokes')} strokes.",
                      "license": KANJI_LICENSE, "url": "https://www.edrdg.org/wiki/index.php/KANJIDIC_Project",
                      "meta": {"meanings": k.get("meanings"), "on": k.get("readings_on"), "kun": k.get("readings_kun"),
                               "strokes": k.get("strokes"), "grade": k.get("grade"), "freq": k.get("freq")}})
    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in (("vocab", vocab), ("kanji", kanji)):
        with gzip.open(OUT / f"{name}.jsonl.gz", "wt", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(name, len(rows))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
