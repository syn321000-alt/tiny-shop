from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user_optional, require_user
from .. import models, security

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def ensure_csrf_cookie(request: Request, response: Response) -> str:
    token = request.cookies.get("csrf_token")
    if not token:
        token = security.generate_csrf_token()
        response.set_cookie("csrf_token", token, httponly=False, samesite="lax")
    return token


@router.get("/", response_class=HTMLResponse)
def main_page(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user_optional),
):
    query = db.query(models.Product).filter(models.Product.is_blocked == False)  # noqa: E712
    if q:
        # LIKE 검색 시에도 파라미터 바인딩(ORM)으로 처리되어 SQL 인젝션 안전
        query = query.filter(models.Product.title.ilike(f"%{q}%"))
    products = query.order_by(models.Product.created_at.desc()).all()

    response = templates.TemplateResponse(
        "main.html", {"request": request, "user": user, "products": products, "q": q}
    )
    return response


@router.get("/product/new", response_class=HTMLResponse)
def new_product_form(request: Request, user: models.User = Depends(require_user)):
    response = templates.TemplateResponse("product_new.html", {"request": request, "user": user, "error": None})
    ensure_csrf_cookie(request, response)
    return response


@router.post("/product/new")
def create_product(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    price: str = Form(...),
    csrf_token: str = Form(...),
    user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    cookie_token = request.cookies.get("csrf_token")
    if not security.verify_csrf(cookie_token, csrf_token):
        return HTMLResponse("CSRF 검증 실패", status_code=400)

    title = title.strip()
    if not (1 <= len(title) <= 100):
        return templates.TemplateResponse(
            "product_new.html",
            {"request": request, "user": user, "error": "상품명은 1~100자여야 합니다."},
        )

    try:
        price_val = Decimal(price)
        if price_val < 0 or price_val > Decimal("100000000"):
            raise InvalidOperation
    except InvalidOperation:
        return templates.TemplateResponse(
            "product_new.html",
            {"request": request, "user": user, "error": "가격은 0 이상의 올바른 숫자여야 합니다."},
        )

    product = models.Product(
        title=title,
        description=description[:2000],
        price=price_val,
        seller_id=user.id,
    )
    db.add(product)
    db.commit()

    return RedirectResponse(f"/product/{product.id}", status_code=303)


@router.get("/product/{product_id}", response_class=HTMLResponse)
def product_detail(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user_optional),
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")
    # 차단된 상품은 관리자 또는 판매자 본인만 볼 수 있게
    if product.is_blocked and not (user and (user.is_admin or user.id == product.seller_id)):
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    is_owner = bool(user and user.id == product.seller_id)
    response = templates.TemplateResponse(
        "product_detail.html",
        {"request": request, "user": user, "product": product, "is_owner": is_owner},
    )
    ensure_csrf_cookie(request, response)
    return response


@router.post("/product/{product_id}/delete")
def delete_product(
    product_id: int,
    request: Request,
    csrf_token: str = Form(...),
    user: models.User = Depends(require_user),
    db: Session = Depends(get_db),
):
    cookie_token = request.cookies.get("csrf_token")
    if not security.verify_csrf(cookie_token, csrf_token):
        return HTMLResponse("CSRF 검증 실패", status_code=400)

    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다.")

    # 핵심 인가 체크: "로그인 했는지"뿐 아니라 "본인 소유인지"까지 확인.
    # 이 체크가 없으면 남의 상품 id만 알면 누구나 삭제 가능해짐 (IDOR 취약점).
    if product.seller_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="본인 상품만 삭제할 수 있습니다.")

    db.delete(product)
    db.commit()
    return RedirectResponse("/", status_code=303)
