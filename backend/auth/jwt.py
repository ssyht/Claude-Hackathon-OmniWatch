from jose import jwt, JWTError
from datetime import datetime, timedelta
import os

SECRET = os.getenv("JWT_SECRET", "changeme")
ALGO   = os.getenv("JWT_ALGORITHM", "HS256")
EXPIRE = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=EXPIRE)
    return jwt.encode(payload, SECRET, algorithm=ALGO)

def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET, algorithms=[ALGO])
    except JWTError:
        return None