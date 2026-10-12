import json
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, Form, Request, UploadFile, File, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.models import (
    User, Group, Module, Lesson, AssignmentMaterial, Quiz, QuizQuestion, Submission, QuizResult
)
from app.auth import require_tutor, hash_password
from app.services.storage import storage_service
from app.config import BASE_DIR

router = APIRouter(prefix="/tutor", dependencies=[Depends(require_tutor)])
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


# --- Dashboard ---

@router.get("/dashboard", response_class=HTMLResponse)
def tutor_dashboard(request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_tutor)):
    groups = db.query(Group).all()
    students_count = db.query(User).filter(User.role == "student").count()
    
    # Submissions needing review
    pending_submissions = db.query(Submission).filter(Submission.status == "submitted").order_by(Submission.submitted_at.desc()).all()
    
    # Storage status
    storage_status = storage_service.get_status()

    return templates.TemplateResponse(
        request=request,
        name="tutor/dashboard.html",
        context={
            "current_user": current_user,
            "groups": groups,
            "students_count": students_count,
            "pending_submissions": pending_submissions,
            "storage_status": storage_status,
        }
    )


# --- Groups Management ---

@router.get("/groups", response_class=HTMLResponse)
def tutor_groups(request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_tutor)):
    groups = db.query(Group).all()
    return templates.TemplateResponse(
        request=request,
        name="tutor/groups.html",
        context={"current_user": current_user, "groups": groups}
    )


@router.post("/groups/add")
def tutor_add_group(
    name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_tutor)
):
    group = Group(name=name.strip(), description=description.strip())
    db.add(group)
    db.commit()
    db.refresh(group)
    return RedirectResponse(url=f"/tutor/group/{group.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/group/{group_id}", response_class=HTMLResponse)
def tutor_group_view(group_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_tutor)):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")

    return templates.TemplateResponse(
        request=request,
        name="tutor/group_view.html",
        context={"current_user": current_user, "group": group}
    )


# --- Group Submissions Matrix (Светофор: зеленые галочки / красные индикаторы) ---

@router.get("/group/{group_id}/matrix", response_class=HTMLResponse)
def tutor_group_matrix(group_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_tutor)):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")

    students = db.query(User).filter(User.group_id == group_id, User.role == "student").order_by(User.full_name).all()
    
    # Get all lessons across modules in this group
    lessons = []
    for module in group.modules:
        for lesson in module.lessons:
            lessons.append(lesson)

    # Build matrix map: (student_id, lesson_id) -> submission / status
    submissions = db.query(Submission).filter(
        Submission.lesson_id.in_([l.id for l in lessons]) if lessons else False,
        Submission.student_id.in_([s.id for s in students]) if students else False
    ).all()

    sub_map = {(sub.student_id, sub.lesson_id): sub for sub in submissions}

    # Also map quiz results
    quiz_results = db.query(QuizResult).filter(
        QuizResult.student_id.in_([s.id for s in students]) if students else False
    ).all()
    quiz_map = {(qr.student_id, qr.quiz_id): qr for qr in quiz_results}

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Matrix data structure
    matrix_rows = []
    for s in students:
        row_cells = []
        for l in lessons:
            sub = sub_map.get((s.id, l.id))
            qr = quiz_map.get((s.id, l.quiz.id)) if l.quiz else None

            # Determine indicator
            # green: submitted or reviewed (or quiz passed)
            # yellow: submitted but needs review
            # red: not submitted and deadline passed (or active deadline)
            if sub:
                if sub.status == "reviewed":
                    status_type = "reviewed"  # 🟢
                elif sub.status == "needs_revision":
                    status_type = "revision"  # 🟠
                else:
                    status_type = "submitted"  # 🟡
            elif qr and qr.passed:
                status_type = "quiz_passed"  # 🟢
            else:
                if l.deadline and now > l.deadline:
                    status_type = "overdue"  # 🔴
                else:
                    status_type = "missing"  # 🔴 (Не приступал)

            row_cells.append({
                "lesson": l,
                "submission": sub,
                "quiz_result": qr,
                "status_type": status_type
            })

        matrix_rows.append({"student": s, "cells": row_cells})

    return templates.TemplateResponse(
        request=request,
        name="tutor/group_matrix.html",
        context={
            "current_user": current_user,
            "group": group,
            "lessons": lessons,
            "matrix_rows": matrix_rows,
            "now": now
        }
    )


# --- Modules & Lessons ---

@router.post("/group/{group_id}/module/add")
def tutor_add_module(
    group_id: int,
    title: str = Form(...),
    description: str = Form(""),
    order: int = Form(1),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_tutor)
):
    mod = Module(group_id=group_id, title=title.strip(), description=description.strip(), order=order)
    db.add(mod)
    db.commit()
    return RedirectResponse(url=f"/tutor/group/{group_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/module/{module_id}/lesson/add")
