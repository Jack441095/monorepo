#!/usr/bin/env bash
# Rehearse the application migration and PostgreSQL dump/restore mechanics.
#
# This script is deliberately disposable-only. It creates its own local
# cluster and databases, ignores DATABASE_URL, never accepts a source or target
# URL, and removes the temporary cluster on exit. Provider backup/PITR
# availability needs separate evidence from the deployed database service.
set -Eeuo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
backend_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
pg_port="${NITE_DSP_REHEARSAL_PORT:-55439}"

for required_command in initdb pg_ctl createdb pg_dump pg_restore psql; do
  command -v "$required_command" >/dev/null || {
    echo "$required_command is required" >&2
    exit 2
  }
done

if ! [[ "$pg_port" =~ ^[0-9]+$ ]] || (( pg_port < 1024 || pg_port > 65535 )); then
  echo "NITE_DSP_REHEARSAL_PORT must be a TCP port between 1024 and 65535" >&2
  exit 2
fi

pg_tmp=$(mktemp -d "${TMPDIR:-/tmp}/nite-dsp-db-rehearsal.XXXXXX")
pg_data="$pg_tmp/data"
pg_socket="$pg_tmp/socket"
pg_log="$pg_tmp/postgres.log"
pg_db=nitedsp_rehearsal
pg_restore_db=nitedsp_rehearsal_restored

cleanup() {
  pg_ctl -D "$pg_data" -m fast stop >/dev/null 2>&1 || true
  rm -R "$pg_tmp"
}
trap cleanup EXIT

mkdir -p "$pg_socket"
initdb -D "$pg_data" --no-locale --encoding=UTF8 --auth=trust >/dev/null
pg_ctl -D "$pg_data" \
  -o "-p $pg_port -k $pg_socket -h 127.0.0.1" \
  -l "$pg_log" start >/dev/null

createdb -h "$pg_socket" -p "$pg_port" "$pg_db"
createdb -h "$pg_socket" -p "$pg_port" "$pg_restore_db"

export DATABASE_URL="postgresql+psycopg2:///$pg_db?host=$pg_socket&port=$pg_port"
cd "$backend_root"
PYTHONPATH="$backend_root" alembic -c "$backend_root/alembic.ini" upgrade head >/dev/null
expected_head=$(python3 -c 'from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config("alembic.ini")).get_current_head())')

psql -h "$pg_socket" -p "$pg_port" -d "$pg_db" -v ON_ERROR_STOP=1 >/dev/null <<'SQL'
INSERT INTO products (id, name, status, public, purchasable, description, current_version, platforms, created_at)
VALUES ('nite-submit', 'Submit', 'active', true, false, 'Rehearsal product', '0.2.0', ARRAY['macos'], now());
INSERT INTO users (id, email, password_hash, email_verified_at, created_at, updated_at)
VALUES ('00000000-0000-0000-0000-000000000001', 'rehearsal@example.invalid', NULL, now(), now(), now());
INSERT INTO releases (id, product_id, version, platform, architecture, channel, checksum_sha256, signature, storage_key, release_notes, published_at)
VALUES ('00000000-0000-0000-0000-000000000002', 'nite-submit', '0.2.0', 'macos', 'arm64', 'private-beta', repeat('a', 64), NULL, 'releases/nite-submit/0.2.0/macos/arm64/Submit.zip', 'Rehearsal release', now());
-- A paid licence with pending email exercises recovery after a provider outage.
-- All provider IDs, payloads, and device values here are synthetic fixtures.
INSERT INTO purchases (id, user_id, product_id, provider, provider_order_id, provider_payment_id, amount_cents, currency, status, purchased_at, confirmation_email_sent_at)
VALUES ('00000000-0000-0000-0000-000000000004', '00000000-0000-0000-0000-000000000001', 'nite-submit', 'stripe', 'cs_restore_fixture', 'pi_restore_fixture', 200, 'GBP', 'completed', now(), NULL);
INSERT INTO entitlements (id, user_id, product_id, purchase_id, license_type, max_activations, status, expires_at, created_at, revoked_at, revoked_reason, license_key)
VALUES ('00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001', 'nite-submit', '00000000-0000-0000-0000-000000000004', 'perpetual', 3, 'active', NULL, now(), NULL, NULL, 'REHEARSAL-LICENSE-KEY');
INSERT INTO activations (id, entitlement_id, machine_id, machine_label, activated_at, last_seen_at)
VALUES ('00000000-0000-0000-0000-000000000005', '00000000-0000-0000-0000-000000000003', 'restore-fixture-device', 'Restore fixture', now(), now());
INSERT INTO webhook_events (id, provider, event_type, provider_event_id, payload_json, received_at, processed_at, processing_error)
VALUES ('00000000-0000-0000-0000-000000000006', 'stripe', 'checkout.session.completed', 'evt_restore_fixture', '{"rehearsal":true}', now(), NULL, 'Synthetic provider outage');
SQL

pg_dump -h "$pg_socket" -p "$pg_port" -Fc -d "$pg_db" -f "$pg_tmp/rehearsal.dump"
pg_restore -h "$pg_socket" -p "$pg_port" -d "$pg_restore_db" --exit-on-error --no-owner "$pg_tmp/rehearsal.dump"

restored_head=$(psql -h "$pg_socket" -p "$pg_port" -d "$pg_restore_db" -Atc "select version_num from alembic_version")
restored_counts=$(psql -h "$pg_socket" -p "$pg_port" -d "$pg_restore_db" -Atc "select (select count(*) from products)||','||(select count(*) from users)||','||(select count(*) from releases)||','||(select count(*) from entitlements)||','||(select count(*) from purchases)||','||(select count(*) from activations)||','||(select count(*) from webhook_events)")
# Row counts alone miss detached licences and lost retry state after a restore.
restored_commerce=$(psql -h "$pg_socket" -p "$pg_port" -d "$pg_restore_db" -Atc "select count(*) from purchases p join entitlements e on e.purchase_id=p.id and e.user_id=p.user_id join activations a on a.entitlement_id=e.id where p.confirmation_email_sent_at is null and p.provider_payment_id='pi_restore_fixture' and e.license_key='REHEARSAL-LICENSE-KEY' and e.status='active' and e.expires_at is null")
restored_retry=$(psql -h "$pg_socket" -p "$pg_port" -d "$pg_restore_db" -Atc "select count(*) from webhook_events where provider_event_id='evt_restore_fixture' and processed_at is null and processing_error='Synthetic provider outage' and payload_json->>'rehearsal'='true'")

printf 'restore_migration_head=%s\n' "$restored_head"
printf 'restored_row_counts(products,users,releases,entitlements,purchases,activations,webhooks)=%s\n' "$restored_counts"
printf 'restored_paid_licence_with_pending_email=%s\n' "$restored_commerce"
printf 'restored_failed_webhook=%s\n' "$restored_retry"

[[ "$restored_head" == "$expected_head" ]]
[[ "$restored_counts" == "1,1,1,1,1,1,1" ]]
[[ "$restored_commerce" == "1" ]]
[[ "$restored_retry" == "1" ]]
echo "local_postgres_restore_rehearsal=pass"
