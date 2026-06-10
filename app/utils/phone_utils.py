import re


def normalize_phone(value: str, country_code: str = "51") -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 10:
        digits = country_code + digits[1:]
    elif len(digits) == 9:
        digits = country_code + digits
    if not 8 <= len(digits) <= 15:
        raise ValueError("Número telefónico inválido")
    return digits
