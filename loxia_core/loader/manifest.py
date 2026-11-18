# SPDX-License-Identifier: MIT OR Apache-2.0
"""Manifest `loxia.toml`: raízes de módulo e dependências `path`/`git` (ADR-0088/0100/0105).

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
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_GIT_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_GIT_TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_GIT_SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*)://")
_GIT_SCP = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+:.+$")
_GIT_SCHEMES = frozenset({"https", "ssh", "git", "file"})
_TOP_LEVEL_KEYS = frozenset({"package", "modules", "dependencies"})
_DEPENDENCY_KEYS = frozenset({"path", "git", "rev"})


class ManifestError(Exception):
    """Manifest inválido; a mensagem já está pronta para o diagnóstico."""

    def __init__(self, message: str, *, line: int = 1, column: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column


@dataclass(frozen=True)
class Dependency:
    """Especificação declarada no manifest; a raiz resolvida mora no lock/loader."""

    path: Path | None = None
    git: str | None = None
    rev: str | None = None


@dataclass(frozen=True)
class Manifest:
    """Manifest já validado; caminhos absolutos, sem exibir no diagnóstico."""

    path: Path
    package: str | None
    version: str | None
    dependencies: dict[str, Dependency]
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
        raise ManifestError("Unknown manifest key(s): " + ", ".join(unknown) + ".")

    base = path.parent
    package, version = _package(data.get("package"))
    dependencies = _dependencies(data.get("dependencies"), base)
    module_paths = _module_paths(data.get("modules"), base)
    return Manifest(path, package, version, dependencies, module_paths)


def _table(value: object, what: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ManifestError(f"Expected '{what}' to be a table.")
    return cast("dict[str, object]", value)


def _string(value: object, what: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ManifestError(f"Expected '{what}' to be a non-empty string.")
    return value


def parse_version(value: object, what: str = "package.version") -> str:
    """Versão exata `X.Y.Z` (sem ranges, pre-release ou build metadata)."""
    version = _string(value, what)
    if not _VERSION.match(version):
        raise ManifestError(f"Expected '{what}' to be X.Y.Z, got '{version}'.")
    return version


def _package(value: object | None) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    package = _table(value, "package")
    unknown = sorted(set(package) - {"name", "version"})
    if unknown:
        raise ManifestError("Unknown [package] key(s): " + ", ".join(unknown) + ".")
    name = _string(package["name"], "package.name") if "name" in package else None
    version = parse_version(package["version"]) if "version" in package else None
    return name, version


def _dependencies(value: object | None, base: Path) -> dict[str, Dependency]:
    result: dict[str, Dependency] = {}
    if value is None:
        return result
    table = _table(value, "dependencies")
    for name in sorted(table):
        if name == "std":
            raise ManifestError("Dependency name 'std' is reserved.")
        if not _IDENTIFIER.match(name):
            raise ManifestError(f"Invalid dependency name '{name}'; use an ASCII identifier.")
        spec = _table(table[name], f"dependencies.{name}")
        unknown = sorted(set(spec) - _DEPENDENCY_KEYS)
        if unknown:
            raise ManifestError(
                f"Unsupported key(s) in dependency '{name}': "
                + ", ".join(unknown)
                + "; use 'path' or 'git' + 'rev'."
            )
        if ("path" in spec) == ("git" in spec):
            raise ManifestError(f"Dependency '{name}' needs exactly one of 'path' or 'git'.")
        if "path" in spec:
            if "rev" in spec:
                raise ManifestError(f"Dependency '{name}': 'rev' is only valid with 'git'.")
            result[name] = Dependency(
                path=_relative_dir(spec["path"], base, f"dependencies.{name}.path")
            )
            continue
        if "rev" not in spec:
            raise ManifestError(f"Git dependency '{name}' needs a 'rev'.")
        result[name] = Dependency(
            git=_git_url(spec["git"], f"dependencies.{name}.git"),
            rev=_git_rev(spec["rev"], f"dependencies.{name}.rev"),
        )
    return result


def _git_url(value: object, what: str) -> str:
    """URL absoluta (`https`/`ssh`/`git`/`file`) ou `user@host:path`; nunca `ext::`/`-x`."""
    url = _string(value, what)
    if any(ch.isspace() or ord(ch) < 32 for ch in url):
        raise ManifestError(f"Expected '{what}' to be a URL without whitespace.")
    if url.startswith("-") or "::" in url:
        raise ManifestError(f"Expected '{what}' to be a URL, not a git option/helper.")
    scheme = _GIT_SCHEME.match(url)
    if scheme is not None:
        if scheme.group(1).lower() not in _GIT_SCHEMES:
            raise ManifestError(f"Unsupported scheme in '{what}'; use https, ssh, git or file.")
        return url
    if _GIT_SCP.match(url):
        return url
    raise ManifestError(
        f"Expected '{what}' to be an absolute URL (https://, ssh://, git://, file://) "
        "or user@host:path."
    )


def _git_rev(value: object, what: str) -> str:
    """Commit completo (40/64 hex) ou tag simples; branch solto nunca."""
    rev = _string(value, what)
    if rev.startswith("-") or ".." in rev or any(ch.isspace() for ch in rev):
        raise ManifestError(f"Expected '{what}' to be a full commit SHA or a tag name.")
    if _GIT_SHA.match(rev) or _GIT_TAG.match(rev):
        return rev
    raise ManifestError(f"Expected '{what}' to be a full commit SHA or a tag name.")


def _module_paths(value: object | None, base: Path) -> tuple[Path, ...]:
    if value is None:
        return ()
    modules = _table(value, "modules")
    unknown = sorted(set(modules) - {"paths"})
    if unknown:
        raise ManifestError("Unknown [modules] key(s): " + ", ".join(unknown) + ".")
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
        raise ManifestError(f"'{what}' does not exist or is not a directory: '{raw}'.")
    return resolved
