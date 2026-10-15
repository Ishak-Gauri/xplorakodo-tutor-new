# Knowledge-base data sources and licences

| Data | Source | Licence | Notes |
|---|---|---|---|
| `vocab.jsonl.gz` (7,896 JLPT N5–N1 words) | [open-anki-jlpt-decks](https://github.com/jamsinclair/open-anki-jlpt-decks) by Jamie Sinclair | MIT | Word lists originate from Jonathan Waller's JLPT resources (tanos.co.uk, CC BY). |
| `kanji.jsonl.gz`, `kanji_meta.json.gz` (2,211 JLPT kanji; frequency/strokes/grade for 13k kanji) | [KANJIDIC](https://www.edrdg.org/wiki/index.php/KANJIDIC_Project) (EDRDG) via [kanji-data](https://github.com/davidluzgouveia/kanji-data) | CC BY-SA 4.0 (KANJIDIC), MIT (kanji-data) | WaniKani fields removed. Derived files keep the CC BY-SA 4.0 licence. |
| `grammar.json` (50 grammar notes) | XploraKōdo, written for this project | CC BY 4.0 | Original wording; Nepali needs native review. |
| Tatoeba sentences (ingested at runtime) | [tatoeba.org](https://tatoeba.org) downloads | CC BY 2.0 FR | Each document links to its sentence page. |
| Wikipedia chunks (ingested at runtime) | en/ja.wikipedia.org via the MediaWiki API | CC BY-SA 4.0 | Each document links to its article. |
| Kaggle: [JLPT Master Vocabulary Library (N5-N1)](https://www.kaggle.com/datasets/celineboutinon/jlpt-master-vocabulary-library-n5-n1) | celineboutinon | CC BY-SA 4.0 | Commercial use OK with attribution + share-alike. |
| Kaggle: [JLPT vocabulary by level](https://www.kaggle.com/datasets/robinpourtaud/jlpt-words-by-level) | robinpourtaud | CC BY-NC 4.0 | **Non-commercial.** Flagged in the admin; excluded from model training by default. |
| Kaggle: [JLPT N4 vocabulary and more](https://www.kaggle.com/datasets/balankdharan7/jlpt-n4-japanese-english-vocabulary-and-more) | balankdharan7 | CC BY-NC-SA 4.0 | **Non-commercial.** Same handling as above. |
| Nepali meanings (`meta.ne`) | Generated with the configured LLM from English meanings | — | Machine translation: have a native speaker review before production. |

Commercial textbooks (Genki, Minna no Nihongo, official JLPT workbooks) are copyrighted and are not included.
`scripts/build_bundled_kb.py` rebuilds the bundled files from the source repositories.
