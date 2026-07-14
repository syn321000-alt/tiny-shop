from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_user
from .. import models, security

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/transfer", response_class=HTMLResponse)
def transfer_form(request: Request, user: models.User = Depends(require_user)):
    response = templates.TemplateResponse(
        "transfer.html", {"request": request, "user": user, "error": None}
    )
    csrf = request.cookies.get("csrf_token")
    if not csrf:
        csrf = security.generate_csrf_token()
        response.set_cookie("csrf_token", csrf, httponly=False, samesite="lax")
    return response


@router.post("/transfer")
def submit_transfer(
    request: Request,
    receiver_username: str = Form(...),
    amount: str = Form(...),
    csrf_token: str = Form(...),
    user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    cookie_token = request.cookies.get("csrf_token")
    if not security.verify_csrf(cookie_token, csrf_token):
        return HTMLResponse("CSRF 검증 실패", status_code=400)

    err_ctx = {"request": request, "user": user}

    try:
        amount_val = Decimal(amount)
    except InvalidOperation:
        return templates.TemplateResponse("transfer.html", {**err_ctx, "error": "금액이 올바르지 않습니다."})

    # 절대 프론트에서 넘어온 금액/잔액을 그대로 신뢰하면 안 됨. 서버에서 재검증.
    if amount_val <= 0:
        return templates.TemplateResponse("transfer.html", {**err_ctx, "error": "0보다 큰 금액을 입력하세요."})

    receiver = db.query(models.User).filter(models.User.username == receiver_username).first()
    if receiver is None:
        return templates.TemplateResponse("transfer.html", {**err_ctx, "error": "받는 사람을 찾을 수 없습니다."})

    if receiver.id == user.id:
        return templates.TemplateResponse("transfer.html", {**err_ctx, "error": "본인에게는 송금할 수 없습니다."})

    # 최신 잔액을 다시 조회해서 확인 (요청 사이 잔액이 바뀌었을 가능성 고려)
    db.refresh(user)
    if user.balance < amount_val:
        return templates.TemplateResponse("transfer.html", {**err_ctx, "error": "잔액이 부족합니다."})

    # NOTE: 실제 서비스라면 동시성 문제(같은 잔액으로 여러 송금이 동시에 들어오는 경우)를
    # 막기 위해 SELECT ... FOR UPDATE 같은 행 잠금이 필요합니다.
    # SQLite는 이를 완전히 지원하지 않으므로, PostgreSQL 등으로 옮길 경우 꼭 추가하세요.
    user.balance -= amount_val
    receiver.balance += amount_val
    tx = models.Transaction(sender_id=user.id, receiver_id=receiver.id, amount=amount_val)
    db.add(tx)
    db.commit()

    return RedirectResponse("/mypage", status_code=303)
