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

    model_config = SettingsConfigDict(env_file=".env")

config = Config()