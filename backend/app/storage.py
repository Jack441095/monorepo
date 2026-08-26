"""Release-artifact storage adapters.

Local filesystem storage remains the default for development and tests.  A
private S3-compatible bucket (including Cloudflare R2) can be selected with
``STORAGE_BACKEND=s3`` once the owner provisions it.  Customer documents are
never accepted by these adapters; they are only for versioned release
artifacts registered through the authenticated admin route.
"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Protocol

from .config import settings
from .security import DOWNLOAD_URL_MAX_AGE_SECONDS


class StorageError(RuntimeError):
    """A storage dependency is unavailable or returned an unexpected error."""


class StorageNotFound(StorageError):
    """The requested release artifact does not exist."""


class ReleaseStorage(Protocol):
    def readiness(self) -> None: ...

    def exists(self, storage_key: str) -> bool: ...

    def sha256(self, storage_key: str) -> str: ...

    def put_file(self, source: Path, storage_key: str, checksum_sha256: str) -> None: ...

    def local_path(self, storage_key: str) -> Path | None: ...

    def presigned_get_url(self, storage_key: str, expires_in: int, filename: str) -> str | None: ...


def local_release_path(storage_root: str, storage_key: str) -> Path:
    """Resolve a release key beneath ``storage_root`` or raise ``ValueError``.

    ``storage_key`` is data from the database, so this check is required both
    when an admin registers a release and when a signed download is fetched.
    Resolving symlinks also prevents a link inside the release directory from
    pointing outside it.
    """
    root = Path(storage_root).resolve()
    candidate = (root / storage_key).resolve()
    if candidate == root or root not in candidate.parents:
        raise ValueError("storage_key must remain inside configured release storage")
    return candidate


def object_storage_key(storage_key: str) -> str:
    """Validate a portable object key for S3-compatible storage."""
    key = storage_key.replace("\\", "/")
    parts = key.split("/")
    if not key or key.startswith("/") or "\x00" in key or ".." in parts:
        raise ValueError("storage_key must be a relative object key")
    return key


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_download_filename(filename: str) -> str:
    """Keep a response filename to one harmless path component."""
    safe = Path(filename).name.replace('"', "_").replace("\r", "_").replace("\n", "_")
    return safe or "download"


class LocalDirStorage:
    """Release storage backed by the configured local directory."""

    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _path(self, storage_key: str) -> Path:
        return local_release_path(str(self.root), storage_key)

    def readiness(self) -> None:
        """Confirm the configured local release directory is usable.

        Local storage is deliberately allowed only for development and
        isolated staging proofs. The probe verifies that the process can
        create the directory and write to it, without leaving a marker behind
        or treating local storage as durable.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.NamedTemporaryFile(
                prefix=".nitedsp-readiness-", dir=self.root, delete=True
            ) as probe:
                probe.write(b"ok")
                probe.flush()
        except Exception as exc:  # noqa: BLE001 - filesystem errors vary by OS
            raise StorageError("local release storage is not writable") from exc

    def exists(self, storage_key: str) -> bool:
        return self._path(storage_key).is_file()

    def sha256(self, storage_key: str) -> str:
        path = self._path(storage_key)
        if not path.is_file():
            raise StorageNotFound("release artifact missing from local storage")
        return _sha256_path(path)

    def put_file(self, source: Path, storage_key: str, checksum_sha256: str) -> None:
        if not source.is_file():
            raise StorageNotFound("source release artifact does not exist")
        destination = self._path(storage_key)
        if destination.exists():
            if self.sha256(storage_key) != checksum_sha256.lower():
                raise StorageError("immutable release key already contains different bytes")
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        actual = _sha256_path(destination)
        if actual != checksum_sha256.lower():
            destination.unlink(missing_ok=True)
            raise StorageError("uploaded local artifact checksum does not match")

    def local_path(self, storage_key: str) -> Path:
        return self._path(storage_key)

    def presigned_get_url(self, storage_key: str, expires_in: int, filename: str) -> None:
        return None


