import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    DATABASE_URL = os.getenv("DATABASE_URL")
    OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "http://localhost:9200")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
