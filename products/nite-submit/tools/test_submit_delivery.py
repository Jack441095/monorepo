"""Exercise the final ZIP through an isolated backend, with captured email only.

Run from backend with PYTHONPATH=. and pytest; the existing fixtures always
use nitedsp_test PostgreSQL and temporary signers, never the hosted database.
"""
import base64
import hashlib
import os
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

from nacl.signing import VerifyKey

pytest_plugins = ('tests.conftest',)


def test_submit_purchase_delivers_the_final_version_once(client, db_session, monkeypatch, tmp_path):
    from app import auth, models, stripe_commerce, submit_licensing
    from app.config import settings
    from tests.test_commerce_catalog import _completed_payload, _post_webhook

    product = Path(__file__).resolve().parents[1]
    version = (product / 'VERSION').read_text().strip()
    archive = product / f'artifacts/Submit-{version}-macOS.zip'
    payload = archive.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(settings, 'environment', 'staging')
    monkeypatch.setattr(settings, 'storage_backend', 'local')
    monkeypatch.setattr(settings, 'mock_storage_dir', str(tmp_path))
    # Optional local client verification uses the owner's existing signer in
    # memory. Neither the signer nor the minted key enters test output.
    signer = os.environ.get('NITE_SUBMIT_LICENSE_SIGNER')
    if signer:
        monkeypatch.setattr(submit_licensing, 'SUBMIT_LICENSE_PUBLIC_KEY_BASE64',
                            'kxzasvgjtZIqSnwQ2Gfh9FlkHSt9oHb4slC1YFAas4g=')
        monkeypatch.setattr(settings, 'submit_license_private_key_base64', Path(signer).read_text().strip())
    mail = []
    monkeypatch.setattr(stripe_commerce, 'send_email', lambda **kwargs: mail.append(kwargs))
    monkeypatch.setattr(auth, 'send_email', lambda **kwargs: mail.append(kwargs))
    db_session.add(models.Product(id='nite-submit', name='NITE Submit', status='active',
                                  public=False, purchasable=True, platforms=['macos'], current_version=version))
    db_session.commit()
    uploaded = client.post('/admin/releases/upload', data={
        'product_id': 'nite-submit', 'version': version, 'platform': 'macos', 'architecture': 'arm64',
    }, files={'artifact': (archive.name, payload, 'application/zip')}, headers={'X-Admin-Key': 'test-admin-key'})
    assert uploaded.status_code == 200
    assert uploaded.json()['checksum_sha256'] == digest
    registered = client.put(f'/admin/releases/nite-submit/{version}/macos/arm64', json={
        'product_id': 'nite-submit', 'version': version, 'platform': 'macos', 'architecture': 'arm64',
        'channel': 'private-beta', 'checksum_sha256': digest, 'storage_key': uploaded.json()['storage_key'],
    }, headers={'X-Admin-Key': 'test-admin-key'})
    assert registered.status_code == 200
    event = _completed_payload('evt_submit_shipping', 'cs_submit_shipping', product_id='nite-submit',
                               price_id='price_submit_test_200gbp', email='submit-shipping@example.com')
    event['livemode'] = False
    event['data']['object']['amount_total'] = 200  # £2 in GBP minor units.
    assert _post_webhook(client, event).json()['status'] == 'processed'
    purchase = db_session.query(models.Purchase).one()
    assert (purchase.amount_cents, purchase.currency) == (200, 'GBP')
    entitlement = db_session.query(models.Entitlement).one()
    key = entitlement.license_key
    raw = base64.urlsafe_b64decode(key.removeprefix('NTSUB1-') + '=' * (-len(key.removeprefix('NTSUB1-')) % 4))
    VerifyKey(base64.b64decode(submit_licensing.SUBMIT_LICENSE_PUBLIC_KEY_BASE64)).verify(raw[:4], raw[4:])
    assert len(mail) == 1
    assert bool('Amount charged: GBP 2.00' in mail[0]['body']), 'Confirmation must quote the test GBP amount'
    assert bool(key in mail[0]['body']), 'Confirmation must contain the issued licence'
    assert _post_webhook(client, event).json()['status'] == 'already_processed'
    assert len(mail) == 1 and db_session.query(models.Entitlement).count() == 1
    assert client.post('/webhooks/stripe', json=event, headers={'Stripe-Signature': 'invalid'}).status_code == 400
    query = {'product_id': 'nite-submit', 'platform': 'macos', 'architecture': 'arm64', 'channel': 'private-beta'}
    assert client.get('/downloads/latest', params=query).status_code == 401
    assert client.post('/auth/request-link', json={'email': 'submit-shipping@example.com'}).status_code == 200
    token = parse_qs(urlsplit(re.search(r'https?://\S+token=\S+', mail[-1]['body']).group()).query)['token'][0]
    assert client.post('/auth/verify', json={'token': token}).status_code == 200
    assert client.post('/auth/verify', json={'token': token}).status_code != 200
    latest = client.get('/downloads/latest', params=query)
    assert latest.status_code == 200
    assert latest.json()['version'] == version and latest.json()['checksum_sha256'] == digest
    url = urlsplit(latest.json()['download_url'])
    downloaded = client.get(url.path + '?' + url.query)
    assert downloaded.status_code == 200
    assert hashlib.sha256(downloaded.content).hexdigest() == digest
    key_output = os.environ.get('NITE_SUBMIT_TEST_LICENSE_OUT')
    if key_output:
        # Only the disposable GUI home receives the activation key.
        target = Path(key_output)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.write_text(key)
        target.chmod(0o600)
