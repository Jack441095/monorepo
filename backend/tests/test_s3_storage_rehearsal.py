import json
from types import SimpleNamespace

from scripts import rehearse_s3_release_storage as rehearsal


def test_s3_rehearsal_defaults_to_dry_run_without_provider_access(capsys):
    assert rehearsal.main([]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "dry-run"
    assert result["writes_attempted"] is False
    assert result["customer_documents_accepted"] is False


def test_s3_rehearsal_requires_explicit_bucket_confirmation(monkeypatch, capsys):
    monkeypatch.setattr(
        rehearsal,
        "settings",
        SimpleNamespace(environment="staging", storage_backend="s3", storage_bucket="staging-releases"),
    )

    assert rehearsal.main(["--execute"]) == 2
    assert "no write attempted" in capsys.readouterr().err


def test_s3_rehearsal_round_trip_uses_synthetic_bytes_and_cleans_up(monkeypatch, capsys):
    objects: dict[str, bytes] = {}
    calls: list[tuple[str, str]] = []

    class FakeClient:
        def delete_object(self, Bucket, Key):
            calls.append((Bucket, Key))
            objects.pop(Key, None)

    class FakeStorage:
        bucket = "staging-releases"
        client = FakeClient()

        def put_file(self, source, key, checksum):
            objects[key] = source.read_bytes()

        def exists(self, key):
            return key in objects

        def sha256(self, key):
            import hashlib

            return hashlib.sha256(objects[key]).hexdigest()

        def delete_rehearsal_object(self, key):
            self.client.delete_object(Bucket=self.bucket, Key=key)

    monkeypatch.setattr(
        rehearsal,
        "settings",
        SimpleNamespace(environment="staging", storage_backend="s3", storage_bucket="staging-releases"),
    )
    monkeypatch.setattr(rehearsal, "get_storage", lambda: FakeStorage())
    monkeypatch.setattr(rehearsal, "S3CompatibleStorage", FakeStorage)

    assert rehearsal.main(["--execute", "--confirm-bucket", "staging-releases"]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "pass"
    assert result["cleaned_up"] is True
    assert result["customer_documents_accepted"] is False
    assert len(calls) == 1
    assert calls[0][0] == "staging-releases"
    assert calls[0][1].startswith("rehearsals/nite-submit/storage-round-trip/")
    assert objects == {}
