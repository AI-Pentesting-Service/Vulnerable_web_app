from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pathlib import Path
import shutil
import os
import uuid
from typing import Optional
from app.database import get_db
from app import models
from app.dependencies import get_current_active_user
from app.config import settings

router = APIRouter()

@router.post("/api/files/upload")
async def upload_file(
    project_id: int,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if file.size and file.size > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large")

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = upload_dir / unique_filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_record = models.File(
        filename=unique_filename,
        original_filename=file.filename,
        filepath=str(file_path),
        file_size=file.size,
        mime_type='application/xml' if file.filename.lower().endswith('.xml') else file.content_type,
        project_id=project_id,
        uploader_id=current_user.id
    )
    db.add(file_record)
    db.commit()
    db.refresh(file_record)
    return file_record

@router.get("/api/files/{file_id}")
async def get_file_info(
    file_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    return file_record

@router.get("/api/files/{file_id}/download")
async def download_file(
    file_id: int,
    path: Optional[str] = None,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if path:
        if ".." in path:
            raise HTTPException(status_code=400, detail="Invalid path")
        file_path = os.path.join(settings.UPLOAD_DIR, path)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(
            path=file_path,
            filename=os.path.basename(file_path)
        )

    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    if not os.path.exists(file_record.filepath):
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=file_record.filepath,
        filename=file_record.original_filename,
        media_type=file_record.mime_type
    )

@router.delete("/api/files/{file_id}")
async def delete_file(
    file_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    if os.path.exists(file_record.filepath):
        os.remove(file_record.filepath)

    db.delete(file_record)
    db.commit()
    return {"message": "File deleted successfully"}

@router.post("/api/files/process")
async def process_file(
    file_id: int,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    file_record = db.query(models.File).filter(models.File.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    if not os.path.exists(file_record.filepath):
        raise HTTPException(status_code=404, detail="File not found on disk")

    try:
        fname = file_record.original_filename.lower()
        if fname.endswith('.xml') or (file_record.mime_type and 'xml' in file_record.mime_type):
            with open(file_record.filepath, 'rb') as f:
                content = f.read()
            try:
                from lxml import etree
                parser = etree.XMLParser(resolve_entities=True, no_network=False, load_dtd=True, huge_tree=True)
                tree = etree.fromstring(content, parser)
                tree.getroottree().xinclude()
                root_tag = tree.tag
                text_content = tree.text or ""
                for child in tree:
                    text_content += (child.text or "")
                return {"message": "XML processed", "root": root_tag, "content": text_content}
            except ImportError:
                import xml.etree.ElementTree as ET
                tree = ET.fromstring(content.decode('utf-8', errors='replace'))
                return {"message": "XML processed", "elements": len(list(tree))}
            except Exception as xml_err:
                raise xml_err

        elif fname.endswith('.pkl') or fname.endswith('.pickle'):
            import pickle
            with open(file_record.filepath, 'rb') as f:
                raw = f.read()
            obj = pickle.loads(raw)
            return {"message": "Report loaded", "type": type(obj).__name__, "preview": str(obj)[:500]}

        elif file_record.mime_type and "image" in file_record.mime_type:
            from PIL import Image
            img = Image.open(file_record.filepath)
            return {
                "message": "Image processed",
                "dimensions": f"{img.width}x{img.height}",
                "format": img.format
            }
        else:
            with open(file_record.filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(1000)
            return {"message": "File processed", "preview": content[:200]}

    except Exception as e:
        return {"message": "File processed", "status": "completed", "info": str(e)}