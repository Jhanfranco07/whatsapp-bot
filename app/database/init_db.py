from sqlalchemy import text

from app.database.connection import Base, engine
from app.database import models  # noqa: F401


def init_db():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    Base.metadata.create_all(bind=engine)
