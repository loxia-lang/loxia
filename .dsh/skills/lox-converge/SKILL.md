---
name: lox-converge
description: Auditoria de convergência pós-feature — confere se tudo o que o PR/issue/ADR prometeu foi implementado, testado, documentado e policiado, e caça bugs no raio de explosão da mudança.
whenToUse: Ao terminar uma feature ou fix, antes de abrir ou mergear o PR, ou quando alguém perguntar "ficou tudo?". Não use para decidir design (isso é ADR/`lox-syntax`).
---

# Convergência pós-feature

O diff prova o que mudou. Ele **não** prova o que faltou. A pergunta desta skill é
**"o que foi prometido?"**, não "o que foi escrito?".

Ela roda em **contexto limpo** (subagente sem a conversa de implementação): quem escreveu
o diff não é quem audita. Ver §7.

## 0. Congele o contrato

Fontes, nesta ordem: descrição do PR/issue → ADR/spec tocados → commits da branch → o que o
**tipo** de mudança implica (tabela do §2).

```bash
git log --oneline dev..HEAD
git diff dev...HEAD --stat
gh pr view <n> --json title,body,files
```

Saída: `C1..Cn`, cada um **uma frase verificável** — "`readU32be` devolve `nil` quando não
cabem 4 bytes", não "implementar decoders". Promessa vaga é pergunta para o autor, não item
de checklist.

## 1. Matriz de convergência

Uma linha por promessa. Sem evidência, não conta.

| # | promessa | implementado | testado | documentado | gate | estado |
|---|---|---|---|---|---|---|
| C1 | `readU32be` → `nil` se faltar byte | `std/bytes.lx:198` | `tests/cases/std_bytes.lx` | `docs/stdlib/bytes.md` | t2 diferencial | ok |
| C2 | `fs.readBytes` preserva prefixo UTF-8 | `fs_runtime.py` | `test_fs_runtime.py` | `docs/stdlib/fs.md` | nativo | ok |
| C3 | builder nativo | — | — | — | — | fora (ADR-0125) |

Regras:

- **"não achei" exige prova**: grep pelo nome, leitura do arquivo, `git log -S`. Ausência
  não se declara de memória.
- **"existe teste" ≠ "o teste cobre a promessa"**: abra o caso e veja se ele falharia se a
  feature sumisse.
- **fora de escopo declarado** é estado válido — mas tem que estar declarado (ADR, issue,
  corpo do PR), não inferido.
- Estado final por promessa: `ok` / `parcial` / `ausente` / `fora`.

## 2. Raio de explosão

A mudança contamina vizinhos. Percorra a coluna do que você tocou:

| tocou | confira também |
|---|---|
| token/keyword | `frontend/keywords.py`, `make grammar`, `tests/test_editor_grammar.py`, completion do LSP |
| nó de AST | `parser`, `ast_printer`, `resolver`, `checker`, `interpreter`, `backend/lower*`, `loxia/formatter.py`, `loxia/symbols.py` |
| precedência/operador | AST (`--dump-ast`), parênteses do formatter, `docs/spec/sintaxe.md` |
| tipo/`Ty` novo | checker, `backend/lower_model.py`, narrowing, hover do LSP, `TIPOS.md` |
| valor novo (Bytes, Enum…) | `stringify`, `==`/`is`/`as`/`for-in`/`len`, truthiness no backend, tag + struct no runtime C, `loxia/builtins_docs.py`, std docs |
| builtin/nativo | `prelude.py`, checker, interpreter, backend, `builtins_docs`, `docs/stdlib/` |
| campo/`init`/herança | resolver, checker, layout/vtable, `super`, `is` |
| CLI/flag | `cli_args.py`, `tests/test_docs_consistency.py`, completion, MCP/`server.json`, site |
| runtime C | `runtime/gen_kernel.py`/`kernel_gen.h`, chamadas no backend, determinismo, `-m backend` |
| semântica observável | `docs/spec/`, ADR, golden case, `LEVELS`/`PENDING` (≤5%), `garantias.md` gerado |
| `std/` | `docs/stdlib/<mod>.md` + índice, exemplos, `make stdlib-docs` |

