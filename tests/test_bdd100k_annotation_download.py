from __future__ import annotations

import json
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from download_bdd100k_enriched_annotations import (
    checkpoint_complete,
    filter_url,
    keyframe_ids,
    partition_response_rows,
    write_checkpoint,
)


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
            [
                '"image_id" = \'abc-def\' OR '
                '"image_id" = \'ghi-jkl\''
            ],
            parameters["where"],
        )
        self.assertNotIn(" IN ", parameters["where"][0])
        self.assertEqual(["train"], parameters["split"])
        self.assertEqual(["100"], parameters["length"])

    def test_partition_keeps_only_original_train_rows(self) -> None:
        def row(image_id: str, split: str) -> dict:
            return {
                "image_id": image_id,
                "split": split,
                "width": 1280,
                "height": 720,
                "ann_categories": [],
                "ann_bboxes": [],
                "ann_occluded": [],
                "ann_truncated": [],
                "ann_traffic_light_colors": [],
                "image_bytes": {"bytes": "must-not-be-retained"},
                "embedding": [1.0],
            }

        result = partition_response_rows(
            ["train-id", "val-id", "unknown-id", "missing-id"],
            [
                row("train-id", "TRAIN"),
                row("val-id", "val"),
                row("unknown-id", "test"),
            ],
        )
        self.assertEqual(
            ["train-id"],
            [item["image_id"] for item in result["retained_rows"]],
        )
        self.assertNotIn("image_bytes", result["retained_rows"][0])
        self.assertNotIn("embedding", result["retained_rows"][0])
        self.assertEqual(
            ["val-id"], result["excluded_original_val_ids"]
        )
        self.assertEqual(
            ["unknown-id"], result["excluded_unknown_split_ids"]
        )
        self.assertEqual(["missing-id"], result["api_no_row_ids"])

    def test_completion_tracks_queries_not_retained_rows(self) -> None:
        requested = ["train-id", "val-id", "missing-id"]
        payload = {
            "complete": True,
            "completed_query_ids": requested,
            "rows": [{"image_id": "train-id", "split": "train"}],
        }
        self.assertTrue(checkpoint_complete(payload, requested))
        payload["completed_query_ids"] = requested[:-1]
        self.assertFalse(checkpoint_complete(payload, requested))

    def test_checkpoint_resume_partitions_are_disjoint_and_complete(
        self,
    ) -> None:
        requested = ["train-id", "val-id", "missing-id"]
        train_row = {
            "image_id": "train-id",
            "split": "train",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            write_checkpoint(
                path,
                requested,
                {"train-id": train_row},
                {"train-id", "val-id"},
                {"val-id"},
                set(),
                set(),
                completed_batches=1,
                resolved_revision="a" * 40,
            )
            partial = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(checkpoint_complete(partial, requested))
            self.assertEqual(1, partial["retained_original_train_rows"])
            self.assertEqual(1, partial["excluded_original_val_count"])
            self.assertEqual(0, partial["api_no_row_count"])

            write_checkpoint(
                path,
                requested,
                {"train-id": train_row},
                set(requested),
                {"val-id"},
                set(),
                {"missing-id"},
                completed_batches=2,
                resolved_revision="a" * 40,
                complete=True,
                post_download_revision="a" * 40,
            )
            complete = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(checkpoint_complete(complete, requested))
            self.assertEqual(["missing-id"], complete["api_no_row_ids"])
            self.assertEqual(
                ["missing-id"], complete["unmatched_keyframe_ids"]
            )


if __name__ == "__main__":
    unittest.main()
