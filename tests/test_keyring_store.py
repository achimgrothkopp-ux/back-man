import keyring
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

import pytest

from backman import keyring_store


class InMemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self._store.get((service, username))

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def delete_password(self, service, username):
        try:
            del self._store[(service, username)]
        except KeyError:
            raise PasswordDeleteError("not found")


@pytest.fixture
def in_memory_keyring():
    previous = keyring.get_keyring()
    backend = InMemoryKeyring()
    keyring.set_keyring(backend)
    try:
        yield backend
    finally:
        keyring.set_keyring(previous)


def test_set_and_get_password(in_memory_keyring):
    keyring_store.set_password("/repo/a", "geheim")
    assert keyring_store.get_password("/repo/a") == "geheim"


def test_get_password_returns_none_when_missing(in_memory_keyring):
    assert keyring_store.get_password("/nicht/da") is None


def test_set_password_rejects_empty():
    with pytest.raises(ValueError):
        keyring_store.set_password("/repo", "")


def test_delete_password_returns_false_when_missing(in_memory_keyring):
    assert keyring_store.delete_password("/nicht/da") is False


def test_delete_password_removes_entry(in_memory_keyring):
    keyring_store.set_password("/repo/b", "x")
    assert keyring_store.delete_password("/repo/b") is True
    assert keyring_store.get_password("/repo/b") is None


def test_service_name_constant():
    assert keyring_store.SERVICE_NAME == "back-man"
