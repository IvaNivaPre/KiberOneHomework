import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Form, Request, UploadFile, File, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.models import (
    User, Group, Module, Lesson, AssignmentMaterial, Quiz, QuizQuestion, Submission, QuizResult
)
from app.auth import require_student
from app.services.storage import storage_service
from app.config import BASE_DIR

router = APIRouter(prefix="/student", dependencies=[Depends(require_student)])
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@router.get("/dashboard", response_class=HTMLResponse)
def student_dashboard(request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_student)):
    group = current_user.group
    modules = group.modules if group else []

    # Get student submissions map: lesson_id -> submission
    submissions = db.query(Submission).filter(Submission.student_id == current_user.id).all()
    sub_map = {s.lesson_id: s for s in submissions}

    # Get quiz results map: quiz_id -> QuizResult
    quiz_results = db.query(QuizResult).filter(QuizResult.student_id == current_user.id).all()
    quiz_map = {qr.quiz_id: qr for qr in quiz_results}

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Separate into pending lessons and completed lessons for children
    pending_items = []
    completed_items = []

    for mod in modules:
        for lesson in mod.lessons:
            sub = sub_map.get(lesson.id)
            qr = quiz_map.get(lesson.quiz.id) if lesson.quiz else None
            is_completed = bool(sub or (qr and qr.passed))

            item = {
                "module": mod,
                "lesson": lesson,
                "submission": sub,
                "quiz_result": qr,
                "is_completed": is_completed,
                "is_overdue": bool(lesson.deadline and now > lesson.deadline and not is_completed)
            }
            if is_completed:
                completed_items.append(item)
            else:
                pending_items.append(item)

    return templates.TemplateResponse(
        request=request,
        name="student/dashboard.html",
        context={
            "current_user": current_user,
            "group": group,
            "modules": modules,
            "sub_map": sub_map,
            "quiz_map": quiz_map,
            "pending_items": pending_items,
            "completed_items": completed_items,
            "now": now
        }
    )


@router.get("/lesson/{lesson_id}", response_class=HTMLResponse)
def student_lesson_view(
    lesson_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student)
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Урок не найден")

    # Find existing submission if any
    submission = db.query(Submission).filter(
        Submission.lesson_id == lesson_id,
        Submission.student_id == current_user.id
    ).first()

    # Find quiz result if any
    quiz_result = None
    if lesson.quiz:
        quiz_result = db.query(QuizResult).filter(
            QuizResult.quiz_id == lesson.quiz.id,
            QuizResult.student_id == current_user.id
        ).order_by(QuizResult.submitted_at.desc()).first()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    is_overdue = bool(lesson.deadline and now > lesson.deadline)

    return templates.TemplateResponse(
        request=request,
        name="student/lesson_view.html",
        context={
            "current_user": current_user,
            "lesson": lesson,
            "submission": submission,
            "quiz_result": quiz_result,
            "now": now,
            "is_overdue": is_overdue
        }
    )


@router.post("/lesson/{lesson_id}/submit")
async def student_submit_homework(
    lesson_id: int,
    text_answer: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student)
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="Урок не найден")

    file_url = None
    file_name = None
    file_size = None
    gdrive_file_id = None

    if file and file.filename:
        upload_res = await storage_service.upload_file(file)
        file_url = upload_res["file_url"]
        file_name = upload_res["file_name"]
        file_size = upload_res["file_size"]
        gdrive_file_id = upload_res.get("file_id")

    # Check if student already submitted
    submission = db.query(Submission).filter(
        Submission.lesson_id == lesson_id,
        Submission.student_id == current_user.id
    ).first()

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if submission:
        # Update existing submission
        if text_answer is not None and text_answer.strip():
            submission.text_answer = text_answer.strip()
        if file_url:
            submission.file_url = file_url
            submission.file_name = file_name
            submission.file_size = file_size
            submission.gdrive_file_id = gdrive_file_id
        submission.status = "submitted"
        submission.submitted_at = now
    else:
        # Create new submission
        submission = Submission(
            lesson_id=lesson_id,
            student_id=current_user.id,
            status="submitted",
            text_answer=text_answer.strip() if text_answer else None,
            file_url=file_url,
            file_name=file_name,
            file_size=file_size,
            gdrive_file_id=gdrive_file_id,
            submitted_at=now
        )
        db.add(submission)

    db.commit()

    return RedirectResponse(url=f"/student/lesson/{lesson_id}?success=1", status_code=status.HTTP_303_SEE_OTHER)


# --- Quiz Taking ---

@router.get("/quiz/{quiz_id}", response_class=HTMLResponse)
def student_quiz_take(
    quiz_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student)
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Тест не найден")

    # Parse options JSON for questions
    questions_data = []
    for q in quiz.questions:
        try:
            opts = json.loads(q.options_json) if q.options_json else []
        except Exception:
            opts = []
        questions_data.append({
            "id": q.id,
            "text": q.question_text,
            "type": q.question_type,
            "options": opts,
            "points": q.points
        })

    prev_result = db.query(QuizResult).filter(
        QuizResult.quiz_id == quiz_id,
        QuizResult.student_id == current_user.id
    ).order_by(QuizResult.submitted_at.desc()).first()

    return templates.TemplateResponse(
        request=request,
        name="student/quiz_take.html",
        context={
            "current_user": current_user,
            "quiz": quiz,
            "questions": questions_data,
            "prev_result": prev_result
        }
    )


@router.post("/quiz/{quiz_id}/submit")
async def student_quiz_submit(
    quiz_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_student)
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Тест не найден")

    form_data = await request.form()
    
    total_score = 0
    max_score = 0
    student_answers = {}

    for q in quiz.questions:
        max_score += q.points
        field_name = f"question_{q.id}"
        
        try:
            correct_opts = json.loads(q.correct_answers_json) if q.correct_answers_json else []
        except Exception:
            correct_opts = []

        if q.question_type == "multiple":
            given = form_data.getlist(field_name)
            student_answers[str(q.id)] = given
            if set(map(str, given)) == set(map(str, correct_opts)):
                total_score += q.points
        elif q.question_type == "single":
            given = form_data.get(field_name, "").strip()
            student_answers[str(q.id)] = given
            if correct_opts and str(given).lower() == str(correct_opts[0]).lower():
                total_score += q.points
        else:  # 'text'
            given = form_data.get(field_name, "").strip()
            student_answers[str(q.id)] = given
            if correct_opts and str(given).strip().lower() == str(correct_opts[0]).strip().lower():
                total_score += q.points

    percentage = int((total_score / max_score * 100) if max_score > 0 else 100)
    passed = percentage >= quiz.passing_score

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    result = QuizResult(
        quiz_id=quiz_id,
        student_id=current_user.id,
        score=total_score,
        max_score=max_score,
        percentage=percentage,
        passed=passed,
        answers_json=json.dumps(student_answers, ensure_ascii=False),
        submitted_at=now
    )
    db.add(result)
    db.commit()

    return RedirectResponse(
        url=f"/student/lesson/{quiz.lesson_id}?quiz_done=1&score={percentage}",
        status_code=status.HTTP_303_SEE_OTHER
    )
