# ADR-0152 — `run` AOT: aceitação estrita, flags do interpretador e cache

- **Status:** accepted
- **Data:** 2026-11-27
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0149](0149-motores-primarios-thir-e-congelamento.md) (`run` compila),
  [ADR-0002](0002-tree-walk-como-oraculo.md) (tree-walk como oráculo),
  [ADR-0031](0031-backend-nativo.md) (backend), [ADR-0059](0059-i4-check-limpo-compila.md)
  (I4), [ADR-0075](0075-diagnosticos-estruturados.md) (diagnósticos),
  [ADR-0089](0089-stack-trace-de-runtime.md) (stack trace),
  [ADR-0112](0112-mcp-servidor-stdio.md) (sandbox),
  [ADR-0142](0142-check-por-fases.md) (check por fases)
- **Implementação:** [`loxia/native_cache.py`](../../loxia/native_cache.py),
  [`loxia/cli_commands.py`](../../loxia/cli_commands.py) (`_run_native`),
  [`loxia/engine.py`](../../loxia/engine.py) (`prepare`/`compile_prepared`),
  [`tests/test_run_native.py`](../../tests/test_run_native.py)

## Contexto

O [ADR-0149](0149-motores-primarios-thir-e-congelamento.md) decidiu que o nativo é o produto
e que `loxia run prog.lx` compila com cache. A issue F0 ([#244](https://github.com/loxia-lang/loxia/issues/244))
é a primeira materialização, e três perguntas que o ADR deixou em aberto precisam de uma
resposta verificável antes do código:

1. **Aceitação.** O `run` de hoje checa em modo gradual (anotação ausente vira `Any`); o
   `build` checa estrito (`E3004`). Se o `run` AOT usa o check do `build`, programas sem
   anotação deixam de rodar. O ADR manda "garantir que a aceitação não divirja **ou declarar
   a diferença**".
2. **Degradação.** Um install mínimo (`pip install loxia`, sem o extra `llvm`, sem `libgc`,
   sem `cc`) não tem backend. Recusar, cair no tree-walk ou tornar a dependência obrigatória
   muda o contrato de distribuição.
3. **Flags sem equivalente no binário.** `--json`, `--json-lines`, `--error-format=json`,
   `--sandbox` e `--stdin` são contratos do interpretador. O binário não tem flags (argv é do
   programa, `args()`), não emite o envelope JSON e não tem perfil de sandbox.

Medições que ancoram a decisão (2026-11-27, 8 núcleos): `build --emit=exe` de programa
pequeno custa **1,26 s** na primeira vez da máquina (compilando as 7 unidades de runtime) e
**0,16 s** com elas quentes; o `run` interpretado de `bench/cases/loop_sum.lx` leva **0,57 s**
e o binário ~0,00 s; a chave de cache conservadora do `loxia test` custa ~30 ms por execução
(walk + hash de 771 arquivos).

## Decisão

`loxia run prog.lx` **compila com o backend e executa o binário**, com cache
content-addressed. As regras:

### 1. Aceitação: estrita, com dica, sem fallback

O caminho AOT usa o **mesmo check estrito do `build`**. Programa sem anotação (`E3004`) ou
com lacuna declarada do backend (`E4001`) é **recusado com exit 65** e uma linha de dica
apontando `--interpret`. Não há fallback silencioso para o tree-walk: o motor que executa é
o que o usuário pediu (ou o padrão), e a latência não muda de programa para programa sem
que o usuário saiba.

Erro **rebaixável** (`lowerable`, ex.: `print(1 + true)`) continua sendo rebaixado a panic
site: o binário produz o mesmo `Rxxxx`/exit 70 do tree-walk. Um valor `<error>` que chega a
uma fronteira tipada (retorno, argumento, atribuição) não pode virar `internal lowering
error` — vira zero do tipo esperado num bloco inalcançável (o panic site já emitiu o erro).

### 2. Toolchain ausente: recusa acionável

Sem `llvmlite`/`libgc`/`cc`, o `run` AOT recusa com exit 65 e o diagnóstico **`E4004`**
("native toolchain unavailable"), com a instrução de instalação e a alternativa
`--interpret`. A mensagem nunca é "internal lowering error" nem traceback. O código novo é
estável e entra no catálogo gerado (`docs/spec/erros.md`).

### 3. Flags do interpretador: `--interpret` implícito

`--json`, `--json-lines`, `--error-format` diferente de `human`, `--sandbox`, `--stdin` e
`--color=always` executam no tree-walk e isso está no `--help` e na spec. O motivo é que
esses flags são **contratos de saída do interpretador** (envelope JSON, perfis de
capacidade, cor); o binário não os tem hoje. `--interpret` é a saída explícita para todo o
resto.

### 4. Cache: closure + fingerprint + memo

- A chave cobre **fontes do closure** (o que o loader resolveu: entrada + módulos
  importados), `loxia.toml`/`loxia.lock` (dependências hipotecadas), flags de dependência,
  flags de build (`debug`, heap), versão, plataforma, arquitetura e a identidade do
  compilador.
- A toolchain (Python + runtime C) entra por um **fingerprint de `mtime_ns`/tamanho**, não
  por hash de conteúdo: qualquer edição invalida (direção segura), e o caminho quente não lê
  ~140 arquivos. A identidade do `cc` é memoizada em `toolchain.json`, validada pelo `mtime`
  do binário do compilador — um hit não roda `cc --version`.
- O build é atômico (temporário + `os.replace` + `chmod 755`); dois `run` concorrentes não
  veem binário pela metade. `--no-cache` compila num diretório temporário.
- O cache é **só desempenho**: não muda bytes, não entra na saída, não esconde erro. Um
  limite total (default **1 GiB**, `LOX_BUILD_CACHE_MAX`) e `loxia cache prune` removem os
  binários mais antigos por `mtime`.

### 5. O que muda no contrato observável

| Programa | `run` (AOT) | `run --interpret` |
| --- | --- | --- |
| check estrito limpo | compila e executa | executa |
| sem anotação (`E3004`) | 65 + dica | executa (gradual) |
| lacuna declarada (`E4001`, hoje 1 caso) | 65 "not supported by the backend yet" | executa |
| erro rebaixável | panic site → 70 no ponto | 70 no ponto |
| `--json`/`--json-lines`/`--error-format≠human`/`--sandbox`/`--stdin`/`--color=always` | cai no interpretador | executa |
| toolchain ausente | 65 `E4004` + dica | executa |

Os testes de contrato do interpretador (golden, suíte oficial, docs, exemplos, determinismo)
passam a pedir `--interpret` explicitamente: o oráculo é o tree-walk, e o binário herdaria o
stdio do processo, furando a captura in-process da suíte. O caminho AOT tem suíte própria,
em processo real (`tests/test_run_native.py`).

## Consequências

### Positivas

- Codegen é exercitado no comando padrão, todo dia; a divergência de desempenho a favor do
  binário aparece em programa real (~0,57 s → ~0,01 s no `loop_sum`).
- Aceitação, degradação e cache são **declarados e testados**, não emergentes.
- `E4004` transforma uma falha de ambiente em diagnóstico acionável.
- `loxia test --native` e `loxia run` compartilham a infraestrutura de cache e o mesmo
  fingerprint de toolchain.

### Negativas / custos

- Programa sem anotação deixa de rodar no comando padrão; `--interpret` é obrigatório até a
  anotação existir (o corpus do livro e snippets antigos são o caso real).
- Hello-world fica ~10 ms mais lento no caminho AOT (parse + chave + exec) do que o
  interpretado; o ganho só aparece quando o programa computa o suficiente.
- A primeira compilação da máquina paga ~1,1 s de runtime; o cache de runtime já amortiza
  da segunda em diante.
- O binário não tem `--json`/sandbox: as superfícies de tooling (MCP incluso) seguem no
  interpretador até a issue de decisão
  ([#261](https://github.com/loxia-lang/loxia/issues/261)).

### Neutras

- O AST, o checker e o oráculo não mudam; o `run` só escolhe o motor.
- O runtime C continua sendo o produto e não congela.
- `loxia run app.bin` segue fora de contrato (o binário é executável direto).

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Fallback silencioso ao tree-walk quando o check estrito falha | Dois motores invisíveis; a latência deixa de ser previsível e o codegen deixa de ser exercitado justamente no código legado. |
| Tornar `llvmlite`/`libgc` dependências obrigatórias no F0 | Decisão de empacotamento/release; o F0 só precisa de uma recusa acionável. |
| Implementar JSON/sandbox no binário agora | Exige ABI de span (offsets/`end`), canal de diagnóstico e perfil de sandbox; é contrato próprio ([#261](https://github.com/loxia-lang/loxia/issues/261)), depois de F1/F2. |
| Chave de cache conservadora (cwd inteiro, como o `loxia test`) | Invalida por arquivo alheio e pode deixar binário velho quando o entry está fora do cwd (`-M`, dependências). A chave por closure é precisa e custa o mesmo (o parse já acontece). |
| Recompilar sempre (sem cache) | Mata o caso de uso (`run` de programa pequeno ficaria ~0,2 s). |

## Como verificar

- `tests/test_run_native.py`: caminho padrão compila; hit não reescreve o binário; edição de
  fonte/módulo invalida; `--no-cache` não escreve; `--max-heap`/`--debug` mudam a chave;
  `E3004`+dica; `--json`/`--sandbox`/`--stdin` caem no interpretador; lacuna `E4001`
  declarada; paridade de canais (sucesso, erro de runtime, `main -> Err`, `args()`+stdin);
  timeout 124; `E4004`+dica sem `cc`; determinismo (hash seed) e `cache prune`.
- `make check` verde (backend incluso); `make bench` sem regressão (o bench mede o
  interpretador com `--interpret`).
- Latência cold/warm registrada em [`docs/plano-de-motores.md`](../plano-de-motores.md)
  (indicador `run_latency_p50/p95`).
- Critério para revisitar: o `run` cold passar de 1 s em programa pequeno sem cache de
  runtime; o hit ficar acima de ~150 ms; ou a issue #261 entregar JSON/sandbox no binário (a
  tabela de flags volta a mudar).

## Referências

- [ADR-0149](0149-motores-primarios-thir-e-congelamento.md) — a decisão de produto.
- [ADR-0059](0059-i4-check-limpo-compila.md) — I4, check limpo compila.
- [`docs/spec/erros.md`](../spec/erros.md) — mensagens e catálogo de códigos.
- [`docs/plano-de-motores.md`](../plano-de-motores.md) — fase F0, indicadores e painel.
- [#261](https://github.com/loxia-lang/loxia/issues/261) — decisão de diagnósticos
  estruturados/sandbox no binário.
