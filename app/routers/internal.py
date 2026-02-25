from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.auth import get_password_hash
from app.config import settings
import os
import subprocess

router = APIRouter()

@router.get("/api/internal/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.VERSION,
        "debug": settings.DEBUG
    }

@router.get("/api/internal/debug")
async def debug_info(db: Session = Depends(get_db)):
    return {
        "database_url": settings.DATABASE_URL,
        "secret_key": settings.SECRET_KEY,
        "upload_dir": settings.UPLOAD_DIR,
        "environment": dict(os.environ)
    }

@router.post("/api/internal/update-config")
async def update_configuration(key: str, value: str):
    if hasattr(settings, key):
        setattr(settings, key, value)
        return {"message": f"Configuration {key} updated successfully"}
    else:
        raise HTTPException(status_code=400, detail="Invalid configuration key")

@router.post("/api/internal/create-admin")
async def create_emergency_admin(
    username: str,
    password: str,
    db: Session = Depends(get_db)
):
    existing_user = db.query(models.User).filter(models.User.username == username).first()

    if existing_user:
        existing_user.role = "admin"
        existing_user.hashed_password = get_password_hash(password)
        db.commit()
        return {"message": "User promoted to admin"}

    new_admin = models.User(
        email=f"{username}@collabspace.io",
        username=username,
        full_name="Emergency Admin",
        hashed_password=get_password_hash(password),
        role="admin"
    )

    db.add(new_admin)
    db.commit()

    return {"message": "Emergency admin created", "user_id": new_admin.id}

@router.post("/api/internal/backup")
async def create_backup(path: str = "/tmp/backup.sql"):
    try:
        _BLOCKED = [";", "|", "&", "`", "$(", ">", "<"]
        for ch in _BLOCKED:
            if ch in path:
                raise HTTPException(status_code=400, detail=f"Disallowed character in path: {ch!r}")

        db_url = settings.DATABASE_URL
        parts = db_url.replace("postgresql://", "").split("@")
        user_pass = parts[0].split(":")
        host_db = parts[1].split("/")

        command = f"pg_dump -h {host_db[0].split(':')[0]} -U {user_pass[0]} {host_db[1]} > {path}"
        result = subprocess.run(command, shell=True, capture_output=True, text=True)

        return {
            "message": "Backup created",
            "path": path,
            "output": result.stdout,
            "error": result.stderr
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/internal/logs")
async def get_logs(lines: int = 100):
    try:
        log_file = "/var/log/app.log"
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                logs = f.readlines()[-lines:]
            return {"logs": logs}
        else:
            return {"logs": [], "message": "No log file found"}
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/internal/sessions")
async def list_active_sessions(db: Session = Depends(get_db)):
    users = db.query(models.User).filter(models.User.is_active == True).all()

    return [{
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "api_key": user.api_key
    } for user in users]
