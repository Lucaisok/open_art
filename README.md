# OpenArt

**An application agent for artists** — it discovers open calls, checks eligibility, and helps draft the application.

## What it does

Artists navigating residencies, grants, and commissions face a fragmented landscape: hundreds of institutions, each with its own eligibility rules, buried in dense bureaucratic language. OpenArt reads that language automatically and tells an artist plainly whether they qualify — and why.

## How it works

- **Model** — a classifier trained on a hand-annotated corpus of real opportunities, benchmarked through a proper baseline-to-comparison pipeline (TF-IDF → embeddings, evaluated on precision, recall, F1). It produces a deterministic, auditable eligibility engine: no black-box LLM judgment, just a transparent answer.
- **Recommender** — a content-based recommender ranks eligible calls by semantic similarity to the artist's profile.
- **RAG** — retrieval grounded in the artist's own CV, statement, and portfolio.
- **Agent** — plans, drafts, and assembles a submission, always with the artist reviewing before anything goes out.

## Data

A pilot corpus collected from primary institutional sources — national and regional cultural authorities across the EU.

## Status

Capstone project, in active development.