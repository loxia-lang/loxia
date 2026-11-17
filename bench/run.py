# SPDX-License-Identifier: MIT OR Apache-2.0
"""Harness de benchmark do interpretador.

Uso:
    uv run python bench/run.py                 # mede e compara com baseline.json
    uv run python bench/run.py --update        # regrava o baseline
    uv run python bench/run.py --repeat 7 --tolerance 1.25
    uv run python bench/run.py --json

Por que medir o processo inteiro: o alvo é o CLI real (`main.py script.lx`), então
o tempo inclui boot do Python (~40 ms). Casos devem durar >100 ms para o ruído
não dominar — se um caso ficar rápido demais, aumente as constantes dele.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = Path(__file__).resolve().parent / "cases"
BASELINE_PATH = Path(__file__).resolve().parent / "baseline.json"
ENTRYPOINT = ROOT / "main.py"

DEFAULT_REPEAT = 5
DEFAULT_TOLERANCE = 1.35
TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class Measurement:
    name: str
    median_ms: float
    min_ms: float


def discover_cases() -> list[Path]:
    return sorted(CASES_DIR.glob("*.lx"))


def run_once(path: Path) -> float:
    return _run_timed([sys.executable, str(ENTRYPOINT), str(path)], f"caso {path.name}")


def build_native(path: Path, binary: Path) -> None:
    process = subprocess.run(
        [
            sys.executable,
            str(ENTRYPOINT),
            "--emit=exe",
            "-o",
            str(binary),
            str(path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    if process.returncode != 0:
        raise SystemExit(
            f"build nativo de {path.name} falhou (exit {process.returncode}):\n{process.stderr}"
        )


def run_native(binary: Path) -> float:
    return _run_timed([str(binary)], f"binário {binary.name}")


def _run_timed(command: list[str], label: str) -> float:
    start = time.perf_counter()
    process = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    elapsed = time.perf_counter() - start

    if process.returncode != 0:
        raise SystemExit(f"{label} falhou (exit {process.returncode}):\n{process.stderr}")

    return elapsed * 1000.0


def measure(path: Path, repeat: int, *, native: Path | None = None) -> Measurement:
    run = run_native if native is not None else run_once
    target = native if native is not None else path
    run(target)  # aquecimento: cache de página, imports, etc.

    samples = [run(target) for _ in range(repeat)]
    return Measurement(
        name=path.stem,
        median_ms=statistics.median(samples),
        min_ms=min(samples),
    )


def load_baseline() -> dict[str, float]:
    if not BASELINE_PATH.exists():
        return {}

    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {name: float(value) for name, value in data.get("cases", {}).items()}


def save_baseline(measurements: list[Measurement]) -> None:
    payload = {
        "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "python": platform.python_version(),
        "plataforma": platform.platform(),
        "casos_ms": {m.name: round(m.median_ms, 2) for m in measurements},
    }
    # Compatibilidade com o leitor (que usa "cases"), mantendo nomes legíveis.
    payload["cases"] = payload.pop("casos_ms")

    BASELINE_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"baseline atualizado em {BASELINE_PATH.relative_to(ROOT)}")


def print_report(
    measurements: list[Measurement],
    baseline: dict[str, float],
    tolerance: float,
    *,
    native: bool = False,
) -> int:
    if not measurements:
        print("nenhum caso em bench/cases/", file=sys.stderr)
        return 1

    name_width = max(len(m.name) for m in measurements)
    compare = "speedup" if native else "vs base"
    header = f"{'caso':<{name_width}}  {'mediana':>10}  {'mínimo':>10}  {compare:>8}  status"
    print(header)
    print("-" * len(header))

    regressions = 0
    for measurement in measurements:
        reference = baseline.get(measurement.name)
        if reference is None:
            ratio_text, status = "—", "sem baseline"
        elif native:
            ratio = reference / measurement.median_ms
            ratio_text = f"{ratio:.1f}x" if ratio < 100 else ">100x"
            status = "mais rápido" if ratio > 1 else "mais lento"
        else:
            ratio = measurement.median_ms / reference
            ratio_text = f"{ratio:.2f}x"

            if ratio > tolerance:
                status = "REGRESSÃO"
                regressions += 1
            elif ratio < 1 / tolerance:
                status = "mais rápido"
            else:
                status = "ok"

        print(
            f"{measurement.name:<{name_width}}  "
            f"{measurement.median_ms:>8.1f}ms  "
            f"{measurement.min_ms:>8.1f}ms  "
            f"{ratio_text:>8}  {status}"
        )

    if regressions:
        print(
            f"\n{regressions} caso(s) acima da tolerância de {tolerance:.2f}x. "
            "Se a piora for intencional, rode com --update."
        )

    return 1 if regressions else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="bench/run.py", description="Benchmark do interpretador")
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEAT, help="medidas por caso")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE,
        help="fator máximo aceitável vs baseline (default 1.35)",
    )
    parser.add_argument("--update", action="store_true", help="regrava o baseline")
    parser.add_argument(
        "--native",
        action="store_true",
        help="compila com --emit=exe e mede o binário (não regrava o baseline)",
    )
    parser.add_argument("--json", action="store_true", help="imprime resultado em JSON")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cases = discover_cases()

    if args.repeat < 1:
        print("--repeat deve ser >= 1", file=sys.stderr)
        return 2
    if args.update and args.native:
        print("--native não regrava o baseline do interpretador", file=sys.stderr)
        return 2

    if args.native:
        with tempfile.TemporaryDirectory(prefix="lox-bench-") as directory:
            binaries = {}
            for case in cases:
                binary = Path(directory) / case.stem
                build_native(case, binary)
                binaries[case] = binary
            measurements = [measure(case, args.repeat, native=binaries[case]) for case in cases]
    else:
        measurements = [measure(case, args.repeat) for case in cases]

    if args.update:
        save_baseline(measurements)

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "caso": m.name,
                        "mediana_ms": round(m.median_ms, 2),
                        "minimo_ms": round(m.min_ms, 2),
                        "motor": "nativo" if args.native else "interpretador",
                    }
                    for m in measurements
                ],
                indent=2,
                ensure_ascii=False,
            )
        )

    if args.update:
        return 0

    baseline = load_baseline()
    if not baseline:
        print("sem baseline: rode com --update para criar\n")

    return print_report(measurements, baseline, args.tolerance, native=args.native)


if __name__ == "__main__":
    raise SystemExit(main())
