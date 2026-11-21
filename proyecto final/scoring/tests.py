import json

import pytest
from django.urls import reverse

from scoring.scorer import score_segments


def test_mock_scores_stay_within_contract():
    texts = [f"texto de prueba {index}" for index in range(500)]
    scores = score_segments(texts)

    assert len(scores) == len(texts)
    assert all(10 <= score <= 100 for score in scores)


@pytest.mark.django_db
def test_model_info(client):
    response = client.get(reverse("model_info"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_model_try_valid(client):
    response = client.post(
        reverse("model_try"),
        data=json.dumps({"text": "Esto es una prueba de puntaje."}),
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.json()
    assert 10 <= payload["score"] <= 100
    assert set(payload["dims"]) == {"hook", "emotion", "surprise", "conflict", "story"}


@pytest.mark.django_db
def test_model_try_rejects_long_text(client):
    response = client.post(
        reverse("model_try"),
        data=json.dumps({"text": "x" * 501}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "text_too_long"
