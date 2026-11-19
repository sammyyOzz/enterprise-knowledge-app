from datetime import timedelta

from pydantic_settings import BaseSettings, SettingsConfigDict

class Config(BaseSettings):
    # ================================
    # API KEYS
    # ================================
    OPENAI_API_KEY: str
    GROQ_API_KEY: str
    GOOGLE_API_KEY: str

    # ================================
    # DATABASE
    # ================================
    DATABASE_URL: str

    # ================================
    # REDIS
    # ================================
    REDIS_URL: str

    # ================================
    # S3
    # ================================
    S3_ENDPOINT_URL: str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_BUCKET: str

    # ================================
    # EMBEDDINGS
    # ================================
    EMBEDDING_DIM: int = 1536
    EMBEDDING_MODEL: str = "text-embedding-3-small"


    # ================================
    # INGESTION
    # ================================
    MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024  # 25 MB
    MAX_FILENAME_LENGTH: int = 200
    # A PENDING/PROCESSING version whose latest job hasn't moved for this long is
    # considered stuck (e.g. worker killed) and may be retried.
    STALE_AFTER: timedelta = timedelta(minutes=15)

    # Extension -> canonical MIME type (browsers report MIME types unreliably).
    ALLOWED_TYPES: dict[str, str] = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".csv": "text/csv",
    }

    # ================================
    # CHUNKING
    # ================================
    CHUNK_MAX_TOKENS: int = 600
    CHUNK_OVERLAP_TOKENS: int = 80
    MAX_CHUNKS_PER_DOCUMENT: int = 10_000  # cost/time guard for embedding

    # ================================
    # LLM / RETRIEVAL
    # ================================
    LLM_PROVIDER: str = "openai"
    LLM_MODEL: str = "gpt-4.1"
    LLM_REASONING_EFFORT: str | None = None
    LLM_MAX_OUTPUT_TOKENS: int = 2000
    RETRIEVAL_TOP_K: int = 6
    RETRIEVAL_MIN_SCORE: float = 0.25
    CHAT_HISTORY_MESSAGES: int = 6

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

app_config = Config()