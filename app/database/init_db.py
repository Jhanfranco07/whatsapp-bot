from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.database.connection import engine


def init_db():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    config = Config("alembic.ini")
    command.upgrade(config, "head")
