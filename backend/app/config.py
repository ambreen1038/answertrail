from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / "backend" / ".env", extra="ignore")

    # Name of the product the knowledge base describes; used in the prompt and the UI.
    product_name: str = "InvoiceFlow"
    database_url: str = "postgresql://postgres:postgres@localhost:5433/support"
    gemini_api_key: str = ""
    # Pinned to a concrete model on purpose: "-latest" aliases can silently change what answers
    # you get, which would invalidate the published evaluation numbers.
    gen_model: str = "gemini-3.5-flash-lite"
    embed_model: str = "gemini-embedding-001"
    embed_dim: int = 768
    top_k: int = 5
    # Sanity floor only: below this cosine similarity for the best chunk we refuse without
    # calling the LLM. It is NOT what separates answerable from unanswerable questions: on the
    # eval set their top scores overlap (0.67-0.85 vs 0.52-0.74), so the model's own
    # "do the sources answer this?" check does that work. See eval results in the README.
    min_similarity: float = 0.5
    # Hybrid search: merge the meaning-based (vector) ranking with a keyword (full-text) ranking using
    # reciprocal rank fusion. OFF by default: on this 58-chunk corpus every variant I measured was no
    # better than plain vector search and the naive ones were worse (README, "Hybrid search"). It is
    # worth trying again on a large corpus with exact identifiers such as part numbers or error codes.
    hybrid_search: bool = False
    hybrid_candidates: int = 20   # how many results each ranking contributes before merging
    rrf_k: int = 60               # fusion constant; 60 is the value from the original RRF paper
    # The keyword ranking only uses words that appear in at most this share of all chunks. Postgres
    # full-text ranking has no notion of word rarity, so without this, common words ("invoice",
    # "upload") pull generic chunks into the results and crowd out relevant ones (measured: see README).
    hybrid_max_term_share: float = 0.10
    # True: a chunk must contain ALL the distinctive words to count as a keyword match (an exact-term
    # match, high precision). False: ANY of them is enough, which on a small corpus mostly adds noise.
    hybrid_match_all: bool = True
    kb_dir: Path = ROOT / "kb"
    eval_results_path: Path = ROOT / "backend" / "eval" / "results.json"
    cors_origins: str = "http://localhost:3000"
    max_question_chars: int = 500

    # --- admin login (Supabase Auth) ---
    # The backend never holds a password or a service-role key. It forwards the signed-in user's
    # access token to Supabase and asks "who is this?". If any of these is empty the admin API is
    # disabled entirely (fails closed).
    supabase_url: str = ""          # e.g. https://abcdefgh.supabase.co
    supabase_anon_key: str = ""     # the public (anon) key; safe to be public by design
    admin_emails: str = ""          # comma-separated allowlist of admin email addresses

    # --- rate limiting for the public chat endpoint (each question costs Gemini quota) ---
    rate_limit_per_minute: int = 10            # per client (IP)
    rate_limit_per_client_per_day: int = 150   # per client (IP), per UTC day
    rate_limit_global_per_day: int = 500       # everyone together, per UTC day: the cost backstop
    rate_limit_max_clients: int = 5000         # how many clients we remember (bounds memory)

    # --- document upload (admin) ---
    max_upload_mb: int = 10
    max_pdf_pages: int = 100
    max_chunks_per_document: int = 400  # bounds embedding cost for one upload
    chunk_max_chars: int = 800          # soft cap for headingless text and PDF pages
    chunk_overlap_chars: int = 100
    section_max_chars: int = 1200       # markdown sections longer than this get split


settings = Settings()
