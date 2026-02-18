from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text, or_
from typing import List, Optional
from app.database import get_db
from app import models, schemas
from app.dependencies import get_current_active_user, optional_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    projects = db.query(models.Project).filter(
        or_(
            models.Project.owner_id == current_user.id,
            models.Project.members.any(id=current_user.id)
        )
    ).all()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": current_user,
        "projects": projects
    })

@router.get("/projects", response_class=HTMLResponse)
async def projects_page(
    request: Request,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    projects = db.query(models.Project).filter(
        or_(
            models.Project.owner_id == current_user.id,
            models.Project.members.any(id=current_user.id)
        )
    ).all()
    return templates.TemplateResponse("projects.html", {
        "request": request,
        "user": current_user,
        "projects": projects
    })

@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(
    request: Request,
    project_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    tasks = db.query(models.Task).filter(models.Task.project_id == project_id).all()
    files = db.query(models.File).filter(models.File.project_id == project_id).all()
    members = db.query(models.User).all()

    return templates.TemplateResponse("project_detail.html", {
        "request": request,
        "user": current_user,
        "project": project,
        "tasks": tasks,
        "files": files,
        "members": members
    })

@router.get("/api/projects")
async def list_projects(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    projects = db.query(models.Project).filter(
        or_(
            models.Project.owner_id == current_user.id,
            models.Project.members.any(id=current_user.id)
        )
    ).all()
    return projects

@router.get("/api/projects/search")
async def search_projects(
    q: str = Query(...),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    query = f"SELECT * FROM projects WHERE name LIKE '%{q}%' OR description LIKE '%{q}%'"
    result = db.execute(text(query))
    projects = result.fetchall()
    return {"query": q, "results": [dict(row._mapping) for row in projects]}

@router.post("/api/projects")
async def create_project(
    project: schemas.ProjectCreate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    new_project = models.Project(
        name=project.name,
        description=project.description,
        is_private=project.is_private,
        owner_id=current_user.id
    )
    db.add(new_project)
    db.commit()
    db.refresh(new_project)

    new_project.members.append(current_user)
    db.commit()
    return new_project

@router.get("/api/projects/{project_id}")
async def get_project(
    project_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.put("/api/projects/{project_id}")
async def update_project(
    project_id: int,
    project_update: schemas.ProjectCreate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project.name = project_update.name
    project.description = project_update.description
    project.is_private = project_update.is_private
    db.commit()
    db.refresh(project)
    return project

@router.delete("/api/projects/{project_id}")
async def delete_project(
    project_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only project owner can delete")

    db.delete(project)
    db.commit()
    return {"message": "Project deleted successfully"}

@router.post("/api/projects/{project_id}/members")
async def add_project_member(
    project_id: int,
    user_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user not in project.members:
        project.members.append(user)
        db.commit()
    return {"message": "Member added successfully"}
