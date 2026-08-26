#!/usr/bin/env bash
# Rehearse the application migration and PostgreSQL dump/restore mechanics.
#
# This script is deliberately disposable-only. It creates its own local
# cluster and databases, ignores DATABASE_URL, never accepts a source or target
# URL, and removes the temporary cluster on exit. It is not evidence of Railway
# backup/PITR availability.
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

psql -h "$pg_socket" -p "$pg_port" -d "$pg_db" -v ON_ERROR_STOP=1 >/dev/null <<'SQL'
INSERT INTO products (id, name, status, public, purchasable, description, current_version, platforms, created_at, paddle_product_id)
VALUES ('nite-submit', 'Submit', 'active', true, false, 'Rehearsal product', '0.2.0', ARRAY['macos'], now(), NULL);
INSERT INTO users (id, email, password_hash, email_verified_at, created_at, updated_at)
VALUES ('00000000-0000-0000-0000-000000000001', 'rehearsal@example.invalid', NULL, now(), now(), now());
INSERT INTO releases (id, product_id, version, platform, architecture, channel, checksum_sha256, signature, storage_key, release_notes, published_at)
VALUES ('00000000-0000-0000-0000-000000000002', 'nite-submit', '0.2.0', 'macos', 'arm64', 'private-beta', repeat('a', 64), NULL, 'releases/nite-submit/0.2.0/macos/arm64/Submit.zip', 'Rehearsal release', now());
INSERT INTO entitlements (id, user_id, product_id, purchase_id, license_type, max_activations, status, expires_at, created_at, revoked_at, revoked_reason, license_key)
VALUES ('00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001', 'nite-submit', NULL, 'beta', 3, 'active', now() + interval '90 days', now(), NULL, NULL, 'REHEARSAL-LICENSE-KEY');
SQL

pg_dump -h "$pg_socket" -p "$pg_port" -Fc -d "$pg_db" -f "$pg_tmp/rehearsal.dump"
pg_restore -h "$pg_socket" -p "$pg_port" -d "$pg_restore_db" --exit-on-error --no-owner "$pg_tmp/rehearsal.dump"

restored_head=$(psql -h "$pg_socket" -p "$pg_port" -d "$pg_restore_db" -Atc "select version_num from alembic_version")
restored_counts=$(psql -h "$pg_socket" -p "$pg_port" -d "$pg_restore_db" -Atc "select (select count(*) from products)||','||(select count(*) from users)||','||(select count(*) from releases)||','||(select count(*) from entitlements)")

printf 'restore_migration_head=%s\n' "$restored_head"
printf 'restored_row_counts(products,users,releases,entitlements)=%s\n' "$restored_counts"

[[ "$restored_head" == "6c3e9e1d4b7a" ]]
[[ "$restored_counts" == "1,1,1,1" ]]
echo "local_postgres_restore_rehearsal=pass"
