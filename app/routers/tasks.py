from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from app.database import get_db
from app import models, schemas
from app.dependencies import get_current_active_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/tasks", response_class=HTMLResponse)
async def tasks_page(
    request: Request,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    tasks = db.query(models.Task).filter(models.Task.assignee_id == current_user.id).all()
    return templates.TemplateResponse("tasks.html", {
        "request": request,
        "user": current_user,
        "tasks": tasks
    })

@router.get("/api/tasks")
async def list_tasks(
    project_id: Optional[int] = None,
    sort_by: str = Query(default="created_at"),
    direction: str = Query(default="DESC"),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    ALLOWED_COLUMNS = {"title", "status", "priority", "created_at", "updated_at"}
    if sort_by not in ALLOWED_COLUMNS:
        sort_by = "created_at"

    if project_id:
        raw_sql = text(f"SELECT * FROM tasks WHERE project_id = :pid ORDER BY {sort_by} {direction}")
        result = db.execute(raw_sql, {"pid": project_id})
    else:
        raw_sql = text(f"SELECT * FROM tasks ORDER BY {sort_by} {direction}")
        result = db.execute(raw_sql)

    return [dict(row._mapping) for row in result.fetchall()]

@router.post("/api/tasks")
async def create_task(
    task: schemas.TaskCreate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    project = db.query(models.Project).filter(models.Project.id == task.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    new_task = models.Task(
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        project_id=task.project_id,
        assignee_id=task.assignee_id,
        created_by=current_user.id
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task

@router.get("/api/tasks/{task_id}")
async def get_task(
    task_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.put("/api/tasks/{task_id}")
async def update_task(
    task_id: int,
    task_update: schemas.TaskUpdate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task_update.title is not None:
        task.title = task_update.title
    if task_update.description is not None:
        task.description = task_update.description
    if task_update.status is not None:
        task.status = task_update.status
    if task_update.priority is not None:
        task.priority = task_update.priority
    if task_update.assignee_id is not None:
        task.assignee_id = task_update.assignee_id

    db.commit()
    db.refresh(task)
    return task

@router.delete("/api/tasks/{task_id}")
async def delete_task(
    task_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"message": "Task deleted successfully"}

@router.post("/api/tasks/{task_id}/transfer")
async def transfer_task_ownership(
    task_id: int,
    new_owner_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    new_owner = db.query(models.User).filter(models.User.id == new_owner_id).first()
    if not new_owner:
        raise HTTPException(status_code=404, detail="User not found")

    task.created_by = new_owner_id
    db.commit()
    return {"message": "Task ownership transferred"}
