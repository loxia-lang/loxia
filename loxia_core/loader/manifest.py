"""Manifest `loxia.toml`: raízes de módulo e dependências `path` (ADR-0088/0100).

O manifest é descoberto do diretório do entry para cima (primeiro vence) e é a única
fonte de raízes fora do projeto. O `import` continua só com identificadores; `..` nunca
aparece no fonte.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

MANIFEST_NAME = "loxia.toml"
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TOP_LEVEL_KEYS = frozenset({"package", "modules", "dependencies"})


class ManifestError(Exception):
    """Manifest inválido; a mensagem já está pronta para o diagnóstico."""

    def __init__(
        self, message: str, *, line: int = 1, column: int = 1
    ) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column


@dataclass(frozen=True)
class Manifest:
    """Manifest já validado; caminhos absolutos, sem exibir no diagnóstico."""

    path: Path
    package: str | None
    dependencies: dict[str, Path]
    module_paths: tuple[Path, ...]


def discover_manifest(start: Path) -> Path | None:
    """Primeiro `loxia.toml` de `start` até a raiz, sem variável de ambiente."""
    directory = start.resolve()
    for candidate in (directory, *directory.parents):
        manifest = candidate / MANIFEST_NAME
        if manifest.is_file():
            return manifest
    return None


def parse_manifest(path: Path, text: str) -> Manifest:
    """Valida o TOML e resolve caminhos relativos à pasta do manifest."""
    try:
        raw: object = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ManifestError(
            f"Invalid TOML: {error}.",
            line=getattr(error, "lineno", 1) or 1,
            column=getattr(error, "colno", 1) or 1,
        ) from None

    data = _table(raw, "manifest")
    unknown = sorted(set(data) - _TOP_LEVEL_KEYS)
    if unknown:
        raise ManifestError(
            "Unknown manifest key(s): " + ", ".join(unknown) + "."
        )

    base = path.parent
    package = _package_name(data.get("package"))
    dependencies = _dependencies(data.get("dependencies"), base)
    module_paths = _module_paths(data.get("modules"), base)
    return Manifest(path, package, dependencies, module_paths)


def _table(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ManifestError(f"Expected '{what}' to be a table.")
    return cast("dict[str, object]", value)


def _string(value: object, what: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ManifestError(f"Expected '{what}' to be a non-empty string.")
    return value


def _package_name(value: object | None) -> str | None:
    if value is None:
        return None
    package = _table(value, "package")
    unknown = sorted(set(package) - {"name"})
    if unknown:
        raise ManifestError(
            "Unknown [package] key(s): " + ", ".join(unknown) + "."
        )
    if "name" not in package:
        return None
    return _string(package["name"], "package.name")


def _dependencies(value: object | None, base: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    if value is None:
        return result
    table = _table(value, "dependencies")
    for name in sorted(table):
        if name == "std":
            raise ManifestError("Dependency name 'std' is reserved.")
        if not _IDENTIFIER.match(name):
            raise ManifestError(
                f"Invalid dependency name '{name}'; use an ASCII identifier."
            )
        spec = _table(table[name], f"dependencies.{name}")
        unknown = sorted(set(spec) - {"path"})
        if unknown:
            raise ManifestError(
                f"Unsupported key(s) in dependency '{name}': "
                + ", ".join(unknown)
                + "; only 'path' is supported."
            )
        if "path" not in spec:
            raise ManifestError(
                f"Dependency '{name}' needs a 'path'."
            )
        result[name] = _relative_dir(spec["path"], base, f"dependencies.{name}.path")
    return result


def _module_paths(value: object | None, base: Path) -> tuple[Path, ...]:
    if value is None:
        return ()
    modules = _table(value, "modules")
    unknown = sorted(set(modules) - {"paths"})
    if unknown:
        raise ManifestError(
            "Unknown [modules] key(s): " + ", ".join(unknown) + "."
        )
    raw_paths = modules.get("paths", [])
    if not isinstance(raw_paths, list):
        raise ManifestError("Expected 'modules.paths' to be a list of strings.")
    result: list[Path] = []
    for index, raw in enumerate(raw_paths):
        result.append(_relative_dir(raw, base, f"modules.paths[{index}]"))
    return tuple(result)


def _relative_dir(value: object, base: Path, what: str) -> Path:
    raw = _string(value, what)
    candidate = Path(raw)
    if candidate.is_absolute():
        raise ManifestError(f"'{what}' must be relative to the manifest.")
    resolved = (base / candidate).resolve()
    if not resolved.is_dir():
        raise ManifestError(
            f"'{what}' does not exist or is not a directory: '{raw}'."
        )
    return resolved
