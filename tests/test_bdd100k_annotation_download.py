from __future__ import annotations

import sys
import unittest
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from download_bdd100k_enriched_annotations import filter_url, keyframe_ids


class BDD100KAnnotationDownloadTests(unittest.TestCase):
    def test_keyframe_ids_exclude_temporal_neighbors(self) -> None:
        records = [
            {"file_name": "b.jpg"},
            {"file_name": "a_1.jpg"},
            {"file_name": "a.jpg"},
            {"file_name": "a_3.jpg"},
            {"file_name": "a.jpg"},
        ]
        self.assertEqual(["a", "b"], keyframe_ids(records))

    def test_filter_url_uses_quoted_image_ids(self) -> None:
        url = filter_url(["abc-def", "ghi-jkl"])
        parameters = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(
            ['"image_id" IN (\'abc-def\',\'ghi-jkl\')'],
            parameters["where"],
        )
        self.assertEqual(["100"], parameters["length"])


if __name__ == "__main__":
    unittest.main()
