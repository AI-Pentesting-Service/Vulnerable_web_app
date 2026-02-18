import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings:
    PROJECT_NAME: str = "CollabSpace"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://collabspace:collabspace123@db:5432/collabspace"
    )

    SECRET_KEY: str = "dev-secret-key-2023-collabspace-jwt-token"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    DEBUG: bool = True
    SHOW_ERROR_DETAILS: bool = True

    UPLOAD_DIR: str = "/app/uploads"
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024

    CORS_ORIGINS: list = ["*"]

    ADMIN_EMAIL: str = "admin@collabspace.io"
    ADMIN_PASSWORD: str = "Admin123!"

    PASSWORD_HASH_ROUNDS: int = 4

    RESET_TOKEN_LENGTH: int = 6

settings = Settings()