## 3. Caça a bug por classe

Falhas que já custaram caro aqui. Cheque as que o diff encosta:

- **Truthiness/tag nova**: todo valor novo precisa de branch no `_is_truthy` do backend,
  senão `--check` passa e o lowering estoura (foi o caso de `Bytes`).
- **Shadowing de namespace nativo**: `val fs = ...` local não pode continuar baixando como
  namespace embutido. Idem `Int`, `Float`, `math`, `Bytes`.
- **Site de erro**: panic no C e `LoxRuntimeError` no tree-walk têm que apontar a **mesma**
  linha/token (callee × parêntese da chamada; token sintético linha 0 é bug).
- **`read(2)`/host**: erro do SO não é EOF. Só `0` bytes é EOF; `EISDIR` e afins são erro
  estável e igual nos dois motores.
- `bool` como número (`is_number`); `isinstance(True, int)` é `True`.
- nó de AST sem `visit_`/`accept` (mypy strict pega; o dump e o LSP não).
- `depth`/escopo e closures (`for-in` cria ambiente por iteração).
- wrap de `Int` × checagem do `--debug`.
- code point × byte em `String`/`Bytes` (`len`, `chars`, slice).
- narrowing invalidado por atribuição/aliasing.
- determinismo: hash, ordem de `set`/`dict`, path, PID, timestamp (I3).
- exit code: 65 sintaxe/check, 70 runtime; mensagem em inglês.
- **I1**: mesmo programa, mesmos 3 canais (stdout, stderr, exit) nos dois motores.
- **I4**: `--check` limpo nunca vira erro de tipo no `--emit`.
- arquivo **gerado** editado à mão (grammar, `kernel_gen.h`, `_spec/index.json`, docs).

## 4. Reproduza antes de reportar

Achado sem caso mínimo é suspeita, não achado — e as duas listas não se misturam.

```bash
uv run main.py caso.lx
uv run main.py --check caso.lx
uv run main.py --emit=exe -o /tmp/app caso.lx   # se o bug for de lowering
```

## 5. Feche o gate do raio

```bash
make check-fast                    # lint + fmt-check + mypy + pytest (sem nativo)
uv run pytest -m backend -q        # se tocou backend/runtime
make bench                         # se tocou caminho quente (opcional, local)
```

Faltou teste? Escreva agora, no mesmo commit (skill `lox-testing`). Comportamento novo sem
caso golden é lacuna de DoD, não "ressalva".

## 6. Veredito

- **BLOQUEIA** — promessa ausente, bug reproduzido, I1/I3/I4 violado, comportamento novo
  sem teste, gerado editado à mão.
- **RESSALVA** — promessa parcial declarada, doc/ADR pendente com issue, follow-up fora do
  diff.
- **OK** — matriz completa e evidência em cada linha.

Toda saída termina com **"não verificado"** (o que você não abriu nem rodou) e cada achado
segue o formato: *o que o código faz / o que quebra / o fix / o que acontece se ignorar*.

## 7. Como rodar (DSH)

- `subagent` com: contrato `C1..Cn`, `git diff`, os paths tocados e esta checklist. **Não**
  passe a conversa de implementação — o valor é um par de olhos sem o vício do autor.
- Diff grande (stack de 3 PRs) → um subagente por frente (semântica/checker, backend/
  runtime, docs/CLI) e consolide a matriz no fim.
- `subagent_fork` só quando o auditor precisar do histórico da decisão; ele herda o viés.

## Armadilhas

- Revisar o diff e não os chamadores — o bug mora no arquivo que ninguém abriu.
- Marcar checklist do PR sem prova.
- Consertar durante a auditoria sem um caso que reproduza o bug primeiro.
- Achar que `make check` verde é convergência: os gates provam invariantes, não completude.
- Confundir "fora de escopo" com "não deu tempo".
