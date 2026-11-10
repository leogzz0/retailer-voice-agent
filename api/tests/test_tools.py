"""Contract tests for the read-side agent tools, against seeded demo data.

Demo store 10234 (Abarrotes Doña Lupe): folio 4721 en ruta hoy, 4715 entrega fallida ayer,
4730 en preparación, 4700-4702 entregados con la "canasta de siempre".
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

Verified = Callable[[str], dict[str, str]]


def test_liveness_and_readiness(anon_client: TestClient) -> None:
    assert anon_client.get("/health/live").json() == {"status": "ok"}
    assert anon_client.get("/health/ready").json() == {"status": "ok"}


# --- customer lookup (identification only) -----------------------------------------------


def test_lookup_returns_only_identification(client: TestClient) -> None:
    r = client.get("/v1/customers/lookup", params={"customer_code": "10234"})
    assert r.status_code == 200
    assert r.json() == {
        "customer_code": "10234",
        "store_name": "Abarrotes Doña Lupe",
        "city": "Monterrey",
    }  # no owner name, phone, or credit before verification


def test_lookup_by_code_with_spaces_from_stt(client: TestClient) -> None:
    # Speech-to-text often renders "diez mil doscientos treinta y cuatro" as "10 234".
    r = client.get("/v1/customers/lookup", params={"customer_code": "10 234"})
    assert r.status_code == 200


def test_lookup_by_phone_any_format(client: TestClient) -> None:
    r = client.get("/v1/customers/lookup", params={"phone": "(81) 5550-1234"})
    assert r.json()["customer_code"] == "10234"


def test_lookup_not_found_is_relayable(client: TestClient) -> None:
    r = client.get("/v1/customers/lookup", params={"customer_code": "99999"})
    assert r.status_code == 404
    assert r.json()["code"] == "customer_not_found"
    assert "dígito por dígito" in r.json()["message_es"]


def test_lookup_requires_an_identifier(client: TestClient) -> None:
    r = client.get("/v1/customers/lookup")
    assert r.status_code == 422
    assert r.json()["code"] == "missing_identifier"


# --- orders ------------------------------------------------------------------------------


def test_recent_orders_newest_first(client: TestClient, verified: Verified) -> None:
    r = client.get("/v1/customers/10234/orders", params={"limit": 3}, headers=verified("10234"))
    folios = [o["folio"] for o in r.json()["orders"]]
    assert folios == [4730, 4721, 4715]


def test_filter_orders_by_status(client: TestClient, verified: Verified) -> None:
    r = client.get(
        "/v1/customers/10234/orders",
        params={"status": "delivered", "limit": 10},
        headers=verified("10234"),
    )
    assert {o["status"] for o in r.json()["orders"]} == {"delivered"}


def test_order_in_transit_today(client: TestClient, verified: Verified) -> None:
    r = client.get("/v1/customers/10234/orders/4721", headers=verified("10234"))
    assert r.status_code == 200
    body = r.json()
    assert body["status_es"] == "en ruta de entrega"
    assert body["promised_date_es"] == "hoy, lunes 9 de noviembre"
    assert body["delivery"]["status"] == "in_transit"
    assert body["delivery"]["window_es"].startswith("hoy, lunes 9 de noviembre, entre ")
    assert " " not in body["delivery"]["driver_first_name"]
    assert len(body["items"]) == 5


def test_failed_delivery_exposes_reason(client: TestClient, verified: Verified) -> None:
    body = client.get("/v1/customers/10234/orders/4715", headers=verified("10234")).json()
    assert body["delivery"]["status"] == "failed"
    assert body["delivery"]["failure_reason"]


def test_cannot_read_another_stores_order(client: TestClient, verified: Verified) -> None:
    # 4721 belongs to 10234; a caller verified as 20518 must not see it.
    r = client.get("/v1/customers/20518/orders/4721", headers=verified("20518"))
    assert r.status_code == 404
    assert r.json()["code"] == "order_not_found"


def test_unknown_customer_in_path(client: TestClient) -> None:
    r = client.get("/v1/customers/99999/orders")
    assert r.status_code == 404


# --- usual order -------------------------------------------------------------------------


def test_usual_order(client: TestClient, verified: Verified) -> None:
    body = client.get("/v1/customers/10234/usual-order", headers=verified("10234")).json()
    skus = {i["sku"] for i in body["items"]}
    assert skus == {"BOT-001", "BEB-001", "ABA-001", "GAL-001", "ABA-002"}
    assert "DUL-001" not in skus  # bought once: not "usual"
    beb = next(i for i in body["items"] if i["sku"] == "BEB-001")
    assert beb["typical_quantity"] == 5


# --- product search ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spoken", "expected_sku"),
    [
        ("papitas", "BOT-001"),
        ("galletas maria", "GAL-001"),  # no accent
        ("sopa de vasito", "ABA-001"),  # nickname, not catalog name
        ("frijoles refritos", "ABA-002"),
        ("cafe soluble", "ABA-010"),
        ("jalapenos", "ABA-008"),  # STT dropped the ñ
    ],
)
def test_product_search_tolerates_how_people_talk(
    client: TestClient, spoken: str, expected_sku: str
) -> None:
    matches = client.get("/v1/products/search", params={"q": spoken}).json()["matches"]
    assert matches, f"no match for {spoken!r}"
    assert matches[0]["sku"] == expected_sku


def test_product_search_no_garbage_matches(client: TestClient) -> None:
    r = client.get("/v1/products/search", params={"q": "tornillos"})
    assert r.json()["matches"] == []


def test_product_search_flags_ambiguity(client: TestClient) -> None:
    # "refresco" fits both cola and toronja equally: the agent must ask which one.
    body = client.get("/v1/products/search", params={"q": "refresco"}).json()
    assert {m["sku"] for m in body["matches"][:2]} == {"BEB-001", "BEB-002"}
    assert body["ambiguous"] is True


def test_product_search_clear_winner_not_ambiguous(client: TestClient) -> None:
    body = client.get("/v1/products/search", params={"q": "sopa de vasito"}).json()
    assert body["ambiguous"] is False
