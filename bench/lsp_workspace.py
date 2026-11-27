# SPDX-License-Identifier: MIT OR Apache-2.0
"""Mede custo e retenção da análise do workspace do LSP sem subprocesso (ADR-0151).

Uso:
    uv run python bench/lsp_workspace.py
    uv run python bench/lsp_workspace.py --sizes 50,500 --memory
    uv run python bench/lsp_workspace.py --json

Gera workspaces sintéticos em que cada arquivo importa `std.lists` (o formato que
domina o custo frio: um `check` por arquivo com o closure) e mede:

- `cold`: build do zero (`WorkspaceCache` e `ModuleCache` novos);
- `warm`: segunda consulta com o fingerprint intacto;
- `rebuild`: editar um arquivo e consultar (o cache por arquivo reanalisa só ele);
- `retained`/`peak` (`--memory`): memória viva/pico do cache depois do build
  (`tracemalloc` com `gc` coletado), mais `entries` e `module_tokens` retidos.

No repo atual mede a descoberta (`Server._workspace_files` quente) e o fingerprint
(`blake2b` dos textos), que é o custo por request depois do #199. O workspace do repo
não é analisado aqui: o corpus tem casos com erro de sintaxe de propósito.

Não roda no CI.
"""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from io import BytesIO
from pathlib import Path

from loxia import rename
from loxia.lsp import Server
from loxia_core.loader.module_cache import ModuleCache

ROOT = Path(__file__).resolve().parents[1]
REPEAT = 3
HELPERS = 6


def _module_source(index: int) -> str:
    helpers = "\n".join(
        f"fn helper_{helper}(x: Int) -> Int {{ return x + {helper} }}" for helper in range(HELPERS)
    )
    return (
        "import std.lists as lists\n"
        "\n"
        f"val v{index}: Int = lists.sum([1, 2]) + {index}\n"
        f"fn f{index}(x: Int) -> Int {{ return v{index} + x }}\n"
        f"{helpers}\n"
    )


def _workspace(size: int) -> Path:
    root = Path(tempfile.mkdtemp(prefix=f"loxia-lsp-ws-{size}-"))
    for index in range(size):
        (root / f"m{index:04d}.lx").write_text(_module_source(index), encoding="utf-8")
    return root


def _files(root: Path) -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in sorted(root.glob("*.lx"))}


def _timed(call: Callable[[], object]) -> float:
    start = time.perf_counter()
    call()
    return (time.perf_counter() - start) * 1000


def _median(call: Callable[[], object], repeat: int = REPEAT) -> float:
    return statistics.median(_timed(call) for _ in range(repeat))


def measure(size: int, *, memory: bool) -> dict[str, float]:
    root = _workspace(size)
    files = _files(root)
    cache = rename.WorkspaceCache()
    module_cache = ModuleCache()

    cold = _timed(lambda: cache.get(root, files, module_cache))
    warm = _median(lambda: cache.get(root, files, module_cache))

    changed = dict(files)
    first = sorted(files)[0]
    changed[first] = files[first] + "\nval extra = 1\n"

    # Uma amostra: a partir da segunda, a entry do arquivo já reanalisado ficaria
    # no cache e a medição viraria o caminho quente. Só o workspace é descartado —
    # as camadas por conteúdo são o que deve reanalisar um único arquivo.
    cache.clear()
    rebuild = _timed(lambda: cache.get(root, changed, module_cache))

    result = {
        "files": len(files),
        "source_kb": sum(len(text.encode()) for text in files.values()) / 1024,
        "cold_ms": cold,
        "warm_ms": warm,
        "rebuild_ms": rebuild,
    }
    if memory:
        fresh = rename.WorkspaceCache()
        tracemalloc.start()
        fresh.get(root, files, ModuleCache())
        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result.update(
            retained_mb=current / 1e6,
            peak_mb=peak / 1e6,
            entries=len(fresh._entries),
            module_tokens=fresh._module_tokens,
        )
    return result


def measure_scan(size: int) -> dict[str, float]:
    """Descoberta do root, sem analisar: o custo por request depois do #199."""
    root = _workspace(size)
    server = Server(BytesIO(), BytesIO())
    server.root = root
    server._workspace_files()  # aquece o cache de leitura do disco
    return {"files": size, "scan_ms": _median(server._workspace_files)}


def measure_std(*, memory: bool) -> dict[str, float]:
    std = ROOT / "std"
    files = _files(std)
    cache = rename.WorkspaceCache()
    result = {"files": len(files), "cold_ms": _timed(lambda: cache.get(std, files, ModuleCache()))}
    if memory:
        fresh = rename.WorkspaceCache()
        tracemalloc.start()
        fresh.get(std, files, ModuleCache())
        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result.update(
            retained_mb=current / 1e6,
            peak_mb=peak / 1e6,
            entries=len(fresh._entries),
            module_tokens=fresh._module_tokens,
        )
    return result


def measure_repo() -> dict[str, float]:
    server = Server(BytesIO(), BytesIO())
    server.root = ROOT
    server._workspace_files()  # aquece o cache de leitura do disco
    scan = _median(server._workspace_files)
    files = dict(server._workspace_files())
    total = sum(len(text.encode("utf-8")) for text in files.values())
    fingerprint = _median(lambda: [rename._digest(text) for text in files.values()])
    return {
        "files": len(files),
        "source_mb": total / 1e6,
        "scan_ms": scan,
        "fingerprint_ms": fingerprint,
    }


def _print(label: str, data: dict[str, float]) -> None:
    parts: list[str] = []
    for key, value in data.items():
        if key in {"files", "entries", "module_tokens"}:
            parts.append(f"{key}={int(value)}")
        elif key.endswith("_mb"):
            parts.append(f"{key.replace('_mb', '')}={value:.1f}MB")
        elif key.endswith("_kb"):
            parts.append(f"{key.replace('_kb', '')}={value:.0f}KB")
        else:
            parts.append(f"{key.replace('_ms', '')}={value:.1f}ms")
    print(f"{label:<12} " + "  ".join(parts))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bench/lsp_workspace.py", description=__doc__)
    parser.add_argument("--sizes", default="50,500", help="tamanhos separados por vírgula")
    parser.add_argument("--memory", action="store_true", help="mede retenção (tracemalloc)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    sizes = [int(item) for item in args.sizes.split(",") if item.strip()]
    results: dict[str, dict[str, float]] = {}
    for size in sizes:
        results[f"workspace_{size}"] = measure(size, memory=args.memory)
        _print(f"{size} files", results[f"workspace_{size}"])
    results["scan_5000"] = measure_scan(5000)
    _print("scan 5000", results["scan_5000"])
    results["std"] = measure_std(memory=args.memory)
    _print("std/", results["std"])
    results["repo"] = measure_repo()
    _print("repo", results["repo"])
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
