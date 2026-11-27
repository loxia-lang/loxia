# SPDX-License-Identifier: MIT OR Apache-2.0
"""Superfície do CLI: comandos, opções do argparse e validação de combinações.

Concentra a árvore de parsers (topo no modo compatível + um por subcomando) e as regras de
"flag X exige/recusa Y". Não executa nada: quem roda é `loxia.cli_commands` e quem
despacha é `loxia.cli`.

O `--help` do topo é **curado**: mostra só os comandos e as opções globais; as flags
históricas do modo compatível ficam fora da lista de opções e aparecem resumidas no
epílogo (`_compat_epilog`). Cada subcomando documenta as suas próprias flags, agrupadas.
"""

import argparse
import signal
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from loxia import __version__
from loxia_core.execution.limits import (
    DEFAULT_HEAP_BYTES,
    MAX_HEAP_BYTES,
    MIN_HEAP_BYTES,
)

COMMANDS = (
    "run",
    "repl",
    "new",
    "init",
    "add",
    "remove",
    "check",
    "build",
    "ast",
    "fmt",
    "doc",
    "explain",
    "capabilities",
    "cache",
    "lsp",
    "mcp",
    "test",
    "fix",
    "lock",
    "fetch",
)

_COMMAND_SUMMARIES = {
    "run": "executa um script Loxia",
    "repl": "abre uma sessão interativa (padrão sem arquivo)",
    "new": "cria um projeto novo (loxia.toml, src/main.lx, lock, git)",
    "init": "inicializa um projeto num diretório existente",
    "add": "adiciona uma dependência ao loxia.toml",
    "remove": "remove uma dependência do loxia.toml",
    "check": "checa os tipos sem executar",
    "build": "compila para código nativo (LLVM)",
    "ast": "imprime a AST como S-expression, sem executar",
    "fmt": "formata arquivos ou diretórios Loxia",
    "doc": "gera referência Markdown/JSON dos comentários `///`",
    "explain": "explica um código de diagnóstico",
    "capabilities": "descreve comandos, formatos e limites",
    "cache": "inspeciona/limpa o cache de binários nativos",
    "lsp": "servidor de linguagem (LSP) sobre stdio",
    "mcp": "servidor MCP (Model Context Protocol) sobre stdio",
    "test": "roda suítes `*_test.lx`",
    "fix": "aplica correções seguras (dry-run por padrão)",
    "lock": "escreve `loxia.lock` a partir do `loxia.toml`",
    "fetch": "materializa/verifica as dependências travadas",
}

_COMMAND_EXAMPLES = {
    "run": """exemplos:
  loxia run examples/fib.lx
  loxia run --stdin --file-name demo.lx < demo.lx
  loxia run --stdin -- --verbose --output=out.txt < demo.lx
  loxia run prog.lx -- --verbose""",
    "check": """exemplos:
  loxia check src/main.lx
  loxia check --watch src/main.lx
  loxia check --stdin < prog.lx""",
    "build": """exemplos:
  loxia build prog.lx --emit=ll
  loxia build prog.lx --emit=exe -o app
  loxia build prog.lx --emit=exe --max-heap=256M -o app""",
    "ast": """exemplos:
  loxia ast prog.lx""",
    "fmt": """exemplos:
  loxia fmt src examples
  loxia fmt --check std tests/cases --exclude 'tests/cases/errors/**'
  loxia fmt --stdin < prog.lx""",
    "doc": """exemplos:
  loxia doc src/main.lx
  loxia doc --json src/main.lx""",
    "new": """exemplos:
  loxia new hello
  loxia new hello --name hello_world --no-git
  loxia new minha-lib --lib""",
    "init": """exemplos:
  loxia init
  loxia init meu-projeto
  loxia init --lib""",
    "add": """exemplos:
  loxia add acme --path ../acme
  loxia add acme --git https://github.com/acme/acme --rev v1.2.3 --lock
  loxia add acme --path ../acme --dry-run""",
    "remove": """exemplos:
  loxia remove acme
  loxia remove acme --dry-run --json""",
    "lock": """exemplos:
  loxia lock
  loxia lock --check""",
    "fetch": """exemplos:
  loxia fetch
  loxia fetch --offline""",
    "test": """exemplos:
  loxia test
  loxia test tests/ --filter fib --jobs 4""",
    "fix": """exemplos:
  loxia fix src/main.lx
  loxia fix src/main.lx --apply""",
    "cache": """exemplos:
  loxia cache path
  loxia cache prune --max-size 512M
  loxia cache prune --dry-run --json""",
}

