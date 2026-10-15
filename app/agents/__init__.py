"""The agent council.

Guardian   kill switch, budget, prompt-injection scan          (deterministic)
AIQ Router topic / question / grader selection by L = NB - Σλ·C  (deterministic)
Smriti     lifetime learning memory in pgvector                  (embeddings)
Retriever  RAG over vocab, model answers and handbook notes      (pgvector HNSW)
Tutor      Kaigo Sensei / Interview Proctor grading              (LLM as a callable asset, or deterministic)
Progress   mastery and heatmap                                   (SQL)
Certifier  signed, QR-verifiable readiness certificate           (deterministic)
"""
