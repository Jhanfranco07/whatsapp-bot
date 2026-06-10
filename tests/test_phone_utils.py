import pytest

from app.utils.phone_utils import normalize_phone


def test_normalize_peruvian_phone():
    assert normalize_phone("+51 999 999 999") == "51999999999"
    assert normalize_phone("999999999") == "51999999999"


def test_invalid_phone():
    with pytest.raises(ValueError):
        normalize_phone("123")
