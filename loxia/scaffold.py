# SPDX-License-Identifier: MIT OR Apache-2.0
"""Scaffolding de projeto: `loxia new` e `loxia init` (ADR-0106).

O template é mínimo e determinístico: `loxia.toml`, `.gitignore`, `src/main.lx` e um
`loxia.lock` vazio (para `--frozen`/`lock --check` já funcionarem). Nada de rede e nada
que dependa da máquina além do `git init` opcional.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from loxia_core.loader.gitenv import git_env
from loxia_core.loader.lock import Lock, write_lock

PROJECT_VERSION = "0.1.0"
NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
APP_PATHS = ("loxia.toml", "src/main.lx", ".gitignore")
_GITIGNORE = ".loxia/\ndist/\n"
_MAIN = 'print("hello from {name}")\n'
_LIBRARY = """/// Adds two integers.\nfn add(a: Int, b: Int) -> Int {\n  return a + b\n}\n"""
_MANIFEST = '[package]\nname = "{name}"\nversion = "{version}"\n'


class ScaffoldError(Exception):
    """Falha ao criar/inicializar o projeto; mensagem pronta para o diagnóstico."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class Project:
    path: Path
    name: str
    git_initialized: bool
    files: tuple[str, ...]


def default_name(directory: Path) -> str:
    """Nome do pacote a partir do diretório: `my-app` → `my_app` (identificador ASCII)."""
    raw = directory.resolve().name
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", raw)
    if not cleaned:
        cleaned = "app"
    if cleaned[0].isdigit():
        cleaned = f"app_{cleaned}"
    return cleaned


def validate_name(name: str) -> str:
    if not NAME_PATTERN.match(name):
        raise ScaffoldError(
            f"Invalid project name '{name}'; use an ASCII identifier "
            "(letters, digits and `_`, not starting with a digit)."
        )
    return name


def template_paths(package: str, *, library: bool) -> tuple[str, ...]:
    """Arquivos do template: app em `src/main.lx`, lib no módulo raiz `<package>.lx`."""
    if library:
        return ("loxia.toml", f"{package}.lx", ".gitignore")
    return APP_PATHS


def create(
    target: Path,
    *,
    name: str | None = None,
    git: bool = True,
    require_new: bool = True,
    library: bool = False,
) -> Project:
    """Cria (`new`) ou inicializa (`init`) o projeto; nunca sobrescreve arquivo."""
    target = Path(target)
    if require_new:
        if target.exists():
            raise ScaffoldError(
                "Destination already exists; use `loxia init` for an existing directory."
            )
        try:
            target.mkdir(parents=True, exist_ok=False)
        except OSError:
            raise ScaffoldError("Can't create the project directory.") from None
    else:
        if not target.exists():
            raise ScaffoldError("Directory does not exist.")
        if not target.is_dir():
            raise ScaffoldError("Not a directory.")

    package = validate_name(name) if name is not None else default_name(target)
    paths = template_paths(package, library=library)
    if not require_new:
        conflicts = [relative for relative in paths if (target / relative).exists()]
        if conflicts:
            raise ScaffoldError(
                "Directory already contains " + ", ".join(f"'{item}'" for item in conflicts) + "."
            )
    created_root = require_new
    initialized = False
    try:
        if git and not _inside_repository(target):
            _git_init(target)
            initialized = True
        (target / "loxia.toml").write_text(
            _MANIFEST.format(name=package, version=PROJECT_VERSION),
            encoding="utf-8",
            newline="\n",
        )
        if library:
            (target / f"{package}.lx").write_text(_LIBRARY, encoding="utf-8", newline="\n")
        else:
            (target / "src").mkdir(exist_ok=True)
            (target / "src" / "main.lx").write_text(
                _MAIN.format(name=package),
                encoding="utf-8",
                newline="\n",
            )
        (target / ".gitignore").write_text(_GITIGNORE, encoding="utf-8", newline="\n")
        write_lock(target / "loxia.lock", Lock())
    except ScaffoldError:
        if created_root:
            shutil.rmtree(target, ignore_errors=True)
        raise
    except OSError:
        if created_root:
            shutil.rmtree(target, ignore_errors=True)
        raise ScaffoldError("Can't write the project files.") from None
    files = (*paths, "loxia.lock")
    return Project(target, package, initialized, files)


def _inside_repository(path: Path) -> bool:
    """Não criar repositório aninhado quando já existe um `.git` acima."""
    for candidate in (path.resolve(), *path.resolve().parents):
        if (candidate / ".git").exists():
            return True
    return False


def _git_init(target: Path) -> None:
    if shutil.which("git") is None:
        raise ScaffoldError("git was not found in PATH; use --no-git to skip the repository.")
    try:
        result = subprocess.run(
            ["git", "init", "-q", str(target)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=git_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ScaffoldError("Can't initialize the git repository.") from None
    if result.returncode != 0:
        raise ScaffoldError("Can't initialize the git repository.")
