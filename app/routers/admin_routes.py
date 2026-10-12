import json
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Form, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.models import User, Group, Module, Lesson, Submission, QuizResult
from app.auth import require_admin, hash_password
from app.config import BASE_DIR, TUTOR_CONTACTS
from app.services.storage import storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@router.get("/dashboard", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Main Administrator control dashboard.
    Shows high-level metrics across the whole school: tutors, students, groups,
    recent homework submissions, and Google Drive storage optimization stats.
    """
    tutors = db.query(User).filter(User.role == "tutor").order_by(User.full_name).all()
    students_count = db.query(User).filter(User.role == "student").count()
    groups = db.query(Group).all()
    groups_count = len(groups)
    lessons_count = db.query(Lesson).count()
    submissions_count = db.query(Submission).count()
    submissions_pending = db.query(Submission).filter(Submission.status == "submitted").count()

    recent_submissions = db.query(Submission).order_by(Submission.submitted_at.desc()).limit(8).all()
    storage_status = storage_service.get_status()

    return templates.TemplateResponse(
        request=request,
        name="admin/dashboard.html",
        context={
            "current_user": current_user,
            "tutors": tutors,
            "tutors_count": len(tutors),
            "students_count": students_count,
            "groups_count": groups_count,
            "lessons_count": lessons_count,
            "submissions_count": submissions_count,
            "submissions_pending": submissions_pending,
            "recent_submissions": recent_submissions,
            "storage_status": storage_status,
            "tutor_contacts": TUTOR_CONTACTS,
            "message": request.query_params.get("msg")
        }
    )


@router.get("/tutors", response_class=HTMLResponse)
def admin_tutors_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Manage teachers / tutors in KIBERone."""
    tutors = db.query(User).filter(User.role == "tutor").order_by(User.full_name).all()
    admins = db.query(User).filter(User.role == "admin").all()
    groups = db.query(Group).all()

    return templates.TemplateResponse(
        request=request,
        name="admin/tutors.html",
        context={
            "current_user": current_user,
            "tutors": tutors,
            "admins": admins,
            "groups": groups,
            "message": request.query_params.get("msg")
        }
    )


@router.post("/tutors/add")
def admin_add_tutor(
    full_name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    phone: str = Form(""),
    telegram: str = Form(""),
    email: str = Form(""),
    whatsapp: str = Form(""),
    max_link: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    clean_username = username.strip().lower()
    existing = db.query(User).filter(User.username == clean_username).first()
    if existing:
        return RedirectResponse(
            url="/admin/tutors?msg=error_username_exists",
            status_code=status.HTTP_303_SEE_OTHER
        )

    new_tutor = User(
        full_name=full_name.strip(),
        username=clean_username,
        password_hash=hash_password(password),
        plain_password=password,
        role="tutor",
        phone=phone.strip(),
        telegram=telegram.strip(),
        email=email.strip(),
        whatsapp=whatsapp.strip(),
        max_link=max_link.strip()
    )
    db.add(new_tutor)
    db.commit()
    logger.info(f"Administrator {current_user.username} created new tutor @{clean_username}")

    return RedirectResponse(
        url="/admin/tutors?msg=tutor_added",
        status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/tutors/{tutor_id}/edit")
def admin_edit_tutor(
    tutor_id: int,
    full_name: str = Form(...),
    password: Optional[str] = Form(None),
    phone: str = Form(""),
    telegram: str = Form(""),
    email: str = Form(""),
    whatsapp: str = Form(""),
    max_link: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    tutor = db.query(User).filter(User.id == tutor_id, User.role.in_(["tutor", "admin"])).first()
    if not tutor:
        raise HTTPException(status_code=404, detail="Преподаватель не найден")

    tutor.full_name = full_name.strip()
    if password and password.strip():
        tutor.password_hash = hash_password(password.strip())
        tutor.plain_password = password.strip()

    tutor.phone = phone.strip()
    tutor.telegram = telegram.strip()
    tutor.email = email.strip()
    tutor.whatsapp = whatsapp.strip()
    tutor.max_link = max_link.strip()

    db.commit()
    logger.info(f"Administrator {current_user.username} updated profile for @{tutor.username}")

    return RedirectResponse(
        url="/admin/tutors?msg=tutor_updated",
        status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/tutors/{tutor_id}/delete")
def admin_delete_tutor(
    tutor_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    if tutor_id == current_user.id:
        return RedirectResponse(
            url="/admin/tutors?msg=error_cannot_delete_self",
            status_code=status.HTTP_303_SEE_OTHER
        )

    tutor = db.query(User).filter(User.id == tutor_id, User.role == "tutor").first()
    if tutor:
        db.delete(tutor)
        db.commit()
        logger.info(f"Administrator {current_user.username} deleted tutor @{tutor.username}")
        return RedirectResponse(
            url="/admin/tutors?msg=tutor_deleted",
            status_code=status.HTTP_303_SEE_OTHER
        )

    return RedirectResponse(
        url="/admin/tutors?msg=error_not_found",
        status_code=status.HTTP_303_SEE_OTHER
    )
