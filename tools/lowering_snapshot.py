# SPDX-License-Identifier: MIT OR Apache-2.0
"""Snapshot do lowering: sha256 do `.ll` de cada caso do corpus.

A migração da F2 troca a árvore que o lowering consome (AST → THIR). Para provar que a
troca é **só de fronteira** e não muda codegen, o `.ll` emitido tem de continuar byte a
byte igual. Este snapshot é congelado **antes** da migração; o teste
`tests/test_lowering_ll.py` recusa qualquer byte diferente, e o diff não tem como ser
"ajustado para passar" sem aparecer aqui.

Atualizar só é legítimo quando o codegen muda de propósito (outra fatia, com issue). O
manifesto é gerado pelo build real do CLI (`build --emit=ll`), não por um caminho paralelo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from tests.corpus_manifest import LEVELS
from tests.inprocess import run_cli

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "tests" / "ll"
MANIFEST = SNAPSHOT_DIR / "manifest.json"


def corpus_cases() -> list[str]:
    return sorted({case for level in LEVELS.values() for case in level})


def ll_digest(case: str) -> str:
    """sha256 do `.ll` emitido para o caso; `None` embutido vira erro claro."""
    result = run_cli("build", case, "--emit=ll")
    if result.returncode != 0:
        raise RuntimeError(f"{case}: build --emit=ll falhou ({result.returncode}): {result.stderr}")
    return hashlib.sha256(result.stdout.encode("utf-8")).hexdigest()


def build_manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "description": "sha256 do .ll emitido por caso do corpus (gate da migração THIR)",
        "cases": {case: ll_digest(case) for case in corpus_cases()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="confere o manifesto versionado")
    group.add_argument("--update", action="store_true", help="regrava o manifesto")
    args = parser.parse_args(argv)

    if args.update:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        manifest = build_manifest()
        MANIFEST.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        sys.stdout.write(f"wrote {MANIFEST.relative_to(ROOT)}\n")
        return 0

    if not MANIFEST.exists():
        sys.stderr.write("tests/ll/manifest.json não existe (rode `make ll-snapshot`)\n")
        return 1
    current = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = current.get("cases", {})
    assert isinstance(cases, dict)
    expected = build_manifest()["cases"]
    assert isinstance(expected, dict)
    problems: list[str] = []
    for case in sorted(set(expected) - set(cases)):
        problems.append(f"{case}: caso novo no corpus declarado (manifesto desatualizado)")
    for case in sorted(set(cases) - set(expected)):
        problems.append(f"{case}: caso não está mais no corpus declarado")
    for case, digest in expected.items():
        if case in cases and cases[case] != digest:
            problems.append(f"{case}: o .ll mudou")
    if problems:
        sys.stderr.write("lowering divergiu do snapshot:\n  " + "\n  ".join(problems) + "\n")
        return 1
    sys.stdout.write("lowering snapshot is current\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