_HEAP_SUFFIXES = {"k": 1024, "m": 1024**2, "g": 1024**3}


@dataclass(frozen=True)
class _Groups:
    """Grupos de opções de um subcomando (a ordem de criação é a ordem no `--help`)."""

    general: argparse._ArgumentGroup
    selection: argparse._ArgumentGroup
    input: argparse._ArgumentGroup
    build: argparse._ArgumentGroup
    execution: argparse._ArgumentGroup
    diagnostics: argparse._ArgumentGroup
    modules: argparse._ArgumentGroup
    project: argparse._ArgumentGroup


def parse_heap_size(text: str) -> int:
    """Interpreta `512M`, `2G` ou bytes puros; devolve o valor validado."""
    value = text.strip().lower()
    multiplier = 1
    if value and value[-1] in _HEAP_SUFFIXES:
        multiplier = _HEAP_SUFFIXES[value[-1]]
        value = value[:-1]
    try:
        number = int(value, 10)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid heap size '{text}' (use bytes, K, M or G)"
        ) from None
    size = number * multiplier
    if not MIN_HEAP_BYTES <= size <= MAX_HEAP_BYTES:
        raise argparse.ArgumentTypeError(
            f"heap size must be between {MIN_HEAP_BYTES // 1024**2}M "
            f"and {MAX_HEAP_BYTES // 1024**3}G"
        )
    return size


def _parse_cache_size(text: str) -> int:
    """Tamanho do cache (`512M`, `2G`) — mesma sintaxe do `--max-heap`."""
    from loxia.native_cache import parse_size

    try:
        return parse_size(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from None


class _ErrorFormatAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        assert isinstance(values, str)
        setattr(namespace, self.dest, values)
        namespace.error_format_explicit = True


# -- opções compartilhadas ---------------------------------------------------


def _add_diagnostics_options(container: argparse._ActionsContainer) -> None:
    container.add_argument(
        "--error-format",
        choices=("human", "short", "json"),
        default="human",
        action=_ErrorFormatAction,
        help="formato dos diagnósticos (human: trecho+caret; short: uma linha; json)",
    )
    container.add_argument(
        "--json",
        action="store_true",
        help="alias de --error-format=json",
    )
    container.add_argument(
        "--json-lines",
        action="store_true",
        help="um objeto JSON por linha (start/diagnostic/summary)",
    )
    container.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="cor nos diagnósticos humanos (auto: só em TTY, respeita NO_COLOR)",
    )
    container.add_argument(
        "--max-errors",
        type=int,
        default=20,
        metavar="N",
        help="limite de diagnósticos por execução (0 = sem limite)",
    )
    container.add_argument(
        "--no-progress",
        action="store_true",
        help="desliga progresso (aceito por compatibilidade; hoje é no-op)",
    )
    container.add_argument(
        "-Werror",
        dest="werror",
        action="store_true",
        help="trata warnings como erros (só tem efeito em check/build)",
    )
    container.set_defaults(error_format_explicit=False)


def _add_module_options(container: argparse._ActionsContainer) -> None:
    container.add_argument(
        "--module-path",
        action="append",
        default=[],
        metavar="DIR",
        help=(
            "raiz adicional de módulos, relativa ao CWD (repetível; "
            "ordem de precedência depois do manifest)"
        ),
    )


def _add_dependency_options(
    container: argparse._ActionsContainer,
    *,
    frozen: bool = True,
    cache: bool = True,
) -> None:
    if frozen:
        container.add_argument(
            "--frozen",
            action="store_true",
            help="resolve só pelo loxia.lock; falha se manifest ou conteúdo divergirem",
        )
    container.add_argument(
        "--offline",
        action="store_true",
        help="nunca acessa a rede (dependências git só do cache)",
    )
    if cache:
        container.add_argument(
            "--cache-dir",
            metavar="DIR",
            help="cache de dependências (default: .loxia/cache na raiz do projeto)",
        )


