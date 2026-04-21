from typing import TYPE_CHECKING

import pytest

from django.contrib.auth import get_user_model
from django.test import Client


if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser as UserType
    from wagtail.models import Site

User = get_user_model()


@pytest.fixture(autouse=True)
def temporary_media_dir(settings, tmp_path: pytest.TempdirFactory):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def default_site() -> "Site":
    from wagtail.models import Site

    return Site.objects.get(is_default_site=True)


@pytest.fixture
def superuser() -> "UserType":
    user_data = {"username": "test@email.com", "password": "password"}
    return User.objects.create_superuser(**user_data)


@pytest.fixture
def client_superuser(client: "Client", superuser) -> "Client":
    client.force_login(superuser)
    return client
