from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


settings = get_settings()
if not settings.database_url.startswith("postgresql"):
    raise RuntimeError("DATABASE_URL debe apuntar a PostgreSQL; SQLite no está permitido")

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_timeout=settings.database_pool_timeout,
    pool_recycle=settings.database_pool_recycle,
    connect_args={"connect_timeout": settings.database_connect_timeout},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
