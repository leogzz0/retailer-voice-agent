"""Pure unit tests: no database needed."""

from datetime import UTC, date, datetime

import pytest

from nopalia_api.services import normalize_mx_phone
from nopalia_api.speech import date_es, digits_es, first_name, window_es


def test_date_es_plain() -> None:
    assert date_es(date(2026, 11, 12)) == "jueves 12 de noviembre"


@pytest.mark.parametrize(
    ("d", "expected_prefix"),
    [(date(2026, 11, 9), "hoy"), (date(2026, 11, 10), "mañana"), (date(2026, 11, 8), "ayer")],
)
def test_date_es_relative(d: date, expected_prefix: str) -> None:
    assert date_es(d, today=date(2026, 11, 9)).startswith(f"{expected_prefix}, ")


def test_window_es_converts_to_business_timezone() -> None:
    # 15:00-19:00 UTC == 9:00-13:00 in Monterrey (UTC-6, no DST since 2022).
    start = datetime(2026, 11, 12, 15, tzinfo=UTC)
    end = datetime(2026, 11, 12, 19, tzinfo=UTC)
    assert (
        window_es(start, end, "America/Monterrey") == "jueves 12 de noviembre, entre 9:00 y 13:00"
    )


@pytest.mark.parametrize(
    "raw",
    ["81 5550 1234", "(81) 5550-1234", "+52 81 5550 1234", "+52 1 81 5550 1234", "528155501234"],
)
def test_normalize_mx_phone(raw: str) -> None:
    assert normalize_mx_phone(raw) == "+528155501234"


def test_normalize_mx_phone_rejects_short() -> None:
    assert normalize_mx_phone("5550 1234") is None


def test_first_name_only() -> None:
    assert first_name("Guadalupe Treviño Salinas") == "Guadalupe"


@pytest.mark.parametrize(
    ("n", "spoken"), [(2, "dos"), (10, "uno, cero"), (4721, "cuatro, siete, dos, uno")]
)
def test_digits_es_reads_short_form(n: int, spoken: str) -> None:
    assert digits_es(n) == spoken
