# SPDX-License-Identifier: MIT OR Apache-2.0
"""Ponto de entrada do CLI: escolhe subcomando ou modo compatível e despacha.

A superfície (comandos e opções) mora em `loxia.cli_args`, a execução em
`loxia.cli_commands` e a engine em `loxia.engine`. Este módulo só liga os três.
"""

import sys

from loxia.cli_args import (
    COMMANDS,
    _build_subcommand_parser,
    _validate_legacy,
    build_parser,
)
from loxia.cli_commands import (
    HANDLERS,
    make_loxia,
    run_build,
    run_source,
    watch_check,
)


def _main_subcommand(command: str, argv: list[str]) -> None:
    parser = _build_subcommand_parser(command)
    args = parser.parse_args(argv)
    HANDLERS[command](args, parser)


def _main_legacy(argv: list[str]) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_legacy(args, parser)
    lox = make_loxia(args)

    if args.watch:
        watch_check(lox, args)
    elif args.stdin:
        run_source(
            lox,
            args,
            command="ast" if args.dump_ast else "check" if args.check else "run",
        )
    elif args.script:
        if args.dump_ast or args.check or args.emit:
            if args.emit is not None:
                run_build(lox, args)
            else:
                run_source(lox, args, command="ast" if args.dump_ast else "check")
        else:
            run_source(lox, args, command="run")
    else:
        lox.run_prompt()


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] in COMMANDS:
        _main_subcommand(argv[0], argv[1:])
    else:
        _main_legacy(argv)


if __name__ == "__main__":
    main()
