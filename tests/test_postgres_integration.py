import os

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.connection import Base
from app.database.models import Contact, Message
from app.database.repositories import ContactRepository, MessageRepository
from app.schemas.contact_schema import ContactCreate


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Define TEST_DATABASE_URL con una base PostgreSQL exclusiva para integración",
)


@pytest.fixture
def db():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
        session.rollback()
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def test_create_contact_and_prevent_duplicate(db):
    repo = ContactRepository(db)
    first = repo.create(ContactCreate(phone_number="999999999", full_name="Ana"))
    same = repo.get_by_phone("+51 999 999 999")
    assert first.id == same.id
    assert len(list(db.scalars(select(Contact)))) == 1


def test_save_inbound_and_outbound(db):
    contact = ContactRepository(db).create(ContactCreate(phone_number="988888888"))
    messages = MessageRepository(db)
    messages.create(contact, "inbound", "hola")
    messages.create(contact, "outbound", "¡Hola!")
    db.flush()
    rows = list(db.scalars(select(Message).order_by(Message.created_at)))
    assert [row.direction for row in rows] == ["inbound", "outbound"]


def test_campaign_candidates_exclude_opt_out(db):
    repo = ContactRepository(db)
    allowed = repo.create(ContactCreate(phone_number="977777777"))
    blocked = repo.create(ContactCreate(phone_number="966666666"))
    blocked.opt_out = True
    db.flush()
    assert repo.campaign_candidates() == [allowed]
