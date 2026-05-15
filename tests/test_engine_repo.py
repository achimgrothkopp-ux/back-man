import pytest

from backman.engine.repo import BackendKind, local_repo, sftp_repo


def test_local_repo_resolves_path(tmp_path):
    repo = local_repo(tmp_path / "data")
    assert repo.kind is BackendKind.LOCAL
    assert repo.url == str(tmp_path / "data")
    assert repo.label == str(tmp_path / "data")


def test_local_repo_expanduser(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    repo = local_repo("~/backups")
    assert repo.url == str(tmp_path / "backups")


def test_sftp_repo_url_format():
    repo = sftp_repo(user="achim", host="nas.local", path="/srv/restic")
    assert repo.kind is BackendKind.SFTP
    assert repo.url == "sftp:achim@nas.local:/srv/restic"
    assert "nas.local" in repo.label


def test_sftp_repo_rejects_relative_path():
    with pytest.raises(ValueError):
        sftp_repo(user="u", host="h", path="relative/path")


def test_sftp_repo_rejects_missing_parts():
    with pytest.raises(ValueError):
        sftp_repo(user="", host="h", path="/p")
