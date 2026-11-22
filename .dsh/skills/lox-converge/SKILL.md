---
name: lox-converge
description: Auditoria de convergência pós-feature — confere se tudo o que o PR/issue/ADR prometeu foi implementado, testado, documentado e policiado, e caça bugs no raio de explosão da mudança.
whenToUse: Ao terminar uma feature ou fix, antes de abrir ou mergear o PR, ou quando alguém perguntar "ficou tudo?". Não use durante a implementação (congele o diff antes), nem para decidir design (isso é ADR/`lox-syntax`).
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
- **RESSALVA** — promessa parcial declarada **com issue aberta**, doc/ADR pendente com issue,
  ou follow-up fora do diff com issue. Sem issue, não é RESSALVA: é BLOQUEIA.
- **OK** — matriz completa e evidência em cada linha.

Toda saída termina com **"não verificado"** (o que você não abriu nem rodou) e cada achado
segue o formato: *o que o código faz / o que quebra / o fix / o que acontece se ignorar*.

### Ressalva não corrigida vira issue — no mesmo PR

O maior risco de uma RESSALVA é ela virar “aceita para sempre” porque ninguém lembra. Regra:

1. **Abra a issue antes de fechar o PR** e linke no corpo do PR. Sem link, o veredito é
   BLOQUEIA; não existe RESSALVA verbal.
2. Se a correção for adiada, a issue precisa de contexto, evidência, impacto, critério de
   aceite e origem (PR/ADR). Use este corpo:

```text
Contexto: <o que foi entregue e o que ficou parcial>
Evidência: <arquivo:linha ou comando + saída>
Impacto se ignorar: <o que quebra na fase seguinte / quem sente>
Critério de aceite: <teste que falharia hoje; comportamento observável>
Origem: <PR #N / ADR-XXXX>
```

```bash
gh issue create --title "..." --label "area:<area>" --label "P2" --label "size:S" \
  --body-file /tmp/ressalva.md
```

Labels: `P0–P3`, `area:*`, `size:*` (`docs/roadmap.md` §Regras). Se não houver acesso ao
tracker, **peça ao humano para abrir** e mantenha o PR bloqueado; o roadmap não é backlog.
3. Se a ressalva for uma **decisão de design** (não bug), ela não vira issue de follow-up:
   vira Discussion › Ideas ou ADR próprio, e o PR declara qual dos dois.

## 7. Como rodar (DSH)

### Escolha o modo

| Mudança | Modo | Quem revisa |
|---|---|---|
| contrato público, CLI/schema, ABI, cross-layer, oráculo, self-host | **completo** | 2 subagentes + 1 re-check curto |
| refactor interno, folha, docs, teste | **leve** | 1 revisor (ou checklist do autor), sem subagente |

O modo completo é caro; use-o quando o custo de drift silencioso for alto. O leve ainda passa
pela matriz e pelos gates — só não paga dois contextos independentes.

### Congele antes de spawnar

Converge sobre árvore em movimento produz relatório ambíguo (e retrabalho):

```bash
git status --short          # vazio, ou commit/stash antes
git log --oneline dev..HEAD
git diff dev...HEAD --stat
```

- **Não edite enquanto o revisor roda.** Achado que chega depois de um fix já aplicado é
  ruído; o revisor não sabe o que é HEAD e o que é worktree.
- Se precisar continuar trabalhando, materialize o HEAD (`git archive HEAD` em um diretório
  temporário, ou worktree separada) e mande o revisor usar **aquela cópia**.
- Congele o contrato `C1..Cn` no prompt. O revisor recebe promessas, não a conversa de
  implementação.

### Choreografia da rodada completa

1. **Congele** o diff (acima) e escreva `C1..Cn`.
2. **Spawne 2 em paralelo**: um de contrato/escopo/docs/CLI e um adversarial
   (spans, bordas, determinismo, chamadores). Instrua **somente leitura**: não editar, não
   stage/commit, não rodar `git init`/comandos que escrevem.
3. **Time-box de 10–15 min** e orçamento de saída: matriz `C1..Cn`, no máximo 5 achados
   ranqueados, lista de “não verificado”. Nada de rodar a suíte inteira; testes targeted.
4. **Consolide** você mesmo: deduplique, separe bug de opinião de design, reproduza antes de
   aceitar.
5. **Corrija** BLOQUEIA/RESSALVA no mesmo PR; para cada RESSALVA que não for corrigida,
   **abra a issue agora** (regra acima).
6. **Commit** e só então um **re-check curto** no HEAD final: um revisor, só a tabela de
   fechamento dos achados + regressões do raio. Não é uma terceira rodada completa.
7. Feche o PR com a matriz, os links das issues e o que ficou “não verificado”.

### Template do prompt (copiar)

```text
Repo: <path>  Branch: <branch>  HEAD: <sha>
Read-only: não edite/stage/commit; não rode `git init` nem comandos que escrevem.
Se a worktree estiver suja, use `git archive HEAD` e diga isso no relatório.
Load skill lox-converge.

Contrato (C1..Cn): <uma frase verificável por item>
Arquivos tocados: <paths>
Verifique implementação, teste, doc e gate de cada item; procure regressões no raio.
Rode só testes targeted. Time-box: 15 min.

Saída:
- matriz C1..Cn (ok/parcial/ausente/fora) com evidência;
- achados BLOQUEIA/RESSALVA (repro, impacto, fix);
- lista “não verificado”.
Não conserte nada.
```

- Diff grande (stack de 3 PRs) → um subagente por frente e consolide no fim.
- `subagent_fork` só quando o auditor precisar do histórico da decisão; ele herda o viés.

### Sinais de que o converge está caro demais

- Revisor auditando worktree suja ou SHA diferente do HEAD do PR.
- Revisor rodando `make check`/suíte inteira em vez de testes targeted.
- Dois relatórios com os mesmos achados porque o prompt não delimitou a frente.
- RESSALVA sem issue: daqui a duas sessões ninguém lembra; isso não é aceitável.

## Armadilhas

- Revisar o diff e não os chamadores — o bug mora no arquivo que ninguém abriu.
- Marcar checklist do PR sem prova.
- Consertar durante a auditoria sem um caso que reproduza o bug primeiro.
- Achar que `make check` verde é convergência: os gates provam invariantes, não completude.
- Confundir "fora de escopo" com "não deu tempo".
- Rodar converge no meio da implementação: o revisor audita um alvo que muda embaixo dele.
- Aceitar RESSALVA sem issue: o passivo some do radar e volta como bug na fase seguinte.
