from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.storage import LocalDirStorage, S3CompatibleStorage, object_storage_key


def test_local_storage_upload_is_checksum_bound_and_immutable(tmp_path: Path):
    source = tmp_path / "release.zip"
    source.write_bytes(b"release bytes")
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    storage = LocalDirStorage(str(tmp_path / "storage"))

    storage.put_file(source, "releases/0.1.0/release.zip", checksum)
    assert storage.exists("releases/0.1.0/release.zip")
    assert storage.sha256("releases/0.1.0/release.zip") == checksum

    # Repeating the same upload is idempotent; a different byte stream cannot
    # overwrite an immutable version-pinned key.
    storage.put_file(source, "releases/0.1.0/release.zip", checksum)
    with pytest.raises(RuntimeError, match="immutable release key"):
        storage.put_file(source, "releases/0.1.0/release.zip", "0" * 64)


def test_local_storage_readiness_creates_no_marker(tmp_path: Path):
    storage = LocalDirStorage(str(tmp_path / "storage"))

    storage.readiness()

    assert (tmp_path / "storage").is_dir()
    assert list((tmp_path / "storage").iterdir()) == []


def test_object_storage_key_rejects_absolute_and_parent_paths():
    assert object_storage_key("releases/0.1.0/release.zip") == "releases/0.1.0/release.zip"
    with pytest.raises(ValueError):
        object_storage_key("../outside.zip")
    with pytest.raises(ValueError):
        object_storage_key("/outside.zip")


def test_s3_presigned_url_is_bounded_to_download_token_ttl(monkeypatch):
    calls: dict = {}

    class FakeClient:
        def head_bucket(self, Bucket):
            calls["bucket"] = Bucket

        def generate_presigned_url(self, operation, Params, ExpiresIn):
            calls.update(operation=operation, params=Params, expires=ExpiresIn)
            return "https://objects.example/signed"

    fake_boto3 = SimpleNamespace(client=lambda *args, **kwargs: FakeClient())
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    storage = S3CompatibleStorage(
        bucket="releases",
        endpoint="https://objects.example",
        access_key_id="access",
        secret_access_key="secret",
        region="auto",
    )
    url = storage.presigned_get_url("releases/0.1.0/Submit.zip", expires_in=99999, filename="Submit.zip")

    assert url == "https://objects.example/signed"
    assert calls["operation"] == "get_object"
    assert calls["expires"] == 15 * 60
    storage.readiness()
    assert calls["bucket"] == "releases"
    assert calls["params"]["Bucket"] == "releases"
    assert calls["params"]["Key"] == "releases/0.1.0/Submit.zip"


def test_s3_storage_upload_and_checksum_are_immutable(monkeypatch, tmp_path: Path):
    objects: dict[str, bytes] = {}

    class MissingObject(Exception):
        response = {"Error": {"Code": "404"}}

    class FakeClient:
        def head_object(self, Bucket, Key):
            if Key not in objects:
                raise MissingObject()
            return {"ContentLength": len(objects[Key])}

        def upload_file(self, filename, Bucket, Key, ExtraArgs=None):
            objects[Key] = Path(filename).read_bytes()

        def get_object(self, Bucket, Key):
            if Key not in objects:
                raise MissingObject()
            return {"Body": io.BytesIO(objects[Key])}

    fake_boto3 = SimpleNamespace(client=lambda *args, **kwargs: FakeClient())
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    source = tmp_path / "Submit.zip"
    source.write_bytes(b"remote release bytes")
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    storage = S3CompatibleStorage(
        bucket="releases",
        endpoint="https://objects.example",
        access_key_id="access",
        secret_access_key="secret",
        region="auto",
    )

    storage.put_file(source, "releases/0.2.0/Submit.zip", checksum)
    assert storage.exists("releases/0.2.0/Submit.zip")
    assert storage.sha256("releases/0.2.0/Submit.zip") == checksum
    with pytest.raises(RuntimeError, match="immutable release key"):
        storage.put_file(source, "releases/0.2.0/Submit.zip", "0" * 64)
