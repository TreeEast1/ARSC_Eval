"""Independently replay every frozen Round 9 salt into cycles and maps.

No ``arsc_eval`` construction code is imported.  This closes the distinction
between checking a stored cycle partition and independently verifying that the
declared salt deterministically produces that partition.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDITY_ROOT = PROJECT_ROOT / "outputs" / "validity"
PROTOCOL_PATH = VALIDITY_ROOT / "round9_multimap_protocol.json"
MAP_PATH = VALIDITY_ROOT / "round9_multimap_maps.npz"
OUTPUT_PATH = VALIDITY_ROOT / "round9_multimap_salt_replay_audit.json"
MAP_IDS = tuple(f"map{index:02d}" for index in range(20))
SALTS = tuple(f"arsc-round9-map{index:02d}" for index in range(20))
Q_VALUES = (0.0, 0.25, 0.5, 0.75, 1.0)
SAMPLE_COUNT = 4557


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def array_sha256(values: np.ndarray) -> str:
    return hashlib.sha256(
        np.ascontiguousarray(values).tobytes()
    ).hexdigest().upper()


def clip_group(file_name: str) -> str:
    return re.sub(r"_(?:1|3)$", "", Path(file_name).stem)


def replay_cycles(
    names: list[str], salt: str
) -> tuple[np.ndarray, np.ndarray, int]:
    groups = [clip_group(name) for name in names]
    order = sorted(
        range(len(names)),
        key=lambda index: (
            hashlib.sha256(
                f"{salt}|{names[index]}".encode("utf-8")
            ).hexdigest(),
            names[index],
            index,
        ),
    )
    triplet = []
    triplet_groups = set()
    for index in reversed(order):
        if groups[index] not in triplet_groups:
            triplet.append(index)
            triplet_groups.add(groups[index])
        if len(triplet) == 3:
            break
    require(len(triplet) == 3, f"{salt}: cannot form triplet")
    triplet_set = set(triplet)
    remaining = [index for index in order if index not in triplet_set]
    half = len(remaining) // 2
    left = remaining[:half]
    right = remaining[half:]
    selected_rotation = None
    paired_right = None
    for rotation in range(half):
        candidate = right[rotation:] + right[:rotation]
        if all(
            groups[first] != groups[second]
            for first, second in zip(left, candidate)
        ):
            selected_rotation = rotation
            paired_right = candidate
            break
    require(
        paired_right is not None and selected_rotation is not None,
        f"{salt}: no clip-safe rotation",
    )
    pairs = list(zip(left, paired_right))
    pairs.sort(
        key=lambda pair: (
            hashlib.sha256(
                (
                    f"{salt}|cycle|"
                    + "|".join(sorted(names[index] for index in pair))
                ).encode("utf-8")
            ).hexdigest(),
            pair,
        )
    )
    return (
        np.asarray(pairs, dtype=np.int64),
        np.asarray(triplet, dtype=np.int64),
        int(selected_rotation),
    )


def replay_maps(
    pair_cycles: np.ndarray, final_triplet: np.ndarray
) -> np.ndarray:
    identity = np.arange(SAMPLE_COUNT, dtype=np.int64)
    cycles = [
        tuple(int(value) for value in pair)
        for pair in pair_cycles.tolist()
    ]
    cycles.append(tuple(int(value) for value in final_triplet.tolist()))
    maps = []
    for q in Q_VALUES:
        source = identity.copy()
        active = (
            cycles
            if q == 1.0
            else cycles[: int(np.floor(q * SAMPLE_COUNT / 2.0 + 0.5))]
        )
        for cycle in active:
            for destination, source_index in zip(
                cycle, (*cycle[1:], cycle[0])
            ):
                source[destination] = source_index
        maps.append(source)
    return np.stack(maps)


def main() -> int:
    require(not OUTPUT_PATH.exists(), "refusing to overwrite replay audit")
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    require(
        tuple(protocol["map_realizations"]["map_ids"]) == MAP_IDS
        and tuple(protocol["map_realizations"]["salts"]) == SALTS,
        "protocol IDs/salts differ",
    )
    with np.load(MAP_PATH, allow_pickle=False) as archive:
        names = [str(value) for value in archive["file_names"].tolist()]
        stored = {
            map_id: {
                "pairs": archive[f"{map_id}_pair_cycles"].copy(),
                "triplet": archive[f"{map_id}_final_triplet"].copy(),
                "maps": archive[f"{map_id}_source_maps"].copy(),
            }
            for map_id in MAP_IDS
        }
    require(len(names) == SAMPLE_COUNT, "sample count differs")
    by_map: dict[str, Any] = {}
    for map_id, salt in zip(MAP_IDS, SALTS):
        pairs, triplet, rotation = replay_cycles(names, salt)
        maps = replay_maps(pairs, triplet)
        require(
            np.array_equal(pairs, stored[map_id]["pairs"]),
            f"{map_id}: independently replayed pairs differ",
        )
        require(
            np.array_equal(triplet, stored[map_id]["triplet"]),
            f"{map_id}: independently replayed triplet differs",
        )
        require(
            np.array_equal(maps, stored[map_id]["maps"]),
            f"{map_id}: independently replayed maps differ",
        )
        by_map[map_id] = {
            "salt": salt,
            "right_half_rotation": rotation,
            "pair_cycle_count": int(len(pairs)),
            "final_triplet": triplet.tolist(),
            "pair_cycles_sha256": array_sha256(pairs),
            "source_maps_sha256": array_sha256(maps),
            "exact_match": True,
        }
    audit = {
        "study": "Round 9 independent salt-to-cycle-to-map replay",
        "status": "PASS",
        "independence": {
            "imports_arsc_eval_construction_code": False,
            "reimplements_salted_filename_order": True,
            "reimplements_distinct_clip_triplet": True,
            "reimplements_rotation_search_and_cycle_sort": True,
            "reimplements_nested_map_activation": True,
            "targets_predictions_confidences_errors_or_metrics_read": False,
        },
        "inputs": {
            "protocol_sha256": sha256_file(PROTOCOL_PATH),
            "map_artifact_sha256": sha256_file(MAP_PATH),
        },
        "maps": by_map,
        "summary": {
            "maps_replayed": len(by_map),
            "exact_cycle_matches": 20,
            "exact_source_map_matches": 20,
            "all_passed": True,
        },
    }
    OUTPUT_PATH.write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": audit["status"],
                "maps_replayed": len(by_map),
                "output": str(OUTPUT_PATH.relative_to(PROJECT_ROOT)).replace(
                    "\\", "/"
                ),
                "sha256": sha256_file(OUTPUT_PATH),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
