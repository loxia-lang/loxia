---
name: lox-testing
description: Como escrever, rodar e organizar testes neste repositório — casos golden .lx com expectativas, exit codes do CLI e testes unitários em pytest.
whenToUse: Ao adicionar um teste, fazer a suíte passar, investigar uma falha ou transformar um bug em caso de regressão.
---

# Testes

## Comandos

```bash
make test                          # pytest (unit + golden)
make test-fast                     # sem backend/install, xdist (~15-20 s)
make test-fast TEST_JOBS=0         # serial (depurar um caso)
make test-backend                  # backend sem os casos lentos (Rust), xdist (~12 s)
make test-backend TEST_JOBS=0      # backend serial (depurar um caso)
make test-backend-all              # backend completo, incluindo os casos lentos
make smoke-backend                 # um caso por nível, processo real (~5 s)
uv run pytest -k block             # subconjunto
make case                          # runner golden sem pytest
uv run python -m tests.runner for  # um caso (filtro por substring)
```

O runner golden, a suíte oficial e o corpus diferencial executam o CLI **no processo
do pytest** (`tests/inprocess.py`); `LOX_GOLDEN_SUBPROCESS=1` volta ao processo por caso.
Use `subprocess` só quando o teste precisa de processo real (hash seed, sinal/timeout,
stdin de REPL, sandbox, `std.proc`, binário compilado, oráculo de regex nativo). Casos
com o crate Rust são `slow`: ficam fora de `make test-backend` e rodam no gate e no CI.

## Caso golden (`tests/cases/*.lx`)

O próprio `.lx` carrega a expectativa em comentário:

```lox
print 1 + 2;                          # expect: 3
print naoexiste;
# expect runtime error: Undefined variable 'naoexiste'.
```

Marcadores aceitos (qualquer posição; a ordem das linhas `# expect:` é a ordem
esperada do stdout):

| Marcador | Efeito |
|---|---|
| `# expect: X` | linha de stdout esperada |
| `# expect runtime error: MSG` | stderr contém MSG; exit **70** |
| `# expect error: MSG` | erro de sintaxe/resolução; exit **65** |
| `# expect exit: N` | exit code explícito |

Exit codes do CLI: 65 sintaxe, 70 runtime, 66 arquivo não encontrado.
Se não houver marcador de erro, o teste exige stdout idêntico, stderr vazio e exit 0.

## Regra de ouro

Todo bug corrigido vira caso em `tests/cases/` **no mesmo commit**. Se o caso já
existia, ele falhou antes do fix — cite isso na mensagem de commit.

## Testes unitários (`tests/test_*.py`)

- Não existe mais estado global de erro: cada `Lox.run` cria seu `ErrorReporter`. Em
  teste, inspecione `lox.reporter` / `scanner.reporter` / `parser.reporter`.
- Scanner/parser: prefira helpers pequenos (`scan`, `parse`, `ast`) a duplicar setup.
- Interpreter: `run(source, capsys)` captura stdout/stderr; não use `print` no teste.
- Para AST, compare com `AstPrinter` — é o snapshot canônico da árvore.

## Suíte oficial do livro

`tests/official/cases/` guarda os testes oficiais dos caps. 10–13 sem alteração;
`tests/test_official_suite.py` adapta (`fun`→`fn`, `//`→`#`, `class B < A`→`class B(A)`,
campos `this.x` declarados) e roda pelo CLI. 112 passam e 8 são `xfail` documentados
(campos dinâmicos do ADR-0009 e o teste de sintaxe antiga de superclasse). Rode com
`uv run pytest tests/test_official_suite.py -q`.

## Corpus diferencial (I1)

O I1 vale para o **corpus anotado e classificado**, nunca para o que o backend "quase"
faz ([ADR-0031](../../../docs/adr/0031-backend-nativo.md),
[ADR-0064](../../../docs/adr/0064-orcamento-do-corpus.md)). Todo caso está em `LEVELS`,
`PENDING` ou `NEGATIVE` ([`tests/corpus_manifest.py`](../../../tests/corpus_manifest.py)):

- **Promover** um caso = mover de `PENDING` para `LEVELS` no mesmo commit, com o teste
  diferencial verde nos três canais (stdout, stderr e exit code).
- **`PENDING` ≤ 5%** do corpus, sempre com nível e motivo; `l?` é proibido. Caso novo sem
  backend espera em issue/branch em vez de inflar `PENDING`.
- O status (quantos compilam, quantos em `PENDING`) é **gerado** em
  [`docs/spec/garantias.md`](../../../docs/spec/garantias.md); não copie números para o
  roadmap.

```bash
uv sync --extra llvm
uv run pytest tests/test_backend.py -q
```

No CI o `libgc-dev` é a fonte da verdade. Nesta máquina, sem o header `gc.h`, use o shim
local descrito no `AGENTS.md` §4.

## Armadilhas

- O runner procura `#` em **qualquer** posição da linha (expectativa no fim da
  linha, como no livro). Comentário com `#` dentro de string ainda funciona?
  Evite: pode ser confundido com expectativa.
- Números são `Int`/`Float`: `print 3` sai `3` e `print 3.0` sai `3.0`.
- Teste de REPL usa `Parser(tokens, repl=True)`; sem isso o `;` é obrigatório.
- Não "conserte" a expectativa para o teste passar. Se o comportamento está errado,
  o código está errado.
