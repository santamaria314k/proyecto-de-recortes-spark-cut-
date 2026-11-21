import pytest
from django.contrib.auth import get_user_model


@pytest.fixture(autouse=True)
def _mock_scorer(settings):
    """Las pruebas no dependen de los artefactos reales del modelo."""
    settings.MOCK_SCORER = True


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(
        username="kevin",
        email="kevin@example.com",
        password="testpass123",
    )


@pytest.fixture
def other_user(db):
    return get_user_model().objects.create_user(
        username="andres",
        email="andres@example.com",
        password="testpass123",
    )


@pytest.fixture
def logged_client(client, user):
    client.force_login(user)
    return client
