"""The owner signing step must sign the download the feed actually advertises."""
import base64
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption


class AppcastTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        (self.root / 'tools').mkdir()
        (self.root / 'web').mkdir()
        self.script = self.root / 'tools/update_appcast.sh'
        shutil.copy2(Path(__file__).parent / 'update_appcast.sh', self.script)
        private = Ed25519PrivateKey.generate()
        self.key = self.root / 'test-key.base64'
        self.key.write_bytes(base64.b64encode(private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())))
        public = base64.b64encode(private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
        # An ephemeral signer tests the workflow without the owner's offline key.
        self.script.write_text(self.script.read_text().replace('XrMZt5AZ8Am24TGn67teEw/RfzC0i0owOYVmpTM0s2g=', public))
        (self.root / 'VERSION').write_text('1.0.0\n')
        self.zip = self.root / 'Submit-1.0.0-macOS.zip'
        self.zip.write_bytes(b'test archive')
        self.feed = self.root / 'web/appcast.xml'
        self.feed.write_text('<rss xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle"><channel><item><enclosure sparkle:version="1.0.0" url="https://releases.nitedsp.co.uk/submit/Submit-1.0.0-macOS.zip" length="0" sparkle:edSignature="" /></item></channel></rss>')

    def run_signer(self, version='1.0.0', archive=None):
        return subprocess.run([str(self.script), '--version', version, '--zip', str(archive or self.zip), '--key', str(self.key)], capture_output=True, text=True)

    def assert_rejected_without_edit(self, **kwargs):
        before = self.feed.read_bytes()
        self.assertNotEqual(self.run_signer(**kwargs).returncode, 0)
        self.assertEqual(self.feed.read_bytes(), before)

    def test_signed_feed_matches_version_url_and_archive_length(self):
        self.assertEqual(self.run_signer().returncode, 0)
        self.assertIn('length="12"', self.feed.read_text())
        self.assertNotIn('edSignature=""', self.feed.read_text())

    def test_feed_url_must_match_the_signed_download(self):
        # Previously a valid signature could be stamped onto a different URL.
        self.feed.write_text(self.feed.read_text().replace('/submit/Submit-', '/other/Submit-'))
        self.assert_rejected_without_edit()

    def test_version_must_match_the_product_version(self):
        (self.root / 'VERSION').write_text('1.0.1\n')
        self.assert_rejected_without_edit()

    def test_archive_filename_must_match_the_version(self):
        other = self.root / 'Submit-0.2.0-macOS.zip'
        other.write_bytes(self.zip.read_bytes())
        self.assert_rejected_without_edit(archive=other)

    def test_wrong_signing_key_does_not_modify_the_feed(self):
        self.script.write_text(self.script.read_text().replace('public_key_b64="', 'unused_key="', 1).replace('usage() {', 'public_key_b64="XrMZt5AZ8Am24TGn67teEw/RfzC0i0owOYVmpTM0s2g="\nusage() {', 1))
        self.assert_rejected_without_edit()


if __name__ == '__main__':
    unittest.main()
