# SPDX-License-Identifier: MIT OR Apache-2.0
"""Gate da matriz de features (ADR-0121)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.feature_coverage import (
    DOC,
    FEATURES,
    SNAPSHOT,
    _levels,
    load_features,
    validate,
)

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "feature_coverage.py"


def test_matrix_validates_and_covers_every_level() -> None:
    features = load_features()
    assert features, "tests/features.toml está vazio"
    assert validate(features) == []
    covered = {feature.differential for feature in features.values()}
    assert set(_levels()) <= covered


def test_snapshot_matches_the_curated_matrix() -> None:
    payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["features"] == {
        feature.id: {
            "differential": feature.differential,
            "golden": list(feature.golden),
        }
        for feature in sorted(load_features().values(), key=lambda item: item.id)
    }


def test_generated_doc_is_up_to_date() -> None:
    result = subprocess.run(
        [sys.executable, str(TOOL), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    text = DOC.read_text(encoding="utf-8")
    for feature in load_features():
        assert f"**{feature}**" in text


def test_features_file_is_the_single_source() -> None:
    assert FEATURES.is_file()
    assert SNAPSHOT.is_file()
    assert DOC.is_file()
