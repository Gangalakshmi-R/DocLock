from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app import config
from app.schemas import LoginBody
from app.security import create_token, credentials_valid, login_limiter, current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginBody, request: Request):
    if not config.PASSWORD or not config.JWT_SECRET:
        raise HTTPException(status_code=503, detail="Authentication is not configured. Set DOCLOCK_PASSWORD and DOCLOCK_JWT_SECRET.")
    client = request.client.host if request.client else "unknown"
    login_limiter.check(client)
    if not credentials_valid(body.username, body.password):
        login_limiter.record_failure(client)
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    login_limiter.reset(client)
    return {"token": create_token(config.USERNAME), "username": config.USERNAME}


@router.get("/me")
def me(user: str = Depends(current_user)):
    return {"username": user}