def _add_input_options(container: argparse._ActionsContainer) -> None:
    container.add_argument(
        "--stdin",
        action="store_true",
        help="lê o programa de stdin em vez de um arquivo",
    )
    container.add_argument(
        "--file-name",
        metavar="NOME",
        help="nome de exibição/raiz de módulos quando --stdin (default: <stdin>)",
    )


def _add_debug(container: argparse._ActionsContainer) -> None:
    container.add_argument(
        "--debug",
        action="store_true",
        help="checa overflow de Int em runtime (release faz wrapping)",
    )


def _add_sandbox(container: argparse._ActionsContainer) -> None:
    container.add_argument(
        "--sandbox",
        action="store_true",
        help="nega fs/process ambientais ao programa (run)",
    )


def _add_timeout(container: argparse._ActionsContainer) -> None:
    container.add_argument(
        "--timeout",
        type=int,
        metavar="MS",
        help=(
            "tempo limite em milissegundos (0 = sem limite); no run AOT cobre a "
            "execução do binário, não o build"
        ),
    )


def _add_watch(container: argparse._ActionsContainer) -> None:
    container.add_argument(
        "--watch",
        action="store_true",
        help="recheca o arquivo e os módulos a cada mudança",
    )


def _add_build_options(container: argparse._ActionsContainer, *, default_emit: bool) -> None:
    if default_emit:
        container.add_argument(
            "--emit",
            choices=("ll", "obj", "exe"),
            default="exe",
            help="tipo de saída (default: exe)",
        )
    else:
        container.add_argument(
            "--emit",
            choices=("ll", "obj", "exe"),
            help="compila para código nativo (ll: IR textual, obj: .o, exe: binário)",
        )
    container.add_argument("-o", "--output", help="caminho de saída do build")
    container.add_argument(
        "--max-heap",
        type=parse_heap_size,
        metavar="SIZE",
        help=(
            "teto de heap do binário nativo (default: "
            f"{DEFAULT_HEAP_BYTES // 1024**2}M; ex.: 512M, 2G); só com --emit=exe"
        ),
    )


def _add_edit_options(container: argparse._ActionsContainer) -> None:
    container.add_argument(
        "--dry-run",
        action="store_true",
        help="não escreve; imprime o diff do manifest",
    )
    container.add_argument(
        "--lock",
        action="store_true",
        help="roda `loxia lock` depois de editar (pode acessar a rede)",
    )


def _add_scaffold_options(container: argparse._ActionsContainer) -> None:
    container.add_argument(
        "--name",
        metavar="NOME",
        help="nome do pacote (default: nome do diretório, normalizado para identificador)",
    )
    container.add_argument(
        "--no-git",
        action="store_true",
        help="não inicializa um repositório git no projeto",
    )
    container.add_argument(
        "--lib",
        action="store_true",
        help="cria uma biblioteca (módulo <nome>.lx na raiz, sem src/main.lx)",
    )


def _option_groups(parser: argparse.ArgumentParser) -> _Groups:
    return _Groups(
        general=parser.add_argument_group("opções gerais"),
        selection=parser.add_argument_group("seleção"),
        input=parser.add_argument_group("entrada"),
        build=parser.add_argument_group("saída do build"),
        execution=parser.add_argument_group("execução"),
        diagnostics=parser.add_argument_group("diagnóstico"),
        modules=parser.add_argument_group("módulos e dependências"),
        project=parser.add_argument_group("projeto"),
    )


def _top_level_description() -> str:
    width = max(len(command) for command in COMMANDS)
    lines = [
        "Loxia: interpretador tree-walk com backend LLVM opcional.",
        "",
        "comandos:",
    ]
    lines.extend(f"  {command.ljust(width)}  {_COMMAND_SUMMARIES[command]}" for command in COMMANDS)
    lines.extend(
        [
            "",
            "Use 'loxia <comando> --help' para as opções e exemplos do comando.",
        ]
    )
    return "\n".join(lines)


def _compat_epilog(parser: argparse.ArgumentParser) -> str:
    """Resume o modo compatível sem repetir a lista de opções do topo."""
    flags = [
        "/".join(action.option_strings)
        for action in parser._actions
        if action.option_strings and action.dest not in {"help", "version"}
    ]
    note = (
        "modo compatível:\n"
        "  'loxia [opções] script.lx' continua aceito e equivale ao subcomando\n"
        "  correspondente (--check → check, --dump-ast → ast, --emit → build).\n"
        "  Flags aceitas neste modo:\n"
    )
    return note + textwrap.fill(
        ", ".join(flags),
        width=78,
        initial_indent="    ",
        subsequent_indent="    ",
    )


