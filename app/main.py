xfrom fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from app.config import settings
from app.database import engine, Base
from app.routers import auth, projects, tasks, files, comments, admin, internal, profile
import traceback
from pathlib import Path

Base.metadata.create_all(bind=engine)

# Ensure avatar upload directory exists at startup
Path("app/static/avatars").mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

app.include_router(auth.router, tags=["auth"])
app.include_router(projects.router, tags=["projects"])
app.include_router(tasks.router, tags=["tasks"])
app.include_router(files.router, tags=["files"])
app.include_router(comments.router, tags=["comments"])
app.include_router(admin.router, tags=["admin"])
app.include_router(internal.router, tags=["internal"])
app.include_router(profile.router, tags=["profile"])

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if settings.SHOW_ERROR_DETAILS:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": str(exc),
                "type": type(exc).__name__,
                "traceback": traceback.format_exc(),
                "path": str(request.url),
                "method": request.method
            }
        )
    else:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Internal server error"}
        )

@app.get("/")
async def root():
    return RedirectResponse(url="/login")

@app.get("/health")
async def health():
    return {"status": "healthy", "version": settings.VERSION}
