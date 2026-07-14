import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .database import Base, engine, SessionLocal
from . import models, security
from .routers import auth, products, reports, transfer, admin, chat

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tiny-shop")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Tiny Second-hand Shopping Platform")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(auth.router)
app.include_router(products.router)
app.include_router(reports.router)
app.include_router(transfer.router)
app.include_router(admin.router)
app.include_router(chat.router)


@app.on_event("startup")
def seed_admin():
    """최초 실행 시 admin/admin1234 계정을 하나 만들어둔다. (실습용. 배포시 반드시 비번 변경!)"""
    db = SessionLocal()
    try:
        exists = db.query(models.User).filter(models.User.username == "admin").first()
        if not exists:
            admin_user = models.User(
                username="admin",
                password_hash=security.hash_password("admin1234!"),
                is_admin=True,
            )
            db.add(admin_user)
            db.commit()
            logger.info("Seeded admin account (username=admin, password=admin1234!) - 실습 후 반드시 변경하세요.")
    finally:
        db.close()


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # 클라이언트에는 최소한의 정보만 반환. DB 내용/스택트레이스는 절대 노출하지 않는다.
    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # 예상 못한 에러는 서버 로그에만 상세히 남기고, 사용자에게는 일반 메시지만 보여준다.
    logger.exception("Unhandled error on %s", request.url)
    return PlainTextResponse("서버 오류가 발생했습니다.", status_code=500)
