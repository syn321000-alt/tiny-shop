from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 개발용으로 SQLite 사용. 실서비스라면 PostgreSQL 등으로 교체 권장.
SQLALCHEMY_DATABASE_URL = "sqlite:///./tiny_shop.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """요청마다 세션 생성 후 반드시 닫아준다 (커넥션 누수 방지)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
