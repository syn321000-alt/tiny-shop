from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin
from .. import models, security

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# 주의: 이 라우터의 모든 엔드포인트는 Depends(require_admin)을 걸어서
# "관리자 메뉴가 화면에 안 보이니 안전하다"가 아니라 서버 단에서 실제로 막아야 함.
# (URL을 직접 입력하면 프론트 숨김은 아무 의미가 없음)


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    products = db.query(models.Product).all()
    reports = db.query(models.Report).order_by(models.Report.created_at.desc()).all()

    response = templates.TemplateResponse(
        "admin.html",
        {"request": request, "user": admin, "users": users, "products": products, "reports": reports},
    )
    csrf = request.cookies.get("csrf_token")
    if not csrf:
        csrf = security.generate_csrf_token()
        response.set_cookie("csrf_token", csrf, httponly=False, samesite="lax")
    return response


@router.post("/admin/user/{user_id}/toggle-suspend")
def toggle_suspend(
    user_id: int,
    request: Request,
    csrf_token: str = Form(...),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not security.verify_csrf(request.cookies.get("csrf_token"), csrf_token):
        return HTMLResponse("CSRF 검증 실패", status_code=400)

    target = db.query(models.User).filter(models.User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=404)
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="본인 계정은 변경할 수 없습니다.")
    target.is_suspended = not target.is_suspended
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/product/{product_id}/toggle-block")
def toggle_block(
    product_id: int,
    request: Request,
    csrf_token: str = Form(...),
    admin: models.User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not security.verify_csrf(request.cookies.get("csrf_token"), csrf_token):
        return HTMLResponse("CSRF 검증 실패", status_code=400)

    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404)
    product.is_blocked = not product.is_blocked
    db.commit()
    return RedirectResponse("/admin", status_code=303)
