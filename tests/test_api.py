from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_calculator_endpoint() -> None:
    response = client.post(
        "/api/v1/calculations/screen",
        json={"width_m": 2, "height_m": 1, "pitch_mm": 2.5},
    )
    assert response.status_code == 200
    assert response.json()["cabinet_count"] == 8


def test_quote_escapes_customer_data() -> None:
    response = client.post(
        "/api/v1/documents/quote/preview",
        json={
            "number": "КП-1",
            "customer": "<script>alert(1)</script>",
            "project": "Экран",
            "total": 100,
        },
    )
    assert response.status_code == 200
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text