class S3CompatibleStorage:
    """Private S3-compatible object storage, including Cloudflare R2.

    The boto3 import is lazy so local development remains usable without cloud
    credentials or a cloud SDK.  Any S3/R2 configuration error becomes a
    generic ``StorageError`` and never exposes credentials or provider detail
    through an API response.
    """

    def __init__(self, bucket: str, endpoint: str, access_key_id: str, secret_access_key: str, region: str):
        if not bucket or not endpoint or not access_key_id or not secret_access_key:
            raise StorageError("S3 storage requires bucket, endpoint, access key, and secret key")
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - deployment dependency guard
            raise StorageError("S3 storage dependency is not installed") from exc

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region or "auto",
        )

    def _key(self, storage_key: str) -> str:
        try:
            return object_storage_key(storage_key)
        except ValueError as exc:
            raise StorageError(str(exc)) from exc

    def readiness(self) -> None:
        """Confirm that the configured bucket is reachable with its credentials."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception as exc:  # noqa: BLE001 - provider SDK exception types vary
            raise StorageError("S3 release storage is not reachable") from exc

    @staticmethod
    def _provider_error(exc: Exception, not_found_message: str) -> StorageError:
        response = getattr(exc, "response", {})
        code = str(response.get("Error", {}).get("Code", ""))
        if code in {"404", "NoSuchKey", "NotFound"}:
            return StorageNotFound(not_found_message)
        return StorageError("S3 storage operation failed")

    def exists(self, storage_key: str) -> bool:
        key = self._key(storage_key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:  # noqa: BLE001 - provider SDK exception types vary
            error = self._provider_error(exc, "release artifact missing from object storage")
            if isinstance(error, StorageNotFound):
                return False
            raise error from exc

    def sha256(self, storage_key: str) -> str:
        key = self._key(storage_key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            body = response["Body"]
            digest = hashlib.sha256()
            try:
                for chunk in iter(lambda: body.read(1024 * 1024), b""):
                    digest.update(chunk)
            finally:
                body.close()
            return digest.hexdigest()
        except Exception as exc:  # noqa: BLE001 - provider SDK exception types vary
            error = self._provider_error(exc, "release artifact missing from object storage")
            raise error from exc

    def put_file(self, source: Path, storage_key: str, checksum_sha256: str) -> None:
        if not source.is_file():
            raise StorageNotFound("source release artifact does not exist")
        key = self._key(storage_key)
        if self.exists(key):
            if self.sha256(key) != checksum_sha256.lower():
                raise StorageError("immutable release key already contains different bytes")
            return
        try:
            self.client.upload_file(
                str(source),
                self.bucket,
                key,
                ExtraArgs={"Metadata": {"sha256": checksum_sha256.lower()}},
            )
        except Exception as exc:  # noqa: BLE001 - provider SDK exception types vary
            raise StorageError("S3 upload failed") from exc

    def local_path(self, storage_key: str) -> None:
        return None

    def presigned_get_url(self, storage_key: str, expires_in: int, filename: str) -> str:
        key = self._key(storage_key)
        bounded_expiry = max(1, min(int(expires_in), DOWNLOAD_URL_MAX_AGE_SECONDS))
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    "ResponseContentType": "application/octet-stream",
                    "ResponseContentDisposition": f'attachment; filename="{_safe_download_filename(filename)}"',
                },
                ExpiresIn=bounded_expiry,
            )
        except Exception as exc:  # noqa: BLE001 - provider SDK exception types vary
            raise StorageError("could not create signed object URL") from exc


def get_storage() -> ReleaseStorage:
    """Build the configured adapter for the current process."""
    backend = settings.storage_backend.strip().lower()
    if backend == "local":
        return LocalDirStorage(settings.mock_storage_dir)
    if backend == "s3":
        return S3CompatibleStorage(
            bucket=settings.storage_bucket,
            endpoint=settings.storage_endpoint,
            access_key_id=settings.storage_access_key_id,
            secret_access_key=settings.storage_secret_access_key,
            region=settings.storage_region,
        )
    raise StorageError(f"unsupported storage backend: {backend}")
