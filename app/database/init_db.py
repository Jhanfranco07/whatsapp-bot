from sqlalchemy import text

from app.database.connection import Base, engine
from app.database import models  # noqa: F401


def init_db():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS "
                "stop_bot BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_contacts_stop_bot "
                "ON contacts (stop_bot)"
            )
        )
