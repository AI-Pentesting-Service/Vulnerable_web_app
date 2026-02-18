from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
import os, shutil, httpx, time, secrets
from app.database import get_db
from app import models
from app.dependencies import get_current_active_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

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

@router.get("/api/users/{user_id}")
async def get_user_profile(
    user_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
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
        "avatar": user.avatar,
        "created_at": str(user.created_at)
    }

@router.put("/api/profile/update")
async def update_profile(
    request: Request,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    data = await request.json()
    allowed_fields = ['full_name', 'bio', 'role']
    for field in allowed_fields:
        if field in data:
            setattr(current_user, field, data[field])
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

    filename = file.filename
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

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.post(
                webhook_url,
                json={"event": "test", "user": current_user.username, "timestamp": time.time()}
            )
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
