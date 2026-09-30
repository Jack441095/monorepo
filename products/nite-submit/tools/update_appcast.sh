#!/usr/bin/env bash
# Sign and stamp web/appcast.xml for a release.
#
# The enclosure carries two things UpdateEngine checks: the byte length of the
# download, and an Ed25519 signature over "<version>\n<download URL>". The
# release private key stays offline with the owner, so this is a manual step
# after packaging, not something the build can do for you. It refuses to write a
# signature the shipped public key does not verify, which is the whole point of
# having a signature gate in the updater.
set -euo pipefail

product_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
appcast="$product_dir/web/appcast.xml"
# UpdateEngine.updatePublicKeyBase64. A signature that does not verify against
# this is not a signature, so it is checked here as well as in the app.
public_key_b64="XrMZt5AZ8Am24TGn67teEw/RfzC0i0owOYVmpTM0s2g="

usage() {
    echo "Usage: $0 --version <version> --zip <zip> --key <release-update-private-key.base64>"
}

version=""
zip_path=""
key_path=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) [[ $# -ge 2 ]] || usage; version="$2"; shift 2 ;;
        --zip) [[ $# -ge 2 ]] || usage; zip_path="$2"; shift 2 ;;
        --key) [[ $# -ge 2 ]] || usage; key_path="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
    esac
done

[[ -n "$version" && -n "$zip_path" && -n "$key_path" ]] || { usage >&2; exit 2; }
[[ -f "$zip_path" ]] || { echo "Missing release zip: $zip_path" >&2; exit 1; }
[[ -f "$key_path" ]] || { echo "Missing release private key: $key_path" >&2; exit 1; }
[[ -f "$appcast" ]] || { echo "Missing appcast: $appcast" >&2; exit 1; }

download_url="https://releases.nitedsp.co.uk/submit/Submit-${version}-macOS.zip"
length="$(stat -f%z "$zip_path")"

python3 - "$key_path" "$version" "$download_url" "$length" "$public_key_b64" "$appcast" <<'PY'
import base64, re, sys
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)
from cryptography.exceptions import InvalidSignature

key_path, version, download_url, length, public_b64, appcast_path = sys.argv[1:7]
raw = base64.b64decode(open(key_path).read().strip())
private = Ed25519PrivateKey.from_private_bytes(raw)
# The payload is version, newline, download URL — byte for byte what
# UpdateEngine.signaturePayload builds, so the app verifies what we sign here.
payload = (version + "\n" + download_url).encode("utf-8")
signature = base64.b64encode(private.sign(payload)).decode()

try:
    Ed25519PublicKey.from_public_bytes(base64.b64decode(public_b64)).verify(
        base64.b64decode(signature), payload)
except InvalidSignature:
    sys.exit("That key does not match UpdateEngine.updatePublicKeyBase64; refusing to write the feed.")

feed = open(appcast_path, encoding="utf-8").read()
pattern = re.compile(
    r'(<enclosure\b[^>]*?sparkle:version="%s"[^>]*?)(/>)' % re.escape(version),
    re.DOTALL)
match = pattern.search(feed)
if not match:
    sys.exit(f"No <enclosure> for version {version} in {appcast_path}")

tag = match.group(1)
tag = re.sub(r'\s+length="[^"]*"', "", tag)
tag = re.sub(r'\s+sparkle:edSignature="[^"]*"', "", tag)
tag = tag.rstrip()
tag = f'{tag}\n                 length="{length}"\n                 sparkle:edSignature="{signature}"'
open(appcast_path, "w", encoding="utf-8").write(feed[:match.start()] + tag + match.group(2) + feed[match.end():])
print(f"appcast {version}: length={length} signature={signature}")
PY