def build_parser() -> argparse.ArgumentParser:
    """Parser do modo compatível; o `--help` do topo lista comandos, não flags.

    As opções históricas continuam aceitas e validadas (`_validate_legacy`), mas ficam
    fora da lista de opções do help: cada uma foi migrada para o `--help` do subcomando
    equivalente. O epílogo resume o que ainda vale neste modo.
    """
    parser = argparse.ArgumentParser(
        prog="loxia",
        usage=("loxia <comando> [opções]\n       loxia [opções] [script]  (modo compatível)"),
        description=_top_level_description(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    globals_group = parser.add_argument_group("opções globais")
    globals_group.add_argument("-h", "--help", action="help", help="mostra esta ajuda e sai")
    globals_group.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="mostra a versão e sai",
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dump-ast",
        action="store_true",
        help="imprime a AST do script (S-expression) e não executa",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="checa os tipos do script e não executa",
    )
    mode.add_argument(
        "--emit",
        choices=("ll", "obj", "exe"),
        help="compila para código nativo (ll: IR textual, obj: .o, exe: binário)",
    )
    parser.add_argument(
        "--gradual",
        action="store_true",
        help="com --check: anotação ausente vira aviso (tipo Any)",
    )
    parser.add_argument(
        "--file-only",
        action="store_true",
        help="com --dump-ast: transforma só o arquivo, sem loader/mangling",
    )
    parser.add_argument(
        "--format",
        choices=("sexp", "json"),
        default="sexp",
        help="com --dump-ast: S-expression (padrão) ou JSON (exige --file-only)",
    )
    parser.add_argument(
        "--allow-errors",
        action="store_true",
        help="com --dump-ast --file-only: emite a árvore recuperada; exit 65",
    )
    parser.add_argument(
        "--typed",
        action="store_true",
        help="com --dump-ast --format=json: inclui o overlay de tipos do checker",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="caminho de saída do build (padrão: nome do script)",
    )
    parser.add_argument(
        "--max-heap",
        type=parse_heap_size,
        metavar="SIZE",
        help=(
            "teto de heap do binário nativo (default: "
            f"{DEFAULT_HEAP_BYTES // 1024**2}M; ex.: 512M, 2G); só com --emit=exe"
        ),
    )
    parser.add_argument(
        "--interpret",
        action="store_true",
        help="executa no tree-walk em vez de compilar (equivalente a 'run --interpret')",
    )
    _add_diagnostics_options(parser)
    _add_module_options(parser)
    _add_input_options(parser)
    _add_debug(parser)
    _add_timeout(parser)
    _add_watch(parser)
    parser.add_argument(
        "script",
        nargs="?",
        help="script Loxia (equivale a 'loxia run script.lx')",
    )
    parser.add_argument(
        "script_args",
        nargs=argparse.REMAINDER,
        help="argumentos repassados para o programa (args())",
    )

    # O help do topo é o índice dos comandos; as flags históricas continuam parseáveis
    # mas aparecem só no epílogo de compatibilidade (sem lista de opções gigante).
    for action in parser._actions:
        if action.option_strings and action.dest not in {"help", "version"}:
            action.help = argparse.SUPPRESS
    parser.epilog = _compat_epilog(parser)
    return parser


def _build_subcommand_parser(command: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=f"loxia {command}",
        description=_COMMAND_SUMMARIES[command],
        epilog=_COMMAND_EXAMPLES.get(command),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    groups = _option_groups(parser)
    groups.general.add_argument("-h", "--help", action="help", help="mostra esta ajuda e sai")

    if command == "run":
        _add_diagnostics_options(groups.diagnostics)
        _add_module_options(groups.modules)
        _add_debug(groups.execution)
        _add_sandbox(groups.execution)
        _add_input_options(groups.input)
        _add_timeout(groups.execution)
        _add_dependency_options(groups.modules)
        groups.execution.add_argument(
            "--interpret",
            action="store_true",
            help=(
                "executa no tree-walk (oráculo/legado) em vez de compilar; "
                "--json, --json-lines, --error-format diferente de human, "
                "--sandbox, --stdin e --color=always já implicam isto"
            ),
        )
        groups.execution.add_argument(
            "--no-cache",
            action="store_true",
            help="força o build nativo; não reusa binário do cache (exige o caminho AOT)",
        )
        groups.execution.add_argument(
            "--max-heap",
            type=parse_heap_size,
            metavar="SIZE",
            help=(
                "teto de heap do binário nativo "
                f"(default: {DEFAULT_HEAP_BYTES // 1024**2}M; ex.: 512M, 2G); "
                "exige AOT"
            ),
        )
        parser.add_argument("script", nargs="?", help="script Loxia")
        parser.add_argument(
            "script_args",
            nargs="*",
            help="argumentos repassados para o programa (use -- antes)",
        )
    elif command == "check":
        _add_diagnostics_options(groups.diagnostics)
        _add_module_options(groups.modules)
        _add_input_options(groups.input)
        _add_timeout(groups.execution)
        _add_watch(groups.execution)
        _add_dependency_options(groups.modules)
        groups.general.add_argument(
            "--gradual",
            action="store_true",
            help="anotação ausente vira aviso (tipo Any) em vez de erro",
        )
        parser.add_argument("script", nargs="?", help="script Loxia")
    elif command == "repl":
        # Sessão interativa (ou stream em pipe): não há arquivo de entrada.
        _add_diagnostics_options(groups.diagnostics)
        _add_module_options(groups.modules)
        _add_debug(groups.execution)
    elif command == "new":
        _add_diagnostics_options(groups.diagnostics)
        _add_module_options(groups.modules)
        _add_scaffold_options(groups.project)
        parser.add_argument("path", help="diretório do projeto (não pode existir)")
    elif command == "init":
        _add_diagnostics_options(groups.diagnostics)
        _add_module_options(groups.modules)
        _add_scaffold_options(groups.project)
        parser.add_argument(
            "path",
            nargs="?",
            default=".",
            help="diretório existente para inicializar (default: .)",
        )
    elif command == "add":
        _add_diagnostics_options(groups.diagnostics)
        _add_module_options(groups.modules)
        _add_dependency_options(groups.modules, frozen=False)
        _add_edit_options(groups.general)
        groups.modules.add_argument(
            "--path",
            metavar="DIR",
            help="dependência local, relativa à pasta do manifest",
        )
        groups.modules.add_argument(
            "--git",
            metavar="URL",
            help="repositório git (exige --rev)",
        )
        groups.modules.add_argument(
            "--rev",
            metavar="REV",
            help="commit completo ou tag (nunca branch)",
        )
        parser.add_argument("name", help="nome da dependência (identificador ASCII)")
    elif command == "remove":
        _add_diagnostics_options(groups.diagnostics)
        _add_module_options(groups.modules)
        _add_dependency_options(groups.modules, frozen=False)
        _add_edit_options(groups.general)
        parser.add_argument("name", help="nome da dependência declarada")
    elif command == "build":
        _add_diagnostics_options(groups.diagnostics)
        _add_module_options(groups.modules)
        _add_build_options(groups.build, default_emit=True)
        _add_dependency_options(groups.modules)
        parser.add_argument("script", help="script Loxia")
    elif command == "ast":
        _add_diagnostics_options(groups.diagnostics)
        _add_module_options(groups.modules)
        _add_input_options(groups.input)
        _add_dependency_options(groups.modules)
        groups.general.add_argument(
            "--file-only",
            action="store_true",
            help="transforma só o arquivo, sem loader, módulos ou mangling",
        )
        groups.general.add_argument(
            "--format",
            choices=("sexp", "json"),
            default="sexp",
            help="S-expression (padrão) ou JSON versionado (exige --file-only)",
        )
        groups.general.add_argument(
            "--allow-errors",
            action="store_true",
            help="com --file-only: emite a árvore recuperada (ErrorStmt/ErrorExpr); exit 65",
        )
        groups.general.add_argument(
            "--typed",
            action="store_true",
            help="com --format=json: inclui o overlay de tipos do checker",
        )
        parser.add_argument("script", nargs="?", help="script Loxia")
    elif command == "fmt":
        _add_diagnostics_options(groups.diagnostics)
        _add_module_options(groups.modules)
        _add_input_options(groups.input)
        groups.general.add_argument(
            "--check",
            action="store_true",
            help="não escreve; exit 1 se mudaria",
        )
        groups.general.add_argument(
            "--max-width",
            type=int,
            default=100,
            metavar="N",
            help="largura máxima do código em colunas (20..1000; padrão 100)",
        )
        groups.general.add_argument(
            "--diff",
            action="store_true",
            help="mostra um diff unificado; não escreve",
        )
        groups.general.add_argument(
            "--edits",
            choices=("json",),
            default=None,
            help="com --check: emite TextEdit[] em JSON; não escreve",
        )
        groups.general.add_argument(
            "--exclude",
            action="append",
            default=[],
            metavar="GLOB",
            help="padrão (relativo ao cwd) a ignorar em diretórios; repetível",
        )
        parser.add_argument(
            "paths",
            nargs="*",
            metavar="PATH",
            help="arquivos ou diretórios .lx; diretórios são recursivos",
        )
    elif command == "doc":
        # `--json` do doc é a referência em JSON, não o formato de erro: por isso as
        # opções de diagnóstico são declaradas à parte em vez de `_add_diagnostics_options`.
        _add_input_options(groups.input)
        parser.add_argument("script", nargs="?", help="arquivo Loxia")
        groups.general.add_argument(
            "--json",
            action="store_true",
            help="referência em JSON (não é o formato dos diagnósticos)",
        )
        groups.diagnostics.add_argument(
            "--error-format",
            choices=("human", "short", "json"),
            default="human",
            action=_ErrorFormatAction,
            help="formato dos diagnósticos",
        )
        groups.diagnostics.add_argument(
            "--color",
            choices=("auto", "always", "never"),
            default="auto",
            help="cor nos diagnósticos",
        )
        groups.diagnostics.add_argument(
            "--max-errors",
            type=int,
            default=20,
            metavar="N",
            help="limite de diagnósticos",
        )
        parser.set_defaults(error_format_explicit=False)
    elif command == "lsp":
        groups.general.add_argument(
            "--stdio",
            action="store_true",
            help="usa stdio (padrão; aceito para compatibilidade)",
        )
    elif command == "mcp":
        # O transporte do MCP é sempre stdio; não há flags de servidor no v1.
        pass
    elif command == "fix":
        parser.add_argument("script", help="arquivo Loxia")
        groups.execution.add_argument(
            "--apply",
            action="store_true",
            help="grava as mudanças (padrão: dry-run)",
        )
        groups.execution.add_argument(
            "--max-iterations",
            type=int,
            default=10,
            metavar="N",
            help="rodadas de fix (default: 10)",
        )
        groups.general.add_argument("--json", action="store_true", help="resumo em JSON")
    elif command == "test":
        parser.add_argument(
            "paths",
            nargs="*",
            help="arquivos ou diretórios (default: tests/ se existir, senão .)",
        )
        groups.selection.add_argument("--filter", metavar="SUB", help="só nomes com SUB")
        groups.selection.add_argument(
            "--only", metavar="NAME", help="só o teste com esse nome exato"
        )
        groups.selection.add_argument(
            "--isolate",
            choices=("file", "test"),
            default="file",
            help="processo por arquivo (default) ou por teste",
        )
        groups.selection.add_argument(
            "--fail-fast", action="store_true", help="para no primeiro arquivo com falha"
        )
        groups.selection.add_argument(
            "--require-tests",
            action="store_true",
            help="exit 5 quando nenhum teste for selecionado (evita falso verde)",
        )
        groups.general.add_argument("--json", action="store_true", help="relatório em JSON")
        groups.general.add_argument(
            "--json-lines",
            action="store_true",
            help="um evento JSON por linha (testes + summary)",
        )
        groups.general.add_argument(
            "--junit",
            metavar="PATH",
            help="grava o relatório JUnit XML no arquivo",
        )
        groups.general.add_argument(
            "--capture",
            action="store_true",
            help="inclui no JSON o stdout do teste que falhou",
        )
        groups.execution.add_argument(
            "--jobs",
            type=int,
            default=None,
            metavar="N",
            help="arquivos em paralelo (default: min(4, CPUs))",
        )
        groups.execution.add_argument(
            "--timeout",
            type=int,
            metavar="MS",
            help="timeout por arquivo em milissegundos",
        )
        groups.execution.add_argument(
            "--changed",
            nargs="?",
            const="HEAD",
            metavar="REF",
            help="só testes afetados por mudanças desde REF (default: HEAD)",
        )
        groups.execution.add_argument(
            "--shard",
            metavar="INDEX/TOTAL",
            help="roda só um shard dos arquivos selecionados (1-based)",
        )
        groups.execution.add_argument(
            "--native",
            action="store_true",
            help="compila cada arquivo e roda o binário",
        )
        groups.execution.add_argument(
            "--no-cache",
            action="store_true",
            help="não reusa binários nativos em cache",
        )
        _add_dependency_options(groups.modules)
    elif command == "lock":
        _add_diagnostics_options(groups.diagnostics)
        _add_module_options(groups.modules)
        groups.general.add_argument(
            "--check",
            action="store_true",
            help="não escreve; exit 1 se o lock estiver desatualizado",
        )
        _add_dependency_options(groups.modules, frozen=False)
    elif command == "fetch":
        _add_diagnostics_options(groups.diagnostics)
        _add_module_options(groups.modules)
        _add_dependency_options(groups.modules, frozen=False)
    elif command == "explain":
        parser.add_argument("code", help="código de diagnóstico (ex.: E2001)")
        groups.general.add_argument("--json", action="store_true", help="saída JSON")
    elif command == "capabilities":
        groups.general.add_argument("--json", action="store_true", help="saída JSON")
    elif command == "cache":
        parser.add_argument(
            "action",
            choices=("path", "prune"),
            help="path: raiz do cache; prune: remove binários antigos até o limite",
        )
        groups.general.add_argument(
            "--max-size",
            type=_parse_cache_size,
            metavar="SIZE",
            help="limite total do cache (default: 1G ou $LOX_BUILD_CACHE_MAX)",
        )
        groups.general.add_argument(
            "--dry-run",
            action="store_true",
            help="não apaga; só relata o que sairia",
        )
        groups.general.add_argument("--json", action="store_true", help="saída JSON")
    else:  # pragma: no cover - guarda de programação
        raise AssertionError(f"unknown command {command}")
    return parser


def _shift_stdin_args(args: argparse.Namespace) -> None:
    """`run --stdin -- a b`: the first positional is a program argument, not a script.

    `argparse` cannot know that `--stdin` removes the `script` positional, so it puts
    the first program argument in `args.script`. Move it (and the remainder) to
    `script_args`, which is what the engine exposes through `args()`.
    """
    script = getattr(args, "script", None)
    if not script:
        return
    args.script_args = [script, *getattr(args, "script_args", [])]
    args.script = None


def _validate(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    *,
    command: str,
) -> None:
    args.stdin = getattr(args, "stdin", False)
    args.file_name = getattr(args, "file_name", None)
    args.timeout = getattr(args, "timeout", None)
    args.watch = getattr(args, "watch", False)
    args.frozen = getattr(args, "frozen", False)
    args.offline = getattr(args, "offline", False)
    args.cache_dir = getattr(args, "cache_dir", None)
    if args.json_lines and args.error_format_explicit:
        parser.error("--json-lines cannot be combined with --error-format")
    if args.max_errors < 0:
        parser.error("--max-errors must be non-negative")
    if args.timeout is not None and args.timeout < 0:
        parser.error("--timeout must be non-negative")
    if args.timeout and not hasattr(signal, "setitimer"):
        parser.error("--timeout is not supported on this platform")
    if args.timeout and command not in {"run", "check"}:
        parser.error("--timeout is only supported by run/check")
    if args.timeout and getattr(args, "watch", False):
        parser.error("--timeout cannot be combined with --watch")
    if getattr(args, "watch", False) and command != "check":
        parser.error("--watch is only supported by check")
    if getattr(args, "watch", False) and args.stdin:
        parser.error("--watch cannot be combined with --stdin")
    if args.stdin and getattr(args, "script", None):
        if command == "run":
            _shift_stdin_args(args)
        else:
            parser.error("--stdin cannot be combined with a script")
    if args.file_name is not None and not args.stdin:
        parser.error("--file-name requires --stdin")
    ast_format = getattr(args, "format", "sexp")
    file_only = getattr(args, "file_only", False)
    if command == "ast":
        if getattr(args, "allow_errors", False) and not file_only:
            parser.error("--allow-errors requires --file-only")
        if getattr(args, "typed", False) and ast_format != "json":
            parser.error("--typed requires --format=json")
        if getattr(args, "typed", False) and not file_only:
            parser.error("--typed requires --file-only")
        if getattr(args, "typed", False) and getattr(args, "allow_errors", False):
            parser.error("--typed cannot be combined with --allow-errors")
        if ast_format == "json" and not file_only:
            parser.error("--format=json requires --file-only")
    elif file_only or ast_format != "sexp":
        parser.error("--file-only/--format are only supported by ast")
    if command in {"run", "check", "ast"} and not args.stdin and not args.script:
        parser.error(f"{command} requires a script (or --stdin)")
    if command == "run":
        native_blockers = (
            getattr(args, "interpret", False)
            or args.stdin
            or getattr(args, "sandbox", False)
            or getattr(args, "json", False)
            or getattr(args, "json_lines", False)
            or args.error_format != "human"
            or getattr(args, "color", "auto") == "always"
        )
        if native_blockers:
            reason = (
                "--interpret, --json, --json-lines, --error-format other than human, "
                "--sandbox, --stdin and --color=always run on the tree-walk"
            )
            if getattr(args, "max_heap", None) is not None:
                parser.error(f"--max-heap requires the native path ({reason})")
            if getattr(args, "no_cache", False):
                parser.error(f"--no-cache requires the native path ({reason})")
    if command == "build":
        if args.stdin:
            parser.error("build does not support --stdin yet")
        if args.max_heap is not None and args.emit != "exe":
            parser.error("--max-heap requires --emit=exe")


def _validate_legacy(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.json_lines and args.error_format_explicit:
        parser.error("--json-lines cannot be combined with --error-format")
    if args.max_errors < 0:
        parser.error("--max-errors must be non-negative")
    if args.timeout is not None and args.timeout < 0:
        parser.error("--timeout must be non-negative")
    if args.timeout and not hasattr(signal, "setitimer"):
        parser.error("--timeout is not supported on this platform")
    if args.timeout and (args.dump_ast or args.emit):
        parser.error("--timeout is only supported by run/check")
    if args.watch and not args.check:
        parser.error("--watch requires --check")
    if args.gradual and not args.check:
        parser.error("--gradual requires --check")
    if args.interpret and (args.check or args.dump_ast or args.emit):
        parser.error("--interpret is only supported by run")
    if args.watch and args.stdin:
        parser.error("--watch cannot be combined with --stdin")
    if args.watch and not args.script:
        parser.error("--watch requires a script")
    if args.watch and args.timeout:
        parser.error("--timeout cannot be combined with --watch")
    if args.file_only and not args.dump_ast:
        parser.error("--file-only requires --dump-ast")
    if args.format != "sexp" and not args.dump_ast:
        parser.error("--format is only supported with --dump-ast")
    if args.allow_errors and not args.file_only:
        parser.error("--allow-errors requires --file-only")
    if args.typed and args.format != "json":
        parser.error("--typed requires --format=json")
    if args.typed and not args.file_only:
        parser.error("--typed requires --file-only")
    if args.typed and args.allow_errors:
        parser.error("--typed cannot be combined with --allow-errors")
    if args.format == "json" and not args.file_only:
        parser.error("--format=json requires --file-only")
    if args.stdin and args.script:
        if args.dump_ast or args.check or args.emit:
            parser.error("--stdin cannot be combined with a script")
        _shift_stdin_args(args)
    if args.file_name is not None and not args.stdin:
        parser.error("--file-name requires --stdin")
    if (args.dump_ast or args.check or args.emit) and not (args.script or args.stdin):
        parser.error("--dump-ast/--check/--emit requires a script")
    if args.emit and args.stdin:
        parser.error("--stdin cannot be used with --emit")
    if args.output and not args.emit:
        parser.error("-o/--output requires --emit")
    if args.max_heap is not None and args.emit != "exe":
        parser.error("--max-heap requires --emit=exe")
    if not args.script and not args.stdin:
        if args.json_lines:
            parser.error("--json-lines requires a script or --stdin")
        if args.timeout:
            parser.error("--timeout requires a script or --stdin")
