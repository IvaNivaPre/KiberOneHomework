import os
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

from app.config import BASE_DIR, UPLOAD_DIR
from app.database import engine, Base
from app.routers import auth_routes, tutor_routes, student_routes

# Initialize DB tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="KiberOne - Платформа домашних заданий",
    description="Система сдачи, хранения (Google Drive) и проверки ДЗ для KiberOne",
    version="1.0.0"
)

# Mount static and uploads
static_dir = BASE_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# Include Routers
app.include_router(auth_routes.router)
app.include_router(tutor_routes.router)
app.include_router(student_routes.router)

# Custom Jinja2 Template Filters
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

def format_datetime(val: datetime, fmt: str = "%d.%m.%Y в %H:%M") -> str:
    if not val:
        return ""
    return val.strftime(fmt)

def format_deadline_badge(dl: datetime) -> str:
    if not dl:
        return "Без дедлайна"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    diff = dl - now
    if diff.total_seconds() < 0:
        return "Дедлайн истек!"
    days = diff.days
    hours = int(diff.seconds // 3600)
    if days > 0:
        return f"Осталось: {days} д. {hours} ч."
    return f"Осталось: {hours} ч. {int((diff.seconds % 3600) // 60)} мин."

def format_filesize(num_bytes: int) -> str:
    if not num_bytes:
        return ""
    for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} ТБ"

templates.env.filters["datetime"] = format_datetime
templates.env.filters["deadline_badge"] = format_deadline_badge
templates.env.filters["filesize"] = format_filesize

auth_routes.templates.env.filters.update(templates.env.filters)
tutor_routes.templates.env.filters.update(templates.env.filters)
student_routes.templates.env.filters.update(templates.env.filters)
