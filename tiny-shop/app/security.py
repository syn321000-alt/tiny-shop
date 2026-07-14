import datetime
import secrets

from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

# ── 비밀번호 해싱 ──────────────────────────────────────────────
# bcrypt: 느리게 설계된 해시 함수라 brute-force에 강함. 절대 md5/sha1 쓰지 말 것.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── 세션 쿠키 서명 ─────────────────────────────────────────────
# 실제 배포 시에는 이 SECRET_KEY를 환경변수로 분리해야 함 (코드에 하드코딩 금지).
# 여기서는 로컬 실습용으로만 하드코딩.
SECRET_KEY = "CHANGE_THIS_TO_A_RANDOM_SECRET_IN_PRODUCTION"
serializer = URLSafeTimedSerializer(SECRET_KEY)

SESSION_MAX_AGE_SECONDS = 60 * 60 * 2  # 2시간 후 세션 만료


def create_session_token(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})


def read_session_token(token: str):
    """만료되었거나 위조된 토큰이면 None 반환."""
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
        return data.get("user_id")
    except (BadSignature, SignatureExpired):
        return None


# ── CSRF 토큰 ─────────────────────────────────────────────────
def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_csrf(session_token: str | None, form_token: str | None) -> bool:
    if not session_token or not form_token:
        return False
    return secrets.compare_digest(session_token, form_token)


# ── 로그인 실패 잠금 ────────────────────────────────────────────
MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION_MINUTES = 5


def is_locked(user) -> bool:
    if user.locked_until is None:
        return False
    return datetime.datetime.utcnow() < user.locked_until


def register_failed_attempt(user, db):
    user.failed_login_count += 1
    if user.failed_login_count >= MAX_FAILED_ATTEMPTS:
        user.locked_until = datetime.datetime.utcnow() + datetime.timedelta(
            minutes=LOCK_DURATION_MINUTES
        )
        user.failed_login_count = 0
    db.commit()


def reset_failed_attempts(user, db):
    user.failed_login_count = 0
    user.locked_until = None
    db.commit()
