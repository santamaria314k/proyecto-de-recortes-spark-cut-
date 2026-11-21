import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from videos.models import Video


@pytest.mark.django_db
def test_signup_creates_user_and_redirects_to_dashboard(client):
    response = client.post(
        reverse("account_signup"),
        {
            "email": "nueva@example.com",
            "password1": "ClaveSegura2026!",
            "password2": "ClaveSegura2026!",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard/"
    user = get_user_model().objects.get(email="nueva@example.com")
    assert client.session["_auth_user_id"] == str(user.pk)


@pytest.mark.django_db
def test_signup_rejects_duplicate_email(client, user):
    response = client.post(
        reverse("account_signup"),
        {
            "email": user.email,
            "password1": "OtraClave2026!",
            "password2": "OtraClave2026!",
        },
    )

    assert response.status_code == 200
    assert get_user_model().objects.filter(email=user.email).count() == 1


@pytest.mark.django_db
def test_signup_rejects_weak_password(client):
    response = client.post(
        reverse("account_signup"),
        {"email": "debil@example.com", "password1": "123", "password2": "123"},
    )

    assert response.status_code == 200
    assert not get_user_model().objects.filter(email="debil@example.com").exists()


@pytest.mark.django_db
def test_login_with_email(logged_client):
    logged_client.logout()
    response = logged_client.post(
        reverse("account_login"),
        {"login": "kevin@example.com", "password": "testpass123"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard/"


@pytest.mark.django_db
def test_google_button_hidden_without_credentials(client):
    response = client.get(reverse("account_login"))

    assert response.status_code == 200
    assert b"Continuar con Google" not in response.content


@pytest.mark.django_db
def test_logout_requires_post(client, user):
    client.force_login(user)

    # El GET solo muestra la confirmación; la sesión se cierra con POST.
    assert client.get(reverse("account_logout")).status_code == 200
    assert client.post(reverse("account_logout")).status_code == 302
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_json_endpoint_returns_403_without_session(client, user):
    video = Video.objects.create(user=user, title="Demo", source_type=Video.SourceType.UPLOAD)

    response = client.get(reverse("video_status", args=[video.pk]))

    assert response.status_code == 403
    assert response.json()["code"] == "not_authenticated"