def tutor_add_lesson(
    module_id: int,
    title: str = Form(...),
    description: str = Form(""),
    deadline: Optional[str] = Form(None),
    order: int = Form(1),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_tutor)
):
    dl_dt = None
    if deadline:
        try:
            dl_dt = datetime.fromisoformat(deadline)
        except Exception:
            dl_dt = None

    mod = db.query(Module).filter(Module.id == module_id).first()
    if not mod:
        raise HTTPException(status_code=404, detail="Модуль не найден")

    lesson = Lesson(
        module_id=module_id,
        title=title.strip(),
        description=description.strip(),
        deadline=dl_dt,
        order=order
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    return RedirectResponse(url=f"/tutor/lesson/{lesson.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/lesson/{lesson_id}", response_class=HTMLResponse)
def tutor_lesson_edit(
    lesson_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_tutor)
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Урок не найден")

    submissions = db.query(Submission).filter(Submission.lesson_id == lesson_id).all()
    storage_status = storage_service.get_status()

    return templates.TemplateResponse(
        request=request,
        name="tutor/lesson_edit.html",
        context={
            "current_user": current_user,
            "lesson": lesson,
            "submissions": submissions,
            "storage_status": storage_status
        }
    )


@router.post("/lesson/{lesson_id}/update")
def tutor_lesson_update(
    lesson_id: int,
    title: str = Form(...),
    description: str = Form(""),
    deadline: Optional[str] = Form(None),
    has_homework: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_tutor)
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Урок не найден")

    dl_dt = None
    if deadline:
        try:
            dl_dt = datetime.fromisoformat(deadline)
        except Exception:
            dl_dt = None

    lesson.title = title.strip()
    lesson.description = description.strip()
    lesson.deadline = dl_dt
    lesson.has_homework = has_homework
    db.commit()

    return RedirectResponse(url=f"/tutor/lesson/{lesson_id}", status_code=status.HTTP_303_SEE_OTHER)


# --- Assignment Materials (File upload to Google Drive / link / text) ---

@router.post("/lesson/{lesson_id}/material/add")
async def tutor_add_material(
    lesson_id: int,
    material_type: str = Form(...),  # 'file', 'link', 'text'
    title: str = Form(...),
    description: str = Form(""),
    external_link: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_tutor)
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Урок не найден")

    file_url = None
    file_name = None
    file_size = None
    gdrive_file_id = None

    if material_type == "file" and file and file.filename:
        upload_res = await storage_service.upload_file(file)
        file_url = upload_res["file_url"]
        file_name = upload_res["file_name"]
        file_size = upload_res["file_size"]
        gdrive_file_id = upload_res.get("file_id")

    material = AssignmentMaterial(
        lesson_id=lesson_id,
        material_type=material_type,
        title=title.strip(),
        description=description.strip() if description else None,
        external_link=external_link.strip() if external_link else None,
        file_url=file_url,
        file_name=file_name,
        file_size=file_size,
        gdrive_file_id=gdrive_file_id
    )
    db.add(material)
    db.commit()

    return RedirectResponse(url=f"/tutor/lesson/{lesson_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/material/{material_id}/delete")
def tutor_delete_material(
    material_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_tutor)
):
    mat = db.query(AssignmentMaterial).filter(AssignmentMaterial.id == material_id).first()
    if mat:
        lesson_id = mat.lesson_id
        db.delete(mat)
        db.commit()
        return RedirectResponse(url=f"/tutor/lesson/{lesson_id}", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/tutor/dashboard", status_code=status.HTTP_303_SEE_OTHER)


# --- Quiz Builder ---

@router.get("/lesson/{lesson_id}/quiz", response_class=HTMLResponse)
def tutor_quiz_edit(
    lesson_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_tutor)
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Урок не найден")

    quiz = lesson.quiz
    if not quiz:
        quiz = Quiz(lesson_id=lesson_id, title=f"Тест к уроку: {lesson.title}", passing_score=70)
        db.add(quiz)
        db.commit()
        db.refresh(quiz)

    return templates.TemplateResponse(
        request=request,
        name="tutor/quiz_edit.html",
        context={"current_user": current_user, "lesson": lesson, "quiz": quiz}
    )


@router.post("/quiz/{quiz_id}/question/add")
def tutor_add_quiz_question(
    quiz_id: int,
    question_text: str = Form(...),
    question_type: str = Form(...),  # 'single', 'multiple', 'text'
    options: str = Form(""),
    correct_answers: str = Form(""),
    points: int = Form(1),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_tutor)
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Тест не найден")

    opts_list = [opt.strip() for opt in options.split("\n") if opt.strip()]
    if question_type in ["single", "multiple"]:
        correct_list = [c.strip() for c in correct_answers.split(",") if c.strip()]
    else:
        correct_list = [correct_answers.strip()]

    question = QuizQuestion(
        quiz_id=quiz_id,
        question_text=question_text.strip(),
        question_type=question_type,
        options_json=json.dumps(opts_list, ensure_ascii=False),
        correct_answers_json=json.dumps(correct_list, ensure_ascii=False),
        points=points,
        order=len(quiz.questions) + 1
    )
    db.add(question)
    db.commit()

    return RedirectResponse(url=f"/tutor/lesson/{quiz.lesson_id}/quiz", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/question/{question_id}/delete")
def tutor_delete_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_tutor)
):
    q = db.query(QuizQuestion).filter(QuizQuestion.id == question_id).first()
    if q:
        lesson_id = q.quiz.lesson_id
        db.delete(q)
        db.commit()
        return RedirectResponse(url=f"/tutor/lesson/{lesson_id}/quiz", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/tutor/dashboard", status_code=status.HTTP_303_SEE_OTHER)


# --- Submissions Review & Grading ---

@router.get("/submission/{submission_id}", response_class=HTMLResponse)
def tutor_review_submission(
    submission_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_tutor)
):
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Ответ не найден")

    return templates.TemplateResponse(
        request=request,
        name="tutor/review.html",
        context={"current_user": current_user, "submission": sub}
    )


