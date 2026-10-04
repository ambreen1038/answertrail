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
    kb_dir: Path = ROOT / "kb"
    cors_origins: str = "http://localhost:3000"
    max_question_chars: int = 500

    # --- admin login (Supabase Auth) ---
    # The backend never holds a password or a service-role key. It forwards the signed-in user's
    # access token to Supabase and asks "who is this?". If any of these is empty the admin API is
    # disabled entirely (fails closed).
    supabase_url: str = ""          # e.g. https://abcdefgh.supabase.co
    supabase_anon_key: str = ""     # the public (anon) key; safe to be public by design
    admin_emails: str = ""          # comma-separated allowlist of admin email addresses

    # --- document upload (admin) ---
    max_upload_mb: int = 10
    max_pdf_pages: int = 100
    max_chunks_per_document: int = 400  # bounds embedding cost for one upload
    chunk_max_chars: int = 800          # soft cap for headingless text and PDF pages
    chunk_overlap_chars: int = 100
    section_max_chars: int = 1200       # markdown sections longer than this get split


settings = Settings()
