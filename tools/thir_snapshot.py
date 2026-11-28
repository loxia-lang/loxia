# SPDX-License-Identifier: MIT OR Apache-2.0
"""Snapshot do THIR: hash por caso do corpus + goldens legíveis.

O THIR é o contrato entre o checker e os motores (ADR-0149, ADR-0154); o snapshot é o que
torna uma mudança do produtor **visível na revisão** em vez de drift silencioso. Mesmo
princípio do oráculo do front (ADR-0129):

- `tests/thir/manifest.json` guarda o sha256 da forma canônica do THIR de cada caso do
  corpus declarado (barato, cobre todos);
- o dump legível de um caso é `loxia build <caso> --emit=thir` (ou
  `tools.thir_snapshot` importado num REPL): o THIR é verboso por causa dos spans, então
  versionar goldens completos seria ruído de revisão, não contrato;
- atualizar é revisão consciente: `make thir-snapshot` regrava o manifesto e o diff de hash
  mostra exatamente quais casos o contrato mudou. "Consertar para passar" é proibido.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from loxia_core.thir.serialize import canonical
from tests.corpus_manifest import LEVELS
from tests.thir_support import module_for_case

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / "tests" / "thir"
MANIFEST = SNAPSHOT_DIR / "manifest.json"


def corpus_cases() -> list[str]:
    return sorted({case for level in LEVELS.values() for case in level})


def _digest(case: str) -> str:
    return hashlib.sha256(canonical(module_for_case(case)).encode("utf-8")).hexdigest()


def build_manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "description": "sha256 da forma canônica do THIR por caso do corpus (ADR-0154)",
        "cases": {case: _digest(case) for case in corpus_cases()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="confere contra o manifesto/goldens")
    group.add_argument("--update", action="store_true", help="regrava manifesto e goldens")
    args = parser.parse_args(argv)

    manifest = build_manifest()

    if args.update:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        sys.stdout.write(f"wrote {MANIFEST.relative_to(ROOT)}\n")
        return 0

    problems: list[str] = []
    if not MANIFEST.exists():
        problems.append("tests/thir/manifest.json não existe (rode `make thir-snapshot`)")
    else:
        current = json.loads(MANIFEST.read_text(encoding="utf-8"))
        expected = manifest["cases"]
        assert isinstance(expected, dict)
        cases = current.get("cases", {})
        assert isinstance(cases, dict)
        for case, digest in expected.items():
            if cases.get(case) != digest:
                problems.append(f"{case}: hash do THIR mudou")
        for case in sorted(set(cases) - set(expected)):
            problems.append(f"{case}: caso não está mais no corpus declarado")

    if problems:
        sys.stderr.write(
            "snapshot do THIR divergente:\n  " + "\n  ".join(problems) + "\n"
            "Se a mudança é intencional, rode `make thir-snapshot` e revise o diff.\n"
        )
        return 1
    sys.stdout.write("thir snapshot is current\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
