from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .database import get_db
from .security import read_session_token
from . import models


def get_current_user_optional(request: Request, db: Session = Depends(get_db)):
    """로그인 안 되어 있으면 None 반환 (로그인 페이지 등에서 사용)."""
    token = request.cookies.get("session")
    if not token:
        return None
    user_id = read_session_token(token)
    if user_id is None:
        return None
    user = db.query(models.User).filter(models.User.id == user_id).first()
    return user


def require_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    """로그인 필수 라우트에서 사용. 미로그인/휴면계정이면 403."""
    user = get_current_user_optional(request, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다.")
    if user.is_suspended:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="휴면 처리된 계정입니다.")
    return user


def require_admin(user: models.User = Depends(require_user)) -> models.User:
    """관리자 전용 라우트. 프론트가 아니라 반드시 서버(여기)에서 체크해야 우회 불가능."""
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="관리자만 접근 가능합니다.")
    return user
