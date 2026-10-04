from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / "backend" / ".env", extra="ignore")

    # Name of the product the knowledge base describes; used in the prompt and the UI.
    product_name: str = "InvoiceFlow"
    database_url: str = "postgresql://postgres:postgres@localhost:5433/support"
    gemini_api_key: str = ""
    gen_model: str = "gemini-flash-lite-latest"
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


settings = Settings()
