from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.models import User
from app.auth import verify_password, create_access_token, get_current_user_optional
from app.config import COOKIE_NAME, BASE_DIR

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


@router.get("/", response_class=HTMLResponse)
def index_redirect(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if user.role in ["tutor", "admin"]:
        return RedirectResponse(url="/tutor/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/student/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if user:
        if user.role in ["tutor", "admin"]:
            return RedirectResponse(url="/tutor/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/student/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None}
    )


@router.post("/login", response_class=HTMLResponse)
def login_post(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    clean_username = username.strip().lower()
    user = db.query(User).filter(User.username == clean_username).first()

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Неверный логин или пароль", "username": username},
            status_code=status.HTTP_400_BAD_REQUEST
        )

    # Issue auth token
    token = create_access_token(user.id, user.username, user.role)

    # Choose destination
    redirect_url = "/tutor/dashboard" if user.role in ["tutor", "admin"] else "/student/dashboard"
    redirect_res = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    redirect_res.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=7 * 86400,
        samesite="lax"
    )
    return redirect_res


@router.get("/logout")
def logout(response: Response):
    res = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    res.delete_cookie(COOKIE_NAME)
    return res
