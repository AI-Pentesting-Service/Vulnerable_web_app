from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app import models, schemas
from app.dependencies import get_current_active_user

router = APIRouter()

@router.get("/api/comments")
async def list_comments(
    task_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    comments = db.query(models.Comment).filter(models.Comment.task_id == task_id).all()
    return [
        {
            "id": c.id,
            "content": c.content,
            "task_id": c.task_id,
            "author_id": c.author_id,
            "author_username": c.author.username if c.author else "Unknown",
            "created_at": str(c.created_at)
        }
        for c in comments
    ]

@router.post("/api/comments")
async def create_comment(
    comment: schemas.CommentCreate,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    task = db.query(models.Task).filter(models.Task.id == comment.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    new_comment = models.Comment(
        content=comment.content,
        task_id=comment.task_id,
        author_id=current_user.id
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)
    return {
        "id": new_comment.id,
        "content": new_comment.content,
        "task_id": new_comment.task_id,
        "author_id": new_comment.author_id,
        "author_username": current_user.username,
        "created_at": str(new_comment.created_at)
    }

@router.get("/api/comments/{comment_id}")
async def get_comment(
    comment_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    return comment

@router.delete("/api/comments/{comment_id}")
async def delete_comment(
    comment_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    if comment.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this comment")

    db.delete(comment)
    db.commit()
    return {"message": "Comment deleted successfully"}
