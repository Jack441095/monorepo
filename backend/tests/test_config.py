from app.config import Settings, _validate_production_config, _validate_staging_config


def _staging_settings(**overrides):
    values = {
        "environment": "staging",
        "paddle_api_key": "sandbox-api-key",
        "paddle_webhook_secret": "sandbox-webhook-secret",
        "paddle_api_base_url": "https://sandbox-api.paddle.com",
        "paddle_product_id": "pro_submit_sandbox",
        "paddle_intro_price_id": "pri_submit_intro_sandbox",
        "paddle_regular_price_id": "pri_submit_regular_sandbox",
        "paddle_active_price_id": "pri_submit_regular_sandbox",
        "nite_dsp_public_url": "https://staging.nite.example",
        "nite_dsp_api_url": "https://api-staging.nite.example",
    }
    values.update(overrides)
    return Settings(**values)


def test_staging_configuration_accepts_sandbox_checkout_values():
    _validate_staging_config(_staging_settings())


def test_staging_configuration_rejects_live_paddle_endpoint():
    settings = _staging_settings(paddle_api_base_url="https://api.paddle.com")

    try:
        _validate_staging_config(settings)
    except RuntimeError as exc:
        assert "sandbox-api.paddle.com" in str(exc)
    else:
        raise AssertionError("live Paddle endpoint was accepted for staging")


def test_staging_configuration_rejects_missing_catalog_or_https_values():
    settings = _staging_settings(paddle_product_id="", nite_dsp_public_url="http://localhost:3000")

    try:
        _validate_staging_config(settings)
    except RuntimeError as exc:
        message = str(exc)
        assert "paddle_product_id" in message
        assert "nite_dsp_public_url" in message
    else:
        raise AssertionError("incomplete staging configuration was accepted")


def test_staging_configuration_accepts_complete_s3_storage():
    _validate_staging_config(
        _staging_settings(
            storage_backend="s3",
            storage_bucket="nitedsp-releases",
            storage_endpoint="https://account.r2.cloudflarestorage.com",
            storage_access_key_id="access-key",
            storage_secret_access_key="secret-key",
        )
    )


def test_staging_configuration_rejects_incomplete_s3_storage():
    settings = _staging_settings(storage_backend="s3", storage_bucket="nitedsp-releases")

    try:
        _validate_staging_config(settings)
    except RuntimeError as exc:
        message = str(exc)
        assert "storage_endpoint" in message
        assert "storage_access_key_id" in message
        assert "storage_secret_access_key" in message
    else:
        raise AssertionError("incomplete S3 storage configuration was accepted")


def test_production_configuration_rejects_local_release_storage():
    settings = Settings(
        environment="production",
        nite_dsp_public_url="https://www.nite.example",
        nite_dsp_api_url="https://api.nite.example",
        nite_dsp_support_email="support@nite.example",
        session_secret="production-session-secret",
        admin_api_key="production-admin-key",
        licensing_private_key_base64="production-key",
        database_url="postgresql+psycopg2://db.example/nitedsp",
        email_from_address="noreply@nite.example",
        storage_backend="local",
    )

    try:
        _validate_production_config(settings)
    except RuntimeError as exc:
        assert "storage_backend must be 's3'" in str(exc)
    else:
        raise AssertionError("production accepted non-durable local release storage")


def test_production_configuration_accepts_complete_s3_release_storage():
    settings = Settings(
        environment="production",
        nite_dsp_public_url="https://www.nite.example",
        nite_dsp_api_url="https://api.nite.example",
        nite_dsp_support_email="support@nite.example",
        session_secret="production-session-secret",
        admin_api_key="production-admin-key",
        licensing_private_key_base64="production-key",
        database_url="postgresql+psycopg2://db.example/nitedsp",
        email_from_address="noreply@nite.example",
        storage_backend="s3",
        storage_bucket="nitedsp-releases",
        storage_endpoint="https://account.r2.cloudflarestorage.com",
        storage_access_key_id="access-key",
        storage_secret_access_key="secret-key",
    )

    _validate_production_config(settings)
