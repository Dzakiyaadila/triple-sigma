import os
from dotenv import load_dotenv

load_dotenv()

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:3000"
).split(",")

DATABASE_URL = os.getenv("DATABASE_URL", "")