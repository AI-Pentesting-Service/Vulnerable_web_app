from fastapi import APIRouter, Depends, HTTPException, Request, Query, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import List
import httpx
from app.database import get_db
from app import models, schemas
from app.dependencies import get_current_active_user, require_admin

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    total_users = db.query(func.count(models.User.id)).scalar()
    total_projects = db.query(func.count(models.Project.id)).scalar()
    total_tasks = db.query(func.count(models.Task.id)).scalar()
    recent_users = db.query(models.User).order_by(models.User.created_at.desc()).limit(10).all()

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "user": current_user,
        "total_users": total_users,
        "total_projects": total_projects,
        "total_tasks": total_tasks,
        "recent_users": recent_users
    })

@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(
    request: Request,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "user": current_user
    })

@router.get("/api/admin/users")
async def list_all_users(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    users = db.query(models.User).all()
    return [{"id": u.id, "username": u.username, "email": u.email,
             "role": u.role, "is_active": u.is_active, "api_key": u.api_key} for u in users]

@router.put("/api/admin/users/{user_id}")
async def update_user(
    user_id: int,
    user_update: schemas.UserUpdate,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user_update.full_name:
        user.full_name = user_update.full_name
    if user_update.role:
        user.role = user_update.role

    db.commit()
    db.refresh(user)
    return user

@router.delete("/api/admin/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    db.delete(user)
    db.commit()
    return {"message": "User deleted successfully"}

@router.get("/api/analytics/export")
async def export_analytics(
    start_date: str = Query(default=None),
    end_date: str = Query(default=None),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Export analytics data."""
    users = db.query(models.User).all()
    projects = db.query(models.Project).all()
    return {
        "generated_by": current_user.username,
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "role": u.role,
                "api_key": u.api_key,
                "created_at": str(u.created_at),
            }
            for u in users
        ],
        "projects": [
            {"id": p.id, "name": p.name, "owner_id": p.owner_id, "is_private": p.is_private}
            for p in projects
        ],
        "totals": {"users": len(users), "projects": len(projects)},
    }


@router.get("/api/admin/stats")
async def get_system_stats(
    current_user: models.User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    stats = {
        "total_users": db.query(func.count(models.User.id)).scalar(),
        "total_projects": db.query(func.count(models.Project.id)).scalar(),
        "total_tasks": db.query(func.count(models.Task.id)).scalar(),
        "total_files": db.query(func.count(models.File.id)).scalar(),
        "active_users": db.query(func.count(models.User.id)).filter(models.User.is_active == True).scalar()
    }
    return stats

@router.post("/api/admin/fetch-url")
async def fetch_external_url(
    url: str = Query(...),
    current_user: models.User = Depends(require_admin),
):
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url)
            return {
                "status_code": response.status_code,
                "content": response.text[:2000],
                "headers": dict(response.headers)
            }
    except Exception as e:
        return {"error": str(e), "message": "Failed to fetch URL"}

@router.post("/api/admin/execute-query")
async def execute_custom_query(
    query: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        result = db.execute(text(query))
        db.commit()
        if result.returns_rows:
            rows = result.fetchall()
            return {
                "success": True,
                "rows": [dict(row._mapping) for row in rows],
                "count": len(rows)
            }
        else:
            return {"success": True, "message": "Query executed successfully"}
    except Exception as e:
        return {"success": False, "error": str(e)}
