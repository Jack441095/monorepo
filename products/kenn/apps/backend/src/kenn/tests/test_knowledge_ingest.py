import unittest

from scripts.knowledge_ingest.crawler import _visible_text, canonical_url, concepts, quality_score, summarize
from scripts.knowledge_ingest.models import SourceSpec


class KnowledgeIngestTests(unittest.TestCase):
    def setUp(self):
        self.source = SourceSpec(
            source_id="test-source",
            name="Test source",
            publisher="Test publisher",
            tier=1,
            seed_urls=("https://example.test/",),
            allowed_prefixes=("https://example.test/",),
            license="test",
            terms_url=None,
        )

    def test_canonical_url_removes_fragment_and_trailing_slash(self):
        self.assertEqual(canonical_url("HTTPS://Example.Test/path/#section"), "https://example.test/path")

    def test_summary_is_bounded(self):
        value = summarize("This is a useful sentence about compression. " * 100)
        self.assertLessEqual(len(value), 650)

    def test_concepts_include_source_topic(self):
        self.assertIn("test-source", concepts("compression compression threshold release", ["test-source"]))

    def test_quality_score_is_bounded(self):
        value = quality_score("A title", "technical content " * 500, self.source)
        self.assertGreaterEqual(value, 0.0)
        self.assertLessEqual(value, 1.0)

    def test_relative_links_use_page_origin(self):
        _, _, links = _visible_text('<a href="chapter-1/">Chapter</a>', "https://example.test/manual/")
        self.assertEqual(links, ["https://example.test/manual/chapter-1/"])


if __name__ == "__main__":
    unittest.main()
