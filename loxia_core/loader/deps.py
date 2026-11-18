# SPDX-License-Identifier: MIT OR Apache-2.0
"""Resolução de dependências: hash de árvore, lock e modo `--frozen` (ADR-0104).

O loader recebe **raízes já resolvidas**; este módulo é a única camada que conhece o
manifest, o lock e (na fase 2) o cache de checkouts git. Nada aqui acessa a rede durante
`run`: rede só em `loxia lock`/`loxia fetch`, e `--offline` proíbe até neles.
"""

from __future__ import annotations

import hashlib
import os
import tomllib
from pathlib import Path

from loxia_core.loader.loader import SOURCE_SUFFIX
from loxia_core.loader.lock import Lock, LockedPackage, render_lock
from loxia_core.loader.manifest import (
    MANIFEST_NAME,
    Manifest,
    ManifestError,
    parse_version,
)


class DependencyError(Exception):
    """Falha de resolução de dependência; mensagem pronta para o diagnóstico."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def default_cache_dir(manifest: Manifest) -> Path:
    """Cache por projeto: sem `HOME` e sem variável de ambiente (I3)."""
    return manifest.path.parent / ".loxia" / "cache"


def tree_sha256(root: Path) -> str:
    """Hash determinístico da árvore `.lx` (caminho posix + sha256 do conteúdo)."""
    base = root.resolve()
    digest = hashlib.sha256()
    files: list[tuple[str, Path]] = []
    for path in base.rglob(f"*{SOURCE_SUFFIX}"):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(base).as_posix()
        except ValueError:  # pragma: no cover - rglob sempre parte de base
            raise DependencyError(
                f"Can't hash '{path.name}' outside the dependency root."
            ) from None
        resolved = path.resolve()
        if base not in resolved.parents:
            raise DependencyError(f"Symlink '{relative}' escapes the dependency root.")
        files.append((relative, path))
    for relative, path in sorted(files):
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
        digest.update(b"\n")
    return digest.hexdigest()


def lock_manifest(manifest: Manifest, *, cache_dir: Path | None = None) -> Lock:
    """Calcula o lock a partir do manifest (o `loxia lock` grava este resultado)."""
    packages: dict[str, LockedPackage] = {}
    base = manifest.path.parent
    for name in sorted(manifest.dependencies):
        dependency = manifest.dependencies[name]
        if dependency.path is None:
            raise DependencyError(
                f"Unsupported dependency '{name}': only 'path' is supported in this version."
            )
        if dependency.path == base:
            raise DependencyError(f"Dependency '{name}' points at the project root.")
        packages[name] = LockedPackage(
            name=name,
            sha256=tree_sha256(dependency.path),
            path=_relative(dependency.path, base),
            version=_dependency_version(dependency.path, name),
        )
    return Lock(packages)


def resolve_dependencies(
    manifest: Manifest,
    *,
    lock: Lock | None,
    frozen: bool,
    offline: bool,
    cache_dir: Path | None = None,
) -> dict[str, Path]:
    """Raízes que o loader consome; `frozen` troca resolução viva pelo lock."""
    roots: dict[str, Path] = {}
    if not frozen:
        for name in sorted(manifest.dependencies):
            dependency = manifest.dependencies[name]
            if dependency.path is None:
                raise DependencyError(
                    f"Unsupported dependency '{name}': only 'path' is supported in this version."
                )
            roots[name] = dependency.path
        return roots

    if lock is None:
        if manifest.dependencies:
            raise DependencyError("loxia.lock is missing; run `loxia lock`.")
        return roots

    _verify_lock(manifest, lock)
    for name in sorted(manifest.dependencies):
        dependency = manifest.dependencies[name]
        assert dependency.path is not None  # garantido por _verify_lock
        entry = lock.packages[name]
        if tree_sha256(dependency.path) != entry.sha256:
            raise DependencyError(
                f"Dependency '{name}' changed since loxia.lock; run `loxia lock`."
            )
        roots[name] = dependency.path
    return roots


def fetch_dependencies(
    manifest: Manifest,
    *,
    lock: Lock | None,
    offline: bool,
    cache_dir: Path | None = None,
) -> None:
    """Materializa/verifica o que o lock manda, sem compilar o projeto."""
    del offline, cache_dir  # fase 1: `path` já está no disco; `git` usa no ADR-0105
    if lock is None:
        raise DependencyError("loxia.lock is missing; run `loxia lock`.")
    _verify_lock(manifest, lock)
    for name in sorted(manifest.dependencies):
        dependency = manifest.dependencies[name]
        assert dependency.path is not None
        entry = lock.packages[name]
        if tree_sha256(dependency.path) != entry.sha256:
            raise DependencyError(
                f"Dependency '{name}' changed since loxia.lock; run `loxia lock`."
            )


def lock_is_current(manifest: Manifest, lock: Lock, *, cache_dir: Path | None = None) -> bool:
    """`loxia lock --check`: o lock no disco é exatamente o que o manifest produz."""
    del cache_dir
    return render_lock(lock_manifest(manifest)) == render_lock(lock)


def _verify_lock(manifest: Manifest, lock: Lock) -> None:
    """Identidade (nomes, origem, versão) — sem hash; o hash é checado à parte."""
    base = manifest.path.parent
    expected = set(manifest.dependencies)
    present = set(lock.packages)
    missing = sorted(expected - present)
    extra = sorted(present - expected)
    if missing:
        raise DependencyError(
            f"Dependency '{missing[0]}' is missing from loxia.lock; run `loxia lock`."
        )
    if extra:
        raise DependencyError(
            f"loxia.lock contains '{extra[0]}', which is not in loxia.toml; run `loxia lock`."
        )
    for name in sorted(expected):
        dependency = manifest.dependencies[name]
        entry = lock.packages[name]
        if dependency.path is None:
            raise DependencyError(
                f"Unsupported dependency '{name}': only 'path' is supported in this version."
            )
        if entry.path != _relative(dependency.path, base):
            raise DependencyError(
                f"Dependency '{name}' changed since loxia.lock; run `loxia lock`."
            )
        if entry.version != _dependency_version(dependency.path, name):
            raise DependencyError(
                f"Dependency '{name}' changed since loxia.lock; run `loxia lock`."
            )


def _dependency_version(root: Path, name: str) -> str | None:
    """`[package].version` do manifest da dependência (opcional; só o campo é lido)."""
    manifest = root / MANIFEST_NAME
    if not manifest.is_file():
        return None
    try:
        text = manifest.read_text(encoding="utf-8")
        data = tomllib.loads(text)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise DependencyError(f"Dependency '{name}' has an invalid loxia.toml: {error}.") from None
    package = data.get("package")
    if not isinstance(package, dict):
        return None
    version = package.get("version")
    if version is None:
        return None
    try:
        return parse_version(version)
    except ManifestError as error:
        raise DependencyError(f"Dependency '{name}': {error.message}") from None


def _relative(path: Path, base: Path) -> str:
    """Caminho relativo ao manifest, em posix, sem absoluto e sem `./` (I3)."""
    raw = os.path.relpath(path, base)
    return Path(raw).as_posix()
