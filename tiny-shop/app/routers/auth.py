import re

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user_optional, require_user
from .. import models, security

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,20}$")


def ensure_csrf_cookie(request: Request, response: Response) -> str:
    token = request.cookies.get("csrf_token")
    if not token:
        token = security.generate_csrf_token()
        # HttpOnly는 걸지 않는다 - 폼에 값을 넣어줘야 하므로. (더블 서브밋 쿠키 패턴)
        response.set_cookie("csrf_token", token, httponly=False, samesite="lax")
    return token


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    response = templates.TemplateResponse("register.html", {"request": request, "error": None})
    ensure_csrf_cookie(request, response)
    return response


@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    cookie_token = request.cookies.get("csrf_token")
    if not security.verify_csrf(cookie_token, csrf_token):
        return HTMLResponse("CSRF 검증 실패", status_code=400)

    # 입력값 검증: 형식/길이 제한 (서버측에서 반드시 재검증. 프론트만 믿지 않는다)
    if not USERNAME_RE.match(username):
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "아이디는 영문/숫자/_ 3~20자여야 합니다."},
        )
    if len(password) < 8:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "비밀번호는 8자 이상이어야 합니다."}
        )

    existing = db.query(models.User).filter(models.User.username == username).first()
    if existing:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "이미 존재하는 아이디입니다."}
        )

    user = models.User(username=username, password_hash=security.hash_password(password))
    db.add(user)
    db.commit()

    return RedirectResponse("/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    response = templates.TemplateResponse("login.html", {"request": request, "error": None})
    ensure_csrf_cookie(request, response)
    return response


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    cookie_token = request.cookies.get("csrf_token")
    if not security.verify_csrf(cookie_token, csrf_token):
        return HTMLResponse("CSRF 검증 실패", status_code=400)

    generic_error = {"request": request, "error": "아이디 또는 비밀번호가 올바르지 않습니다."}

    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        # 존재하지 않는 계정이어도 동일한 에러 메시지 (계정 존재 여부 추측 방지)
        return templates.TemplateResponse("login.html", generic_error)

    if security.is_locked(user):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "로그인 시도 초과로 잠시 잠겼습니다. 잠시 후 다시 시도하세요."},
        )

    if not security.verify_password(password, user.password_hash):
        security.register_failed_attempt(user, db)
        return templates.TemplateResponse("login.html", generic_error)

    security.reset_failed_attempts(user, db)

    if user.is_suspended:
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "휴면 처리된 계정입니다."}
        )

    token = security.create_session_token(user.id)
    response = RedirectResponse("/", status_code=303)
    # HttpOnly: JS로 세션 쿠키 탈취(XSS 통한) 방지 / Secure: HTTPS 환경에서만 전송되게 (배포시 True로)
    response.set_cookie(
        "session", token, httponly=True, samesite="lax", max_age=security.SESSION_MAX_AGE_SECONDS
    )
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("session")
    return response


@router.get("/mypage", response_class=HTMLResponse)
def mypage(request: Request, user: models.User = Depends(require_user)):
    response = templates.TemplateResponse("mypage.html", {"request": request, "user": user, "error": None})
    ensure_csrf_cookie(request, response)
    return response


@router.post("/mypage")
def update_mypage(
    request: Request,
    bio: str = Form(""),
    new_password: str = Form(""),
    csrf_token: str = Form(...),
    user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    cookie_token = request.cookies.get("csrf_token")
    if not security.verify_csrf(cookie_token, csrf_token):
        return HTMLResponse("CSRF 검증 실패", status_code=400)

    # bio는 Jinja2 autoescape로 출력 시 이스케이프되므로 저장은 그대로 하되 길이만 제한
    user.bio = bio[:500]
    if new_password:
        if len(new_password) < 8:
            return templates.TemplateResponse(
                "mypage.html",
                {"request": request, "user": user, "error": "비밀번호는 8자 이상이어야 합니다."},
            )
        user.password_hash = security.hash_password(new_password)
    db.commit()

    return RedirectResponse("/mypage", status_code=303)
