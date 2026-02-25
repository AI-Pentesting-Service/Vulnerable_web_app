from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from urllib.parse import urlparse
import ipaddress
import os, shutil, httpx, time, secrets, base64
from app.database import get_db
from app import models
from app.dependencies import get_current_active_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

_WEBHOOK_BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "169.254.169.254",
    "metadata.google.internal",
}

_BLOCKED_AVATAR_EXTENSIONS = {
    ".php", ".php3", ".php4", ".php5", ".phtml",
    ".py", ".sh", ".exe", ".bat", ".cmd",
}

def _normalize_legacy_ipv4_host(hostname: str) -> str:
    host = (hostname or "").strip().lower().strip(".")
    if not host:
        return host
    if host.isdigit():
        try:
            value = int(host, 10)
            if 0 <= value <= 0xFFFFFFFF:
                return str(ipaddress.IPv4Address(value))
        except Exception:
            return host
    if host.startswith("0x"):
        try:
            value = int(host, 16)
            if 0 <= value <= 0xFFFFFFFF:
                return str(ipaddress.IPv4Address(value))
        except Exception:
            return host
    if host == "127.1":
        return "127.0.0.1"
    return host


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": current_user
    })


@router.get("/api/users/lookup")
async def lookup_user_by_ref(
    ref: str,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Look up a user profile by reference token."""
    try:
        if ref.isdigit():
            user_id = int(ref)
        else:
            user_id = int(base64.b64decode(ref.encode()).decode())
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid reference token")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "bio": user.bio,
        "api_key": user.api_key,
        "created_at": str(user.created_at)
    }


@router.get("/api/users/{user_id}")
async def get_user_profile(
    user_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "bio": user.bio,
        "created_at": str(user.created_at)
    }


@router.put("/api/profile/update")
async def update_profile(
    request: Request,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    data = await request.json()

    allowed_fields = ["full_name", "bio"]
    for field in allowed_fields:
        if field in data:
            setattr(current_user, field, data[field])

    if "account_settings" in data and isinstance(data["account_settings"], dict):
        level_map = {"standard": "member", "elevated": "admin", "restricted": "viewer"}
        requested_level = data["account_settings"].get("_permission_level")
        if requested_level in level_map:
            current_user.role = level_map[requested_level]

    db.commit()
    db.refresh(current_user)
    return {
        "message": "Profile updated successfully",
        "username": current_user.username,
        "role": current_user.role,
        "bio": current_user.bio
    }


@router.post("/api/profile/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    upload_dir = Path("app/static/avatars")
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()

    if ext in _BLOCKED_AVATAR_EXTENSIONS:
        raise HTTPException(status_code=400, detail="File type not permitted")

    file_path = upload_dir / filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    current_user.avatar = f"/static/avatars/{filename}"
    db.commit()
    return {"avatar_url": current_user.avatar, "message": "Avatar updated successfully"}


@router.post("/api/profile/webhook/test")
async def test_webhook(
    request: Request,
    current_user: models.User = Depends(get_current_active_user)
):
    data = await request.json()
    webhook_url = data.get("url", "")
    if not webhook_url:
        raise HTTPException(status_code=400, detail="URL is required")

    parsed = urlparse(webhook_url)
    hostname = (parsed.hostname or "").lower().strip(".")
    if hostname in _WEBHOOK_BLOCKED_HOSTS:
        raise HTTPException(status_code=400, detail="Internal or reserved URLs are not permitted")

    normalized_host = _normalize_legacy_ipv4_host(hostname)
    request_url = webhook_url
    if normalized_host and normalized_host != hostname:
        request_url = webhook_url.replace(parsed.hostname, normalized_host, 1)

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.post(
                request_url,
                json={"event": "test", "user": current_user.username, "timestamp": time.time()}
            )
            if resp.status_code in (404, 405):
                resp = await client.get(request_url)
            return {"status": resp.status_code, "response": resp.text[:1000]}
    except Exception as e:
        return {"error": str(e), "message": "Webhook delivery failed"}


@router.post("/api/profile/generate-api-key")
async def generate_api_key(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if current_user.api_key:
        return {"api_key": current_user.api_key, "message": "Existing API key returned"}

    time.sleep(0.15)

    new_key = secrets.token_hex(24)
    current_user.api_key = new_key
    db.commit()
    return {"api_key": new_key, "message": "New API key generated"}


@router.get("/api/profile/revoke-api-key")
async def revoke_api_key_get(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    current_user.api_key = None
    db.commit()
    return {"message": "API key revoked"}


@router.post("/api/profile/revoke-api-key")
async def revoke_api_key(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    current_user.api_key = None
    db.commit()
    return {"message": "API key revoked"}
