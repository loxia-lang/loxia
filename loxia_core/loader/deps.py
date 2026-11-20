# SPDX-License-Identifier: MIT OR Apache-2.0
"""Resolução de dependências: hash, lock, cache e modo `--frozen` (ADR-0104/0105).

O loader recebe **raízes já resolvidas**; este módulo é a única camada que conhece o
manifest, o lock e o cache de checkouts. Nada aqui acessa a rede durante `run`: rede só em
`loxia lock`/`loxia fetch`, e `--offline` proíbe até neles.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import subprocess
import tarfile
import tomllib
from pathlib import Path

from loxia_core.loader.gitenv import git_env
from loxia_core.loader.loader import SOURCE_SUFFIX
from loxia_core.loader.lock import Lock, LockedPackage, render_lock
from loxia_core.loader.manifest import (
    MANIFEST_NAME,
    Manifest,
    ManifestError,
    parse_version,
)

_GIT_TIMEOUT_SECONDS = 300
_COMMIT = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


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


def lock_manifest(
    manifest: Manifest,
    *,
    offline: bool = False,
    cache_dir: Path | None = None,
) -> Lock:
    """Calcula o lock a partir do manifest (o `loxia lock` grava este resultado).

    Dependência `git` usa o cache: o mirror é criado/atualizado (rede, salvo `--offline`)
    e o commit é materializado para que o hash da árvore possa ser calculado.
    """
    packages: dict[str, LockedPackage] = {}
    base = manifest.path.parent
    cache = cache_dir or default_cache_dir(manifest)
    for name in sorted(manifest.dependencies):
        dependency = manifest.dependencies[name]
        if dependency.path is not None:
            if dependency.path == base:
                raise DependencyError(f"Dependency '{name}' points at the project root.")
            packages[name] = LockedPackage(
                name=name,
                sha256=tree_sha256(dependency.path),
                path=_relative(dependency.path, base),
                version=_dependency_version(dependency.path, name),
            )
            continue
        assert dependency.git is not None and dependency.rev is not None
        mirror = _ensure_mirror(dependency.git, cache, offline=offline, name=name)
        commit = _resolve_commit(mirror, dependency.rev, name=name)
        checkout = _checkout_dir(cache, dependency.git, commit)
        _ensure_checkout(mirror, commit, checkout, name=name)
        version = _dependency_version(checkout, name)
        if version is None:
            raise DependencyError(f"Dependency '{name}' needs [package].version in its loxia.toml.")
        packages[name] = LockedPackage(
            name=name,
            sha256=tree_sha256(checkout),
            git=dependency.git,
            rev=dependency.rev,
            commit=commit,
            version=version,
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
    cache = cache_dir or default_cache_dir(manifest)

    if not frozen:
        for name in sorted(manifest.dependencies):
            dependency = manifest.dependencies[name]
            if dependency.path is not None:
                roots[name] = dependency.path
                continue
            roots[name] = _locked_checkout(name, dependency.git, lock, cache)
        return roots

    if lock is None:
        if manifest.dependencies:
            raise DependencyError("loxia.lock is missing; run `loxia lock`.")
        return roots

    _verify_lock(manifest, lock)
    for name in sorted(manifest.dependencies):
        dependency = manifest.dependencies[name]
        entry = lock.packages[name]
        if dependency.path is not None:
            if tree_sha256(dependency.path) != entry.sha256:
                raise DependencyError(
                    f"Dependency '{name}' changed since loxia.lock; run `loxia lock`."
                )
            roots[name] = dependency.path
            continue
        assert dependency.git is not None
        checkout = _checkout_dir(cache, dependency.git, _entry_commit(entry))
        if not checkout.is_dir():
            raise DependencyError(
                f"Dependency '{name}' is not available locally; run `loxia fetch`."
            )
        if tree_sha256(checkout) != entry.sha256:
            raise DependencyError(
                f"Dependency '{name}' doesn't match loxia.lock; run `loxia fetch`."
            )
        roots[name] = checkout
    return roots


def fetch_dependencies(
    manifest: Manifest,
    *,
    lock: Lock | None,
    offline: bool,
    cache_dir: Path | None = None,
) -> None:
    """Materializa/verifica o que o lock manda, sem compilar o projeto."""
    if lock is None:
        raise DependencyError("loxia.lock is missing; run `loxia lock`.")
    _verify_lock(manifest, lock)
    cache = cache_dir or default_cache_dir(manifest)
    for name in sorted(manifest.dependencies):
        dependency = manifest.dependencies[name]
        entry = lock.packages[name]
        if dependency.path is not None:
            if tree_sha256(dependency.path) != entry.sha256:
                raise DependencyError(
                    f"Dependency '{name}' changed since loxia.lock; run `loxia lock`."
                )
            continue
        assert dependency.git is not None
        commit = _entry_commit(entry)
        checkout = _checkout_dir(cache, dependency.git, commit)
        if not checkout.is_dir() or tree_sha256(checkout) != entry.sha256:
            if checkout.is_dir():
                shutil.rmtree(checkout)
            mirror = _mirror_dir(cache, dependency.git)
            if not (mirror.is_dir() and _has_commit(mirror, commit)):
                mirror = _ensure_mirror(dependency.git, cache, offline=offline, name=name)
            _ensure_checkout(mirror, commit, checkout, name=name)
            if tree_sha256(checkout) != entry.sha256:
                raise DependencyError(
                    f"Dependency '{name}' doesn't match loxia.lock; run `loxia lock`."
                )


def lock_is_current(
    manifest: Manifest,
    lock: Lock,
    *,
    offline: bool = False,
    cache_dir: Path | None = None,
) -> bool:
    """`loxia lock --check`: o lock no disco é exatamente o que o manifest produz."""
    expected = lock_manifest(manifest, offline=offline, cache_dir=cache_dir)
    return render_lock(expected) == render_lock(lock)


def _verify_lock(manifest: Manifest, lock: Lock) -> None:
    """Identidade (nomes, origem, rev/versão) — sem hash; o hash é checado à parte."""
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
        if dependency.path is not None:
            if entry.path != _relative(dependency.path, base):
                raise DependencyError(
                    f"Dependency '{name}' changed since loxia.lock; run `loxia lock`."
                )
            if entry.version != _dependency_version(dependency.path, name):
                raise DependencyError(
                    f"Dependency '{name}' changed since loxia.lock; run `loxia lock`."
                )
            continue
        assert dependency.git is not None and dependency.rev is not None
        if entry.git != dependency.git or entry.rev != dependency.rev:
            raise DependencyError(
                f"Dependency '{name}' changed since loxia.lock; run `loxia lock`."
            )


def _locked_checkout(
    name: str,
    url: str | None,
    lock: Lock | None,
    cache: Path,
) -> Path:
    """Raiz de uma dependência git a partir do commit travado (nunca resolve rev)."""
    if lock is None or name not in lock.packages:
        raise DependencyError(
            f"Dependency '{name}' is not locked; run `loxia lock` and `loxia fetch`."
        )
    assert url is not None
    entry = lock.packages[name]
    checkout = _checkout_dir(cache, url, _entry_commit(entry))
    if not checkout.is_dir():
        raise DependencyError(f"Dependency '{name}' is not available locally; run `loxia fetch`.")
    if tree_sha256(checkout) != entry.sha256:
        raise DependencyError(f"Dependency '{name}' doesn't match loxia.lock; run `loxia fetch`.")
    return checkout


def _entry_commit(entry: LockedPackage) -> str:
    if entry.commit is None:
        raise DependencyError(f"Dependency '{entry.name}' has no commit in loxia.lock.")
    return entry.commit


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


# -- git: mirror, rev e checkout -----------------------------------------


def _url_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _mirror_dir(cache: Path, url: str) -> Path:
    return cache / "git" / f"{_url_key(url)}.git"


def _checkout_dir(cache: Path, url: str, commit: str) -> Path:
    return cache / "src" / _url_key(url) / commit


def _display_url(url: str) -> str:
    """URL sem userinfo (e sem caminho absoluto no `file://`): estável e sem vazar I3."""
    scheme, separator, rest = url.partition("://")
    if not separator:
        return url
    if scheme.lower() == "file":
        return f"file://{Path(rest).name}"
    authority, slash, tail = rest.partition("/")
    authority = authority.rpartition("@")[2]
    return f"{scheme}://{authority}{slash}{tail}"


def _require_git() -> None:
    if shutil.which("git") is None:
        raise DependencyError("git was not found in PATH; it is required for git dependencies.")


def _git_run(args: list[str], *, git_dir: Path | None = None) -> subprocess.CompletedProcess[bytes]:
    _require_git()
    environment = git_env()
    command = ["git"]
    if git_dir is not None:
        command.extend(["--git-dir", str(git_dir)])
    command.extend(args)
    try:
        return subprocess.run(
            command,
            capture_output=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            env=environment,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DependencyError(f"Can't run git: {type(error).__name__}.") from None


def _ensure_mirror(url: str, cache: Path, *, offline: bool, name: str) -> Path:
    mirror = _mirror_dir(cache, url)
    if mirror.is_dir():
        if not offline:
            fetched = _git_run(["fetch", "--quiet", "--tags", "--prune", "origin"], git_dir=mirror)
            if fetched.returncode != 0:
                raise DependencyError(f"Can't fetch '{name}' from '{_display_url(url)}'.")
        return mirror
    if offline:
        raise DependencyError(
            f"Dependency '{name}' is not in the cache; fetch it without `--offline`."
        )
    mirror.parent.mkdir(parents=True, exist_ok=True)
    cloned = _git_run(["clone", "--quiet", "--bare", "--", url, str(mirror)])
    if cloned.returncode != 0:
        shutil.rmtree(mirror, ignore_errors=True)
        raise DependencyError(f"Can't fetch '{name}' from '{_display_url(url)}'.")
    return mirror


def _has_commit(mirror: Path, commit: str) -> bool:
    return _git_run(["cat-file", "-e", f"{commit}^{{commit}}"], git_dir=mirror).returncode == 0


def _resolve_commit(mirror: Path, rev: str, *, name: str) -> str:
    resolved = _git_run(["rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"], git_dir=mirror)
    if resolved.returncode != 0:
        raise DependencyError(f"Can't resolve rev '{rev}' for dependency '{name}'.")
    commit = resolved.stdout.decode("ascii", "replace").strip()
    if not _COMMIT.match(commit):
        raise DependencyError(f"Can't resolve rev '{rev}' for dependency '{name}'.")
    return commit


def _ensure_checkout(mirror: Path, commit: str, checkout: Path, *, name: str) -> None:
    if checkout.is_dir():
        return
    archived = _git_run(["archive", "--format=tar", commit], git_dir=mirror)
    if archived.returncode != 0:
        raise DependencyError(f"Can't materialize dependency '{name}'.")
    checkout.parent.mkdir(parents=True, exist_ok=True)
    temporary = checkout.with_name(f"{checkout.name}.tmp")
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.mkdir()
    try:
        with tarfile.open(fileobj=io.BytesIO(archived.stdout), mode="r:") as archive:
            archive.extractall(temporary, filter="data")
    except (tarfile.TarError, OSError):
        shutil.rmtree(temporary, ignore_errors=True)
        raise DependencyError(f"Can't materialize dependency '{name}'.") from None
    os.replace(temporary, checkout)


def _relative(path: Path, base: Path) -> str:
    """Caminho relativo ao manifest, em posix, sem absoluto e sem `./` (I3)."""
    raw = os.path.relpath(path, base)
    return Path(raw).as_posix()