@router.post("/submission/{submission_id}/grade")
def tutor_grade_submission(
    submission_id: int,
    grade: str = Form(...),
    tutor_comment: str = Form(""),
    status_choice: str = Form("reviewed"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_tutor)
):
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Ответ не найден")

    sub.grade = grade.strip()
    sub.tutor_comment = tutor_comment.strip()
    sub.status = status_choice
    sub.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()

    return RedirectResponse(url=f"/tutor/group/{sub.lesson.module.group_id}/matrix", status_code=status.HTTP_303_SEE_OTHER)


# --- Students Management ---

@router.get("/students", response_class=HTMLResponse)
def tutor_students(request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_tutor)):
    students = db.query(User).filter(User.role == "student").order_by(User.full_name).all()
    groups = db.query(Group).all()
    return templates.TemplateResponse(
        request=request,
        name="tutor/students.html",
        context={"current_user": current_user, "students": students, "groups": groups}
    )


@router.post("/students/add")
def tutor_add_student(
    full_name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    group_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_tutor)
):
    clean_user = username.strip().lower()
    existing = db.query(User).filter(User.username == clean_user).first()
    if existing:
        raise HTTPException(status_code=400, detail="Пользователь с таким логином уже существует")

    student = User(
        full_name=full_name.strip(),
        username=clean_user,
        password_hash=hash_password(password),
        plain_password=password,
        role="student",
        group_id=group_id
    )
    db.add(student)
    db.commit()

    return RedirectResponse(url="/tutor/students", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/settings", response_class=HTMLResponse)
def tutor_settings(request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_tutor)):
    storage_status = storage_service.get_status()
    from app.config import TUTOR_CONTACTS
    return templates.TemplateResponse(
        request=request,
        name="tutor/settings.html",
        context={
            "current_user": current_user,
            "storage_status": storage_status,
            "tutor_contacts": TUTOR_CONTACTS,
            "message": request.query_params.get("msg")
        }
    )


@router.post("/settings/upload_key")
async def tutor_settings_upload_key(
    file: Optional[UploadFile] = File(None),
    json_text: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_tutor)
):
    from app.config import GDRIVE_SERVICE_ACCOUNT_FILE
    content = ""
    if file and file.filename:
        file_bytes = await file.read()
        content = file_bytes.decode("utf-8", errors="ignore")
    elif json_text and json_text.strip():
        content = json_text.strip()

    if content:
        # Validate that it's json
        try:
            json.loads(content)
            with open(GDRIVE_SERVICE_ACCOUNT_FILE, "w", encoding="utf-8") as f:
                f.write(content)
            storage_service.reload()
            return RedirectResponse(url="/tutor/settings?msg=key_saved", status_code=status.HTTP_303_SEE_OTHER)
        except Exception as e:
            return RedirectResponse(url=f"/tutor/settings?msg=error_{str(e)}", status_code=status.HTTP_303_SEE_OTHER)

    return RedirectResponse(url="/tutor/settings", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/contacts")
def tutor_settings_update_contacts(
    phone: str = Form(""),
    telegram: str = Form(""),
    email: str = Form(""),
    whatsapp: str = Form(""),
    max_link: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_tutor)
):
    from app.config import TUTOR_CONTACTS
    TUTOR_CONTACTS["phone"] = phone.strip()
    TUTOR_CONTACTS["telegram"] = telegram.strip()
    TUTOR_CONTACTS["email"] = email.strip()
    TUTOR_CONTACTS["whatsapp"] = whatsapp.strip()
    TUTOR_CONTACTS["max"] = max_link.strip()
    return RedirectResponse(url="/tutor/settings?msg=contacts_saved", status_code=status.HTTP_303_SEE_OTHER)

