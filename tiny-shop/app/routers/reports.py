from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_user
from .. import models, security

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

REPORT_THRESHOLD = 5  # 이 횟수 이상 신고되면 자동 차단/휴면 처리


@router.get("/report", response_class=HTMLResponse)
def report_form(request: Request, target_type: str, target_id: int, user: models.User = Depends(require_user)):
    if target_type not in ("user", "product"):
        raise HTTPException(status_code=400, detail="잘못된 신고 대상입니다.")
    response = templates.TemplateResponse(
        "report.html",
        {"request": request, "user": user, "target_type": target_type, "target_id": target_id, "error": None},
    )
    csrf = request.cookies.get("csrf_token")
    if not csrf:
        csrf = security.generate_csrf_token()
        response.set_cookie("csrf_token", csrf, httponly=False, samesite="lax")
    return response


@router.post("/report")
def submit_report(
    request: Request,
    target_type: str = Form(...),
    target_id: int = Form(...),
    reason: str = Form(...),
    csrf_token: str = Form(...),
    user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    cookie_token = request.cookies.get("csrf_token")
    if not security.verify_csrf(cookie_token, csrf_token):
        return HTMLResponse("CSRF 검증 실패", status_code=400)

    reason = reason.strip()
    if target_type not in ("user", "product") or not (1 <= len(reason) <= 300):
        raise HTTPException(status_code=400, detail="입력값이 올바르지 않습니다.")

    # 자기 자신 신고 방지 (본인 상품/계정)
    if target_type == "user" and target_id == user.id:
        raise HTTPException(status_code=400, detail="본인을 신고할 수 없습니다.")

    report = models.Report(
        reporter_id=user.id,
        target_type=models.TargetType(target_type),
        target_id=target_id,
        reason=reason,
    )
    db.add(report)
    try:
        # DB의 UniqueConstraint(reporter_id, target_type, target_id)가
        # 동일 유저의 반복 신고(신고 남용)를 막아준다.
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="이미 신고한 대상입니다.")

    if target_type == "product":
        product = db.query(models.Product).filter(models.Product.id == target_id).first()
        if product:
            product.report_count += 1
            if product.report_count >= REPORT_THRESHOLD:
                product.is_blocked = True
            db.commit()
    else:
        target_user = db.query(models.User).filter(models.User.id == target_id).first()
        if target_user:
            target_user.report_count += 1
            if target_user.report_count >= REPORT_THRESHOLD:
                target_user.is_suspended = True
            db.commit()

    return RedirectResponse("/", status_code=303)
