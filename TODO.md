# TODO — Roadmap e ideias

Documento vivo do projeto: o que **falta** na linguagem, no checker, no runtime e no
backend. O que já foi implementado **não fica aqui**: vira ADR, [`docs/spec/`](docs/spec/) e
[`docs/decisoes.md`](docs/decisoes.md). Discussões em aberto ficam em
[`IDEIAS.md`](IDEIAS.md); tipos e números em [`TIPOS.md`](TIPOS.md).

> **Escopo:** nada neste arquivo é 1.0. O escopo 1.0 está congelado no
> [ADR-0026](docs/adr/0026-freeze-1.0.md) (com T3b/D-8 como exceções); este TODO é
> **pós-1.0**. Para o mapa completo, veja [`ESCOPO.md`](ESCOPO.md).

**Legenda:** `P0` agora · `P1` próximo · `P2` depois · `P3` algum dia
**Esforço:** `S` (horas) · `M` (dias) · `L` (semanas) · `XL` (meses)

> Regra de ouro: fechar as definições que cada nível consome **antes** de codá-lo
> (checklist na §0.1). Cada feature nova entra com teste; cada mudança de sintaxe entra
> documentada no mesmo commit.

---

## 0. Fila única

Esta é a **ordem oficial**. As seções 1–12 são o catálogo de detalhes; se houver conflito,
vale o que está aqui. Estado em 2026-11-13: backend em **L0–L5 + T7 + L6a–L6i**; o que
resta do L6 está em `PENDING` (`enums`, `exceptions`, `Result` e função genérica como
valor) e o L7 não começou. O status por nível é **gerado** em
[`docs/spec/garantias.md`](docs/spec/garantias.md) a partir de
[`tests/corpus_manifest.py`](tests/corpus_manifest.py) — não copie números para cá.

### 0.1 Definições que não podem faltar antes de cada nível

| Antes de | O que precisa estar fechado | Estado |
| --- | --- | --- |
| **L6 (resto)** | enums/`match` no backend (tags, dispatch e exaustividade), exceções (unwinding), `Any` residual (classes/funções), `repr` de enum e o que o ADR-0055 ainda lista | ⬜ |
| **L7** | `mod.verify()`, passes `-O2`, benchmarks, JIT e mensagens de erro de codegen | ⬜ |

### 0.2 Ordem de execução

1. [ ] **Fechar o L6 em três cortes** (ADRs 0061–0065, aceitos):
       - [x] **L6i — enums/`match`/`Result`** (ADR-0061 aceito) ([ADR-0061](docs/adr/0061-l6-enums-match.md)):
         valor de enum + descritor, construtores de variante, `match` como expressão e
         igualdade/print; alvos `enums.lox`, `result.lox`.
       - [ ] **L6j — exceções/unwinding** ([ADR-0062](docs/adr/0062-l6-excecoes-unwinding.md)):
         aceitar o ADR de ABI **antes** de codar; spike `try`/`raise` com `setjmp`/
         `longjmp` + pilha de cleanup, depois `finally`/retorno e erros de runtime
         capturáveis; alvo `exceptions.lox`.
       - [ ] **L6k — função genérica como valor** ([ADR-0063](docs/adr/0063-orcamento-monomorfizacao.md)):
         especialização no call site ou adiamento explícito para o M8; alvo
         `generic_lambda_value.lox`.
       Ordem recomendada: L6i → L6j → L6k. Enums são aditivos; exceções mexem em toda a
       ABI de chamada e devem ter o spike isolado; o valor genérico é o menor ganho.
2. [ ] **Diagnósticos**: spans → caret → stack trace. ADR próprio **antes**, porque mexe em
       stderr (I3) e no corpus do I1.
3. [ ] **L7 — qualidade**: `mod.verify()`, `-O2`, benchmarks nativo × interpretado, JIT no
       REPL.

### 0.3 Fora do caminho crítico (não bloqueiam nenhum L)

Traits/constraints (T6b, [ADR-0038](docs/adr/0038-traits-nominais.md), pós-MVP), métodos/
herança genérica/reificação (parked na §10), type application explícita, função genérica
como valor, módulos/imports, stdlib, contratos, async, tooling/LSP/formatter e performance.
Esses itens voltam quando o backend estiver no nível em que passam a doer; nenhum deles
impede o L6 ou o L7.

**Com plano fechado, mas ainda fora da fila:**

- **stdlib, kernel e imports** — §13, com [ADR-0071](docs/adr/0071-primitivas-de-runtime.md)
  (primitivas e complexidade), [ADR-0072](docs/adr/0072-stdlib-batteries.md) (batteries) e
  [ADR-0073](docs/adr/0073-imports-modulos.md) (imports, **proposto**). O passo 13.3
  (cache de offsets + `substr`/`join`) é independente do backend e pode começar já; a
  ordem completa está na §13.7.

### 0.4 Onde está o detalhe

| Assunto | Seção |
| --- | --- |
| sintaxe e açúcar | §1 |
| tipos, checker e narrowing | §2 + [`TIPOS.md`](TIPOS.md) |
| diagnósticos, exceções e runtime | §3 |
| performance do tree-walk | §4 |
| decisão sobre bytecode/VM | §5 |
| backend LLVM, níveis, corpus | §6 |
| tooling, CI e LSP | §7 |
| o que ainda vale do Lox2 | §8 |
| milestones M6–M9 | §9 |
| ideias soltas e coisas adiadas | §10 |
| decisões ainda em aberto | §11 |
| stdlib, kernel de primitivas e imports | §13 |

---

## 1. Sintaxe pendente

> Portão: sintaxe nova passa pelo
> [ADR-0066](docs/adr/0066-orcamento-e-gate-sintatico.md) (quatro perguntas, orçamento e
> aprovação humana). O agente **pergunta antes** de adicionar sintaxe; diagnóstico
> dirigido sem mudar gramática não conta como feature.

**Fechado em 2026-11-13**
- [x] `not` substitui `!` como negação ([ADR-0068](docs/adr/0068-not-substitui-bang.md)).
- [x] destructuring aninhado (`val (a, (b, c)) = t`)
      ([ADR-0069](docs/adr/0069-destructuring-aninhado.md)).
- [x] `"""` multilinha canônica e raw `r"..."`/`r"""..."""`, com `"..."` de uma linha
      ([ADR-0070](docs/adr/0070-strings-multilinha-e-raw.md)).
- [x] `fn` opcional em método, operador no início da linha em brackets, união em `is`
      com parênteses e diagnósticos dirigidos
      ([ADR-0067](docs/adr/0067-desambiguacao-sintatica.md)).

**Fila aprovada para permanecer** (o `P` é prioridade **dentro do §1**, não a ordem do §0;
cada uma ainda responde às quatro perguntas e exige aprovação humana antes de codificar)

| Pri | Item | Nota |
| --- | --- | --- |
| `P2` | `break`/`continue` | saída antecipada de laço; `while` não cobre. Rótulo (`break outer`) é capacidade extra, depois. |
| `P2` | spread `...lista` em chamadas e literais | anda junto com variádicos; custo no checker/backend. |
| `P2` | variádicos (`fn log(nivel, ...args)`) | direção em [`IDEIAS.md`](IDEIAS.md) I-5; aridade dinâmica no checker/backend. |
| `P3` | argumentos nomeados | **bloqueado até o LLVM MVP** ([ADR-0014](docs/adr/0014-identidade-e-invariantes.md)/[ADR-0066](docs/adr/0066-orcamento-e-gate-sintatico.md)); o registro fica aqui. |
| `P3` | namespaces/imports | capacidade, fora do caminho crítico (§0.3); ADR próprio. |
| `P3` | traits nominais, extension methods, operator overloading e `derive` | pós-MVP ([ADR-0038](docs/adr/0038-traits-nominais.md)); o registro fica aqui. |
| `P3` | `type` alias transparente (sem generics) | [ADR-0039](docs/adr/0039-decisoes-tipos-pendentes.md); gasta o último slot de forma de declaração (5/6). |

Diagnóstico que não muda gramática continua sendo feito direto (e ganha teste), como os
de [ADR-0067](docs/adr/0067-desambiguacao-sintatica.md).

### Decisões já descartadas (para não revisitar)

A lista completa de não-objetivos sintáticos está no
[ADR-0066](docs/adr/0066-orcamento-e-gate-sintatico.md); os principais:

- parênteses opcionais na condição do `if` → **não**: exigiria regra de newline nova para
  separar condição e corpo e manteria duas grafias do mesmo `if`.
- corpo de expressão em `fn` (`fn f(x) -> x * 2`) → **não**: segunda forma de corpo, e o
  `->` fica ambíguo com tipo-tupla e com corpo de bloco.
- bloco como expressão → **não**: `{` já é bloco, mapa e braço de `match`; "último valor
  implícito" contraria o I2.
- `match` estrutural em uniões → **não**: exige tipos em runtime (*witnesses*), contra o
  erasure do [ADR-0040](docs/adr/0040-generics-classes-desenho.md).
- `loop { }` → **não**: duplica `while (true)`, mesma lógica de `++`/`--`.
- trailing closure (`lista.map { |x| x * 2 }`) → **não**: `{` e `|` já têm dono (bloco,
  mapa, ou-de-bits); não-objetivo do [ADR-0066](docs/adr/0066-orcamento-e-gate-sintatico.md).
- `!` como negação → **não**: substituído por `not`
  ([ADR-0068](docs/adr/0068-not-substitui-bang.md)).
- `//` como comentário → **não**: é divisão inteira; comentário é `#`.
- `&&`/`||` → **não**: `and`/`or` existem; `not` cobre a negação.
- `switch` → **não**: `match` existe ([ADR-0041](docs/adr/0041-enums-match.md)).
- `++`/`--` → **não**: `i = i + 1` existe.
- `end` no estilo Ruby/Lua → **não**: chaves são melhores para erro de parser.
- Off-side rule (indentação significativa) → **não**: caro no scanner e ruim no REPL.
- Herança com `<` → **não**: `class Cachorro(Animal)`
  ([ADR-0008](docs/adr/0008-heranca-class-parens.md)).
- Pipeline `|>`/`:>` → **não** por enquanto ([`IDEIAS.md`](IDEIAS.md) I-2).
- `?:` elvis → **não**: duplicaria `??` ([ADR-0013](docs/adr/0013-ternario-nil-aware-escapes.md)).
- `s[i]` em string → **não**: acesso explícito por `chars(s)`
  ([ADR-0035](docs/adr/0035-strings-texto.md)).
- Identificadores Unicode → **não** por ora: ASCII ([ADR-0035](docs/adr/0035-strings-texto.md)).
- `fun` como keyword → **não**: é `fn` ([ADR-0011](docs/adr/0011-fn-elif-ponto-e-virgula.md)).
- `**kwargs`, named args por enquanto e `**` de mapa: ver [I-5](IDEIAS.md).

---

## 2. Tipos: o que ainda falta

T1/T2/T3a/T3b, T4, T5, T6a, T6c e T7 estão **fechados** (detalhes em
[`docs/decisoes.md`](docs/decisoes.md) e nos ADRs 0020–0027/0033/0040/0041/0050). O que
sobrou:

| Etapa | O que falta | Ganho |
| --- | --- | --- |
| **T3c** ❌ | parâmetro implícito foi implementado e **revertido**: omissão virava quantificação universal sem marcador, contra o [ADR-0020](docs/adr/0020-assinaturas-explicitas.md) ([ADR-0034](docs/adr/0034-t3c-revertido.md)) | — |
| **T6b** ⏸ | traits nominais com `implements`, métodos default e constraints: decididos, **pós-MVP** ([ADR-0038](docs/adr/0038-traits-nominais.md)) | abstração |

Pendências pontuais:
- [ ] `P2` merge completo em CFG e aliasing fino (chamada/atribuição já invalidam refinos de
      campo/índice; `var` capturado por closure ainda não); ver
      [ADR-0045](docs/adr/0045-narrowing-representacao.md) e
      [ADR-0032](docs/adr/0032-narrowing-campos-indices.md) §Limitações.
- [ ] `P2` **T3c-v2 (HM-lite)**: inferir o tipo do parâmetro pelo **uso no corpo**
      (unificação: `x * 2` liga a `Int`, `==` generaliza), em vez de universal por omissão;
      precisa de unificação no corpo e mensagens próprias ([ADR-0034](docs/adr/0034-t3c-revertido.md)).
- [ ] `P3` flow-sensitive para `val` (uma atribuição só).
- [ ] `P3` generics com constraints (`T: Trait`), type application explícita
      (`id[Int](1)`) e função genérica como valor.
- [ ] `P3` inferência de retorno para funções com corpo de expressão.
- [ ] `P3` `--check --json` com spans para editor/LSP.

Modelo atual em [`src/frontend/ty.py`](src/frontend/ty.py): primitivos, `List[T]`, `Map[K,V]`,
`FnTy`, `ClassTy`/`ClassObjectTy`, `NativeModuleTy`, `UnionTy`, `TyVar`, `GenericFnTy` e
`Never`. `Any` existe no tree-walk e no backend boxeado (L6e,
[ADR-0055](docs/adr/0055-l6-any-casts.md)); os limites estão no próprio ADR.

---

## 3. Runtime e semântica (depois do livro)

### 3.1 Diagnósticos profissionais (P2, L)

`ErrorReporter` já é instância por execução (sem estado global). O desenho profissional:

- [ ] `Diagnostic` imutável: `severity` (error/warning/note/help), `code` (`E0102`),
      `span` (arquivo, linha, coluna, offset, largura), `message`, `labels[]`, `notes[]`.
- [ ] **Coleta separada de renderização**: o reporter só acumula; quem imprime é um
      `Renderer` (TTY colorido, texto puro, JSON). Hoje `ErrorReporter.report` imprime
      direto — quebrar isso permite testar diagnóstico sem capturar stderr.
- [ ] `SourceFile` com cache de linhas e coluna correta com tabs/Unicode → caret preciso.
- [ ] Dedup por `(code, span)`, limite `--max-errors` e supressão de erros em cascata
      (panic mode): um erro de sintaxe não deve gerar 20 erros derivados.
- [ ] **Códigos estáveis** documentados em `docs/spec/erros.md`: `E0xxx` lexer, `E1xxx`
      parser, `E2xxx` resolver, `E3xxx` tipos, `E4xxx` runtime. Testes citam o código.
- [ ] Mensagens com ação: `expected ';'` + `ajuda: adicione ';' ao fim da linha 3` +
      `nota: declarações terminam com ';' por enquanto`.
- [ ] Erros de tipo com proveniência: `expected Float, found String` + "o valor vem de
      `pessoa.nome` (linha 7)".
- [ ] Warnings que não interrompem a execução; `-Werror` no CI para tratá-los como erro.
- [ ] `--json` com a lista de diagnósticos (mesma estrutura do LSP) para editor e CI.
- [ ] Stack trace de runtime com frames: `at fib (linha 4) ← main (linha 9)`.
- [ ] Mesmos `Diagnostic` alimentam `textDocument/publishDiagnostics` no LSP (P3).
- [ ] Testes de diagnóstico: snapshot de `(code, span, message)` e golden de stderr.
- [ ] **Schema JSON v1** com `code`/`kind`/`span` (offset em bytes + linha/coluna)/
      `fixes[]`/`docs`, versionado em `schema_version`, com teste de determinismo
      (mesmo input → bytes idênticos). Desenho em [`IDEIAS.md`](IDEIAS.md) I-4.
- [ ] `--error-format=human|short|json|json-lines`; `lox explain <code> --json` e
      `lox capabilities --json` (versão, schema, códigos, exit codes).
- [ ] Resolução determinística: ordenar por `(file, offset, code)`, dedup, sem timestamp/
      endereço/caminho absoluto, um erro raiz por causa.

**Anti-metas:** não usar `assert` do Python para validar código do usuário (assert pode
ser desligado com `-O` e não tem span); não engolir exceção; não imprimir direto do
scanner/parser (só coletar); não usar exceção Python como controle de fluxo normal.

### 3.2 Runtime e linguagem

- [ ] `P1` **spans/caret/stack trace**: recorte mínimo da §3.1; ADR próprio **antes** de
      mexer em stderr (I3) e no corpus do I1.
- [ ] `P2` **subclasses de runtime** (`DivisionByZero`, `IndexError`, ...): hoje tudo é
      `LoxRuntimeError` ([ADR-0042](docs/adr/0042-excecoes.md)); diagnóstico, não sintaxe.
- [ ] `P2` **`assert`/`panic`/`exit` nativos**: funções da stdlib, sem sintaxe nova — o
      portão aplicável é o do [ADR-0014](docs/adr/0014-identidade-e-invariantes.md), não o
      sintático.
- [ ] `P2` **recuperação de erro no parser** (múltiplos erros por execução).
- [ ] `P2` **REPL multiline** (continua enquanto `(`/`{`/`[` abertos) + histórico
      (`readline`) + `:help`, `:ast`, `:type expr`, `:clear`.
- [ ] `P3` **`import`/módulos** com cache de compilação.
- [ ] `P3` **`toString` customizável por classe** (interpolação chamando o método).

### 3.3 Contratos (Design by Contract) — P2, M

- [ ] `requires` / `ensures` / `invariant` como cláusulas opcionais entre assinatura e
      corpo; `result` no `ensures` e `old(expr)` para o estado de entrada.
- [ ] Expressões de contrato **puras** (sem I/O/atribuição); o checker impõe.
- [ ] Violação é erro fatal **estruturado** (`C1xxx`, `kind: contract_violation`), não
      exceção capturável por `try`/`except`.
- [ ] `--contracts=off|check|warn` (default `check` no interpretador, `off` no nativo).
- [ ] Invariante de classe checado na entrada/saída de métodos públicos; herança com
      pré-condições enfraquecidas e pós-condições fortalecidas (Liskov).
- [ ] Contratos como oráculo de property-based testing (conecta com o fuzzing do §7).
- [ ] Codegen: cláusula vira branch + chamada de panic; **nunca** `llvm.assume` sem
      checagem (violação seria UB, não erro).

Sintaxe, opcionalidade e protocolo de reparo: [`IDEIAS.md`](IDEIAS.md) I-4.

---

## 4. Performance do interpretador (paralelo, não bloqueia o backend)

Objetivo: não otimizar por otimizar, mas **não deixar o oráculo lento demais** para os
testes diferenciais. O backend já existe; isto não é pré-requisito do L6/L7.

- [ ] `P2` resolver já com **slots** (índice inteiro) em vez de dict de nomes.
      É o maior ganho por linha de código no tree-walk.
- [ ] `P2` `Environment` com lista + profundidade em vez de dict encadeado.
- [ ] `P3` inline caching de `Get`/métodos.
- [ ] `P3` novos casos de benchmark: `fib` recursivo, criação de objetos/`Get`,
      `List`/`Map` e (depois) tuplas/generics.
- [ ] `P3` `--profile` simples (contagem de nós visitados).

> Não vale reescrever o interpretador em Cython/PyPy agora. O alvo é LLVM.

---

## 5. Bytecode: fazer ou não?

**Decisão provisória: não** (por enquanto). Motivos:

- o alvo final é **LLVM**, não uma VM própria;
- uma VM intermediária em Python não é rápida o suficiente para justificar o desvio;
- o tree-walk é a **especificação executável** da linguagem — ótimo para teste diferencial.

Quando reconsiderar: se o codegen LLVM ficar complexo demais para debugar, um "HIR"
(IR própria, tipada, em SSA leve) cumpre o papel sem virar VM. Um bytecode só faria
sentido como *exercício* do livro (Parte III), em repositório separado.

---

## 6. LLVM: o objetivo final

### 6.1 Escolha de ferramenta

**Decidido** ([ADR-0031](docs/adr/0031-backend-nativo.md)): `llvmlite` como *extra*
opcional (`uv sync --extra llvm`), object file emitido pelo LLVM embutido e link com o
`cc` do sistema. `.ll` é artefato de inspeção (`--emit=ll`), não etapa de build. As
alternativas (IR textual + `clang`, transpile para C, `inkwell`) foram comparadas e
descartadas no ADR.

### 6.2 Pipeline

```
AST → Resolver → TypeChecker (tipos concretos/monomorfizados)
    → normalização leve (AST → AST; desugar)
    → LLVM IR (llvmlite.ir)
    → object file (LLVM embutido) → cc → executável
                              └→ MCJIT (modo `lox jit` / REPL) — L7
```

Sem HIR: o lowering foi extraído em módulos no P0 do L5 e o spike de `Any` mostrou que
HIR-lite não é necessária agora ([ADR-0049](docs/adr/0049-any-boxeado-spike-l6.md)).
Reavaliar depois de `Any` completo e containers estabilizados (§11).

### 6.3 Representação de valor (o que falta)

As representações já decididas e implementadas (escalares, `T?`, `String`, closures,
instâncias) estão nos ADRs 0047/0048 e nos níveis `L0`–`L5` do manifesto. O que falta:

| Item | Representação alvo | Nível |
| --- | --- | --- |
| `Any` completo | caixa `{i64 tag, i64 payload}` (spike em [ADR-0049](docs/adr/0049-any-boxeado-spike-l6.md); unbox/`is`/`as` em [ADR-0055](docs/adr/0055-l6-any-casts.md)) — falta classes/funções como payload | L6 |
| enums | tag da variante + payloads; exaustividade já checada no tree-walk ([ADR-0041](docs/adr/0041-enums-match.md)) | L6 |
| exceções | unwinding (decisão pendente: `setjmp/longjmp` × valores de retorno) | L6 |

Regras que continuam valendo:
- `Int` e `Float` separados ([ADR-0006](docs/adr/0006-int-float-separados.md)), sem boxing
  no caminho quente; slots são monomórficos.
- `var x = 1.5; x = 2` **não** é mais divergência: é erro de tipo nos dois motores
  ([ADR-0059](docs/adr/0059-i4-check-limpo-compila.md)).
- `//` e `%` passam pelo runtime (guarda de zero e de `INT_MIN / -1`, que é UB em LLVM).
- toda operação tem caminho desboxado; o runtime só entra onde há caso de borda ou I/O.

### 6.4 Runtime em C (`runtime/runtime.c`)

O runtime já cobre escalares, strings/arena, closures, classes e `Any` do spike (cada
adição está no ADR do nível). Falta acrescentar:

- [ ] unwinding de exceções (com o desenho escolhido no L6);
- [ ] despacho/impressão de enums;
- [ ] os payloads residuais de `Any` (classes/funções).

`main` gerado devolve `0` no sucesso — o valor de retorno de uma função do usuário não é
exit code.

### 6.5 Memória

**Decidido** ([ADR-0031](docs/adr/0031-backend-nativo.md), contrato no
[ADR-0060](docs/adr/0060-orcamento-de-memoria.md)): arena (bump) com teto de **64 MiB**
fixo e `lox_panic` determinístico ao estourar; o orçamento é contrato testado
(`tests/test_backend.py`), não detalhe de implementação. `lox_alloc` é o único ponto de
alocação, então trocar por Boehm é mudar o corpo de uma função — e um ADR novo decide qual
passa a ser a falha determinística de esgotamento.

- **Fase 1 (hoje):** arena sem `free` (CLI curta) — simples, rápida e determinística na falha.
- **Fase 2 (M7, se rodar programa longo):** Boehm (`GC_malloc`, `-lgc`), opt-in por flag.
- **Fase 3 (talvez):** GC preciso com shadow stack — só se o projeto virar sério.
- Contagem de referência está fora: a linguagem permite ciclos (`list_cycle.lox`).
- Referência: *Mapping High-Level Constructs to LLVM IR* (capítulo de GC) — ver §12.

### 6.6 Closures e classes

Implementado no L4/L5 e registrado nos ADRs 0046 e 0048. O que ainda falta de ABI está na
tabela do §6.3 (`Any`, enums, exceções).

### 6.7 Riscos conhecidos

| Risco | Mitigação |
| --- | --- |
| exceções em LLVM (`invoke`/landingpad) são difíceis | começar com `setjmp/longjmp` no runtime; ou `Result` na linguagem |
| GC + LLVM não têm integração nativa | Boehm; ou arena sem free |
| debug info ruim no llvmlite | `--emit=ll` + `lli` no começo; DWARF depois |
| ABI/linking em Windows | usar `clang` como driver, sempre; testar cedo |
| otimizar antes de funcionar | `-O0` até passar a suíte inteira; depois ligar passes |
| erros de codegen são crípticos | verificar módulo (`mod.verify()`), testes pequenos por feature |

### 6.8 Marcos do backend

L0–L5, T7 e L6a–L6i estão entregues (ADRs 0031, 0046–0048, 0050–0058); o detalhe de cada
um fica nos ADRs e no [`CHANGELOG.md`](CHANGELOG.md). Falta:

- [x] **L6i — enums/`match`/`Result`**: ADR-0061 implementado; representação
      `LoxEnumValue`, construtores de variante, `match` com blocos/phi e `Any` tag ENUM.
- [ ] **L6j — exceções/unwinding**: ADR-0062 proposto; ABI `LoxTryFrame`/`LoxException`,
      cleanup stack e `finally`; spike antes da feature completa.
- [ ] **L6k — função genérica como valor**: ADR-0063; especialização no call site dentro
      do orçamento de monomorfização, ou adiamento declarado para o M8.
- [ ] **L7 — Qualidade**: `mod.verify()`, passes `-O2`, benchmarks, JIT no REPL e
      mensagens de erro de codegen.

### 6.9 CLI alvo

```bash
lox run script.lox            # interpretador (hoje: main.py script.lox)
lox check script.lox          # só typecheck/resolver (hoje: --check)
uv run main.py --emit=ll  script.lox  # inspecionar LLVM IR (hoje)
uv run main.py --emit=obj script.lox  # .o para linkar (hoje)
uv run main.py --emit=exe -o app script.lox  # nativo (hoje)
lox build script.lox -o app   # nativo (quando o CLI ganhar subcomandos)
lox build script.lox --emit=ll        # equivalente futuro
lox jit script.lox            # MCJIT, sem arquivo intermediário
lox fmt script.lox            # formatador (dogfooding do parser)
lox repl                      # REPL, com :type, :ast
```

### 6.10 Bônus: WebAssembly

`llvmlite` sabe emitir para **wasm32** (`Target.from_triple("wasm32-unknown-unknown")`).
Isso permitiria um playground no navegador sem Pyodide — a linguagem rodando a 100% no
browser. Guardar como ideia P3 (precisa de runtime mínimo em wasm e de uma ABI de
imports para `print`).

### 6.11 Corpus diferencial (bloqueia o I1)

Regra: o I1 vale para o **corpus anotado e classificado**, nunca para o que o backend
"quase" faz. Todo caso está em `LEVELS`, `PENDING` ou `NEGATIVE`
([`tests/corpus_manifest.py`](tests/corpus_manifest.py)); promover caso = mover de
`PENDING` para `LEVELS` no mesmo commit, com o teste diferencial verde nos três canais.
O status atual (quantos compilam, quantos em `PENDING`) é **gerado** em
[`docs/spec/garantias.md`](docs/spec/garantias.md) — não duplique aqui.

**Teto proposto** ([ADR-0064](docs/adr/0064-orcamento-do-corpus.md)): `PENDING` ≤ 5% do
corpus (hoje 4/110 = 3,6%), sempre com nível/motivo, e `l?` proibido. O I1 só cobre
`LEVELS`; o teto impede que o teste verde vire ficção. Para features grandes, o caso
espera em issue/branch em vez de inflar `PENDING`.

```bash
uv sync --extra llvm
uv run pytest tests/test_backend.py -q
```

---

## 7. Tooling e qualidade

- [ ] `P2` testes diferenciais interpretador × LLVM no corpus **completo** (hoje: o corpus
      declarado em `LEVELS`).
- [ ] `P2` CLI agent-friendly: `--json` em `check`/`ast`/`types`/`fmt`, `--no-progress`,
      `--timeout`, sem prompt interativo, exit codes estáveis (checklist em
      [`IDEIAS.md`](IDEIAS.md) I-4).
- [ ] `P3` fuzzing do scanner/parser com `hypothesis`.
- [ ] `P3` snapshot de AST em arquivo.
- [ ] `P3` tree-sitter grammar + LSP mínimo (diagnostics/hover).
- [ ] `P3` `lox fmt` e teste de idempotência.
- [ ] `P3` site publicado (mkdocs/mdbook) a partir de `docs/`.

---

## 8. Lox2: o que ainda vale

| Recurso | Status | Nota |
| --- | --- | --- |
| iterador de usuário no `for-in` | ⏳ | o `for-in` embutido existe; falta protocolo |
| `print` como função (`println`) | ⏳ | depois da 1.0; statement é a decisão |
| variádicos `...args` | ⏳ | falta implementar |
| trailing closure | ⏳ | falta implementar |
| `type` alias | ⏳ | falta implementar |
| generics + constraints | ⏳ | funções T3b prontas; constraints pós-MVP ([ADR-0038](docs/adr/0038-traits-nominais.md)) |
| uniões + narrowing | 🟡 | `T?`/`is`/`while`/campos/índices prontos; falta merge CFG/aliasing |
| traits nominais + `implements` | ⏸ | decididos com métodos default; pós-MVP ([ADR-0038](docs/adr/0038-traits-nominais.md)) |
| operator overloading | ⏳ | depois de classes |
| namespaces/import | ⏳ | fase A proposta em [ADR-0073](docs/adr/0073-imports-modulos.md) (só `std.*`); fase B (arquivos) em aberto; plano na §13 |
| `try`/`raise` no backend | 🟡 | tree-walk pronto ([ADR-0042](docs/adr/0042-excecoes.md)); unwinding no L6 |
| `match` estrutural em uniões | ⏳ | enum/`match` exaustivo já existe ([ADR-0041](docs/adr/0041-enums-match.md)); falta união/estrutural |
| extension methods | ⏳ | depois do LLVM MVP e de traits |
| classes como valores / metaclasses | 🤔 | só se precisar |
| FFI com C | ⏸ | **não haverá FFI genérica**: kernel fixo de primitivas ([ADR-0071](docs/adr/0071-primitivas-de-runtime.md)); reavaliar só com dor demonstrada |
| stdlib (`io`, `string`, `collections`) | 📝 | plano completo na §13 ([ADR-0072](docs/adr/0072-stdlib-batteries.md)); kernel mínimo primeiro, resto em Lox |
| `async`/`await` | ⏳ | direção no [ADR-0037](docs/adr/0037-async-direcao.md): colored, `Task[T]`, determinístico; só com I/O, pós-M7 |

Fora: VM própria, GC geracional, JIT tracing, cache de bytecode e `Object` raiz — o LLVM
cobre o codegen e o escopo humano manda.

---

## 9. Milestones pendentes

M0–M5 estão fechados (ver [`docs/decisoes.md`](docs/decisoes.md)). Falta:

| # | Marco | Critério de pronto | Estado |
| --- | --- | --- | --- |
| **M6** | LLVM vertical | L0–L6 completos e I1 verde no corpus anotado (hoje falta o resto do L6) | 🟡 em andamento |
| **M7** | Runtime completo | L6 fechado + GC (Boehm) + I1 verde no corpus completo | ⬜ |
| **M8** | Performance | L6–L7: `-O2`, benchmarks e JIT | ⬜ |
| **M9** | Ecossistema | formatter, LSP, docs e playground | ⬜ |

**Regra:** a ordem oficial é a §0. Se algo mudar a semântica de um nível já compilado, o
nível afetado volta para a fila com caso diferencial. Traits nominais continuam pós-MVP e
não bloqueiam nenhum nível.

**Async (ADR-0037):** a arquitetura (frames materializáveis, GC que enxergue frames
suspensos) é preparada durante o L6; a feature entra **depois do M7**, junto com a stdlib
de I/O, e **antes do M8**. Sem I/O não há o que esperar e a feature não passa no portão do
ADR-0014. Paralelismo/multithread fica em avaliação no [`IDEIAS.md`](IDEIAS.md) — não é
async.

---

## 10. Parque de diversões (ideias soltas)

- [ ] **Compilar o próprio interpretador?** (self-hosting) — o *front-end* já é
      self-hostable hoje (lexer em Lox compila nativo e bate a saída); o compilador inteiro
      depende de I/O, GC e do resto do L6. Escada em §13.7 (passo 7). P3/XL.
- [ ] **`lox fmt` em Lox** — primeiro exercício de dogfooding depois do kernel: parser +
      AST printer na própria linguagem, validado contra o `--dump-ast` do Python (§13.7).
- [ ] **Playground WASM** (target `wasm32` do LLVM) rodando no navegador.
- [ ] **REPL com `:type`** — mostra o tipo inferido de uma expressão antes de rodar.
- [ ] **`lox test`** — runner de testes embutido na linguagem (`#[test] fn ...`).
- [ ] **Erros com sugestão** ("você quis dizer `println`?" via distância de edição).
- [ ] **Debugger (DAP)** — breakpoints no tree-walk primeiro; no nativo depois.
- [ ] **Hot reload** no REPL (redefinir funções sem perder estado).
- [ ] **Benchmark suite pública** (fib, nbody, mandelbrot) para acompanhar regressões.
- [ ] **Compilar para um Arduino/Pico?** (LLVM target `thumbv6m`) — suicídio de escopo,
      mas divertido de tentar um dia.
- [ ] **Dialeto embutido**: `lox` como linguagem de script de um app Python (via CFFI).
- [ ] **Gerador de AST a partir de schema** (o livro faz à mão; um script evita erro
      quando a linguagem crescer).
- [ ] **`lox doc`** — gera docs a partir de comentários de documentação (ex.: `##`).
- [ ] **Modo "strict"** vs "loose" para compatibilidade com Lox puro durante a transição.

### Generics pós-MVP — adiados (2026-11-13)

Nada aqui será feito por enquanto. Retomar só com dor demonstrada (um caso de uso real) ou
quando T6b/constraints existirem; o desenho está no
[ADR-0040](docs/adr/0040-generics-classes-desenho.md) §"Em aberto".

- [ ] `fn map[U]` — métodos genéricos: a função livre cobre; sem constraints o corpo só usa
      operações universais.
- [ ] `class IntBox(Box[Int])` — herança de instanciação: composição cobre; exige
      substituição em cadeia no checker e aumenta a superfície que o backend tem que
      reproduzir (I1).
- [ ] `is`/`as Box[Int]` — reificação: exige tipos em runtime (*witnesses*), conflita com o
      erasure e com o tree-walk rodar sem `--check`; o erro explícito atual é o
      comportamento correto.

---

## 11. Decisões em aberto

Só o que ainda **não** foi decidido. Fechadas: [`docs/decisoes.md`](docs/decisoes.md);
pendências de tipo: [`TIPOS.md`](TIPOS.md).

1. **Generics além do MVP:** continuam em aberto type application explícita e função
   genérica como valor; métodos genéricos, herança de `Box[Int]` e `is/as` reificado estão
   adiados (§10). Constraints e traits nominais ficam pós-MVP
   ([ADR-0038](docs/adr/0038-traits-nominais.md)).
2. **Nome e extensão** definitivos (hoje "PyLox", `.lox`; nomes de trabalho na 1.0).
3. **Stdlib pós-1.0:** `io`, `string`, `collections`, `time` não determinístico;
   transcendentais de `math` fora do I3.
4. **Constraints de generics e traits genéricos:** falta desenhar `T: Trait`, coerência e o
   custo na monomorfização ([ADR-0038](docs/adr/0038-traits-nominais.md)).
5. **Contratos e agentes:** `requires`/`ensures`/`invariant`, `--contracts` default e JSON
   schema v1 com `fixes[]` — [`IDEIAS.md`](IDEIAS.md) I-4.
6. **`if`/bloco como expressão:** fora da 1.0; reavaliar quando houver dor real.
7. **Paralelismo (multithread):** em avaliação no [`IDEIAS.md`](IDEIAS.md); async é
   concorrência single-thread ([ADR-0037](docs/adr/0037-async-direcao.md)), não paralelismo.
8. **HIR tipada × extração:** a extração foi feita e o spike de `Any` não pediu HIR
   ([ADR-0049](docs/adr/0049-any-boxeado-spike-l6.md)); reavaliar depois de `Any`
   completo e containers estabilizados.
9. **Unwinding de exceções no backend:** `setjmp`/`longjmp` no runtime × retorno de erro
   explícito (`Result`-like) × tabelas de unwind do LLVM. Decidir antes de promover
   `exceptions`; mexe em ABI, no runtime C e no I1.
10. **Sintaxe de import:** [ADR-0073](docs/adr/0073-imports-modulos.md) propõe
    `import std.<módulo>` (namespace completo, módulos só de declaração, fase A só std).
    Aguarda aprovação humana no gate do ADR-0066; fase B (arquivos do usuário, caminho
    relativo, diagnóstico por fonte) fica em aberto.

---

## 12. Referências

- Livro: <https://craftinginterpreters.com/> — e a suíte de testes oficial em
  <https://github.com/munificent/craftinginterpreters/tree/master/test>.
- Lox2: <https://github.com/HallofFamer/Lox2> · docs <https://mysidia-inc.gitbook.io/lox2>
  (ler `notes/DESIGN.md` e `notes/TYPESYSTEM.md`).
- `llvmlite`: <https://llvmlite.readthedocs.io/> · <https://github.com/numba/llvmlite>
- LLVM LangRef: <https://llvm.org/docs/LangRef.html> · tutorial Kaleidoscope:
  <https://llvm.org/docs/tutorial/>
- *Mapping High-Level Constructs to LLVM IR*:
  <https://mapping-high-level-constructs-to-llvm-ir.readthedocs.io/> (closures, vtables, GC)
- Hindley–Milner (para o modelo mental de unificação):
  <https://en.wikipedia.org/wiki/Hindley%E2%80%93Milner_type_system>
- Crafting Interpreters, cap. 11 (resolver) e cap. 26 (GC) — reler quando chegar a vez.

---

## 13. Stdlib, kernel de primitivas e módulos

> **Escopo:** pós-1.0; **não** bloqueia L6/L7 (§0.3). Decisões:
> [ADR-0071](docs/adr/0071-primitivas-de-runtime.md) (primitivas e complexidade),
> [ADR-0072](docs/adr/0072-stdlib-batteries.md) (política de batteries) e
> [ADR-0073](docs/adr/0073-imports-modulos.md) (imports — **proposto**, aguarda o gate do
> ADR-0066).
>
> **Regra de ouro:** kernel = SO ou representação; tudo o mais é Lox. Nenhuma lógica de
> negócio em primitiva, nenhuma primitiva que Lox faria em O(n).
>
> **Fora:** regex, cripto, rede, subprocesso, async, timezone DB, i18n, YAML/TOML, UUID, bigint.

### 13.1 Camadas

| Camada | O que entra | Implementações | Onde |
| --- | --- | --- | --- |
| kernel | syscalls e representação | Python (oráculo) + C (binário) | `src/execution/primitives.py`, `runtime/runtime.c` |
| std | biblioteca | **uma** (Lox) | `std/*.lox` |
| módulos | nomeação e carga | loader/desugar, sem lógica | `src/loader/` |

### 13.2 Kernel v1 (teto: 15 primitivas)

| # | Primitiva | Assinatura | Amb.¹ | Estado |
| --- | --- | --- | --- | --- |
| 1 | `args` | `args() -> List[String]` | sim | ⬜ |
| 2 | `io.readFile` | `(path: String) -> String?` | sim | ⬜ |
| 3 | `io.write` | `(text: String)` — stdout sem `\n` | não | ⬜ |
| 4 | `io.writeErr` | `(text: String)` — stderr sem `\n` | não | ⬜ |
| 5 | `io.writeFile` | `(path: String, text: String) -> Bool` | sim | ⬜ |
| 6 | `io.readLine` | `() -> String?` (nil no EOF) | sim | ⬜ |
| 7 | `os.exit` | `(code: Int)` — não retorna; 0..255 | sim | ⬜ |
| 8 | `os.getenv` | `(name: String) -> String?` | sim | ⬜ |
| 9 | `time.now` | `() -> Int` (ms desde a época) | sim | ⬜ |
| 10 | `time.sleep` | `(ms: Int)` | sim | ⬜ |
| 11 | `substr` | `(s: String, start: Int, end: Int) -> String` | não | ⬜ |
| 12 | `join` | `(parts: List[String], sep: String) -> String` | não | ⬜ |
| 13 | `charCodeAt` | `(s: String, index: Int) -> Int` | não | ⬜ |
| 14 | `fromCodePoint` | `(codePoint: Int) -> String` | não | ⬜ |

¹ Ambiente = fora do corpus I1 (depende do SO/mundo). `io.write`/`io.writeErr` são
determinísticos e **podem** entrar no corpus. `args()` devolve os argumentos depois do
script/binário, para os dois motores verem a mesma lista.

**Fora do kernel v1** (candidatos à 15ª vaga): `fs.listDir`, `fs.exists`, `os.cwd`.
Entram só quando `std.fs`/`std.paths` precisar; cada um acima de 15 exige remover outro.

### 13.3 Complexidade (ADR-0071)

- [ ] `LoxStr` ganha `i32 *cp_offsets` (NULL até o primeiro acesso aleatório; só para
      `cp_len >= 64`), inicializado em **todo** construtor do runtime.
- [ ] `lox_str_char_at` O(1) usando o cache; `chars` e `for-in` sobre `String` O(n) total.
- [ ] `substr` O(1) para localizar + O(b−a) de cópia; `join` O(total).
- [ ] `charCodeAt`/`fromCodePoint` (Python + C + lowering + checker + spec).
- [ ] `bench/cases/string_scan.lox` (100k code points): antes **2,22 s**; alvo **≤ 0,05 s**.
      Registrar o número no commit e no ADR-0071.
- [ ] Reavaliar os testes de memória: o ponto do `Out of memory` pode mudar com o cache.
- [ ] `docs/spec/semantica.md` (+ nota "atualizado por ADR-0071" no ADR-0035, que é
      imutável).
- [ ] Nível `k0` no `tests/corpus_manifest.py` para os casos do kernel.

### 13.4 Tabela única de primitivas

- [ ] `src/execution/primitives.py`: `Primitive(lox, c_symbol, params, result, py, ambient)`
      + `PRIMITIVES`.
- [ ] Checker registra `FnTy` a partir da tabela (sem `if` por nome).
- [ ] Interpreter embrulha `py` num `LoxCallable` genérico (aridade/tipos da tabela).
- [ ] Backend resolve `c_symbol`/assinatura pela tabela (sem caso especial por nome).
- [ ] `tests/test_primitives.py` itera a tabela: um caso por primitiva, ordem e aridade.
- [ ] Opcional: migrar `len`/`chars`/`str`/`repr`/`range` (tipo sobrecarregado) — não
      bloqueia.

### 13.5 Imports — fase A (ADR-0073, proposto)

- [ ] **Aprovação humana** das quatro perguntas + dos quatro itens em aberto do ADR-0073.
- [ ] `TokenType.IMPORT` + `KEYWORDS` (25 → 26) + linha do ADR-0066 atualizada.
- [ ] Parser: bloco de imports só no topo (antes de qualquer outro statement).
- [ ] Loader: resolve `std.<modulo>` no bundle, dedup, ciclo diagnosticado.
- [ ] Desugar: mangle `std$strings$split` (separador não lexável) e reescreve
      `std.strings.split`; `std` reservado; módulo não é valor.
- [ ] Privacidade: `_nome` de módulo inacessível de fora.
- [ ] Reporter com **nome da fonte** (`std/strings.lox:12`), sem caminho absoluto (I3).
- [ ] Goldens (`tests/cases/imports/`): básico, dois módulos, genérico; negativos
      (import fora do topo, módulo inexistente, módulo como valor, `_privado`, ciclo,
      `std` redeclarado).
- [ ] `docs/spec/sintaxe.md` + `docs/spec/erros.md`; `--dump-ast` documentado como
      desugarizado.
- [ ] **Fase B** (arquivos do usuário): ADR próprio; restrições já decididas no ADR-0073 §5.

### 13.6 Batteries — inventário

Tiers do ADR-0072. `⬜` = a fazer; cada módulo entra com golden + `--check` + auditoria de
determinismo.

**T0 — kernel** (13.2): a base de tudo.

**T1 — núcleo**

| Módulo | Funções | Estado |
| --- | --- | --- |
| `std.strings` | `split`, `splitLines`, `lines`, `words`, `trim`, `ltrim`, `rtrim`, `upper`, `lower` (ASCII), `capitalize`, `startsWith`, `endsWith`, `contains`, `indexOf`, `lastIndexOf`, `replaceAll`, `replaceFirst`, `repeat`, `padStart`, `padEnd`, `reverse`, `slice` (clamp), `isBlank`, `count` | ⬜ |
| `std.lists` | `map`, `filter`, `each`, `fold`, `reduce`, `find`, `findIndex`, `any`, `all`, `none`, `count`, `sum`, `min`, `max`, `sort`, `sortBy`, `reverse`, `slice`, `take`, `drop`, `zip`, `flatten`, `unique`, `contains`, `indexOf`, `first`, `last`, `getOr`, `chunk`, `partition`, `groupBy`, `flatMap` | ⬜ |
| `std.maps` | `entries`, `fromEntries`, `merge`, `pick`, `omit`, `mapValues`, `filterKeys`, `filterValues`, `invert`, `hasValue`, `getOr`, `toList` | ⬜ |
| `std.numeric` | `gcd`, `lcm`, `isPrime`, `primes`, `factorial`, `powMod`, `digitSum`, `isEven`, `isOdd`, `sign`, `mean`, `median`, `mode`, `variance`, `stddev`, `roundTo`, `toBase`, `fromBase` | ⬜ |
| `std.asserts` | `assert`, `assertEq`, `assertNotNil`, `fail` | ⬜ |
| `std.results` | `map`, `mapErr`, `unwrapOr`, `andThen`, `isOk`, `isErr`, `toOptional` | ⬜ |

**T2 — comum**

| Módulo | Funções | Estado |
| --- | --- | --- |
| `std.json` | `parse`, `stringify`, `pretty` (ordem de inserção; `Int`/`Float` distintos) | ⬜ |
| `std.fmt` | `format(template, List[Any])`, `pad`, `commas`, `fixed`, `percent`, `bytes` | ⬜ |
| `std.paths` | `join`, `dirname`, `basename`, `ext`, `stem`, `normalize`, `isAbsolute`, `split` (POSIX) | ⬜ |
| `std.fs` | `readText`, `readLines`, `writeText`, `appendText`, `exists`, `listDir` | ⬜ |
| `std.io` | `write`, `writeErr`, `readLine`, `readAll`, `prompt` | ⬜ |
| `std.cli` | `parse(args, spec)`, `flag`, `option`, `positional`, `usage` | ⬜ |
| `std.sets` | `Set[T]` sobre `Map[T, Bool]`: `add`, `has`, `remove`, `len`, `union`, `intersect`, `difference`, `toList`, `fromList` (precisa de **classe em módulo**) | ⬜ |
| `std.csv` | `parse`, `stringify` (RFC 4180, determinístico) | ⬜ |
| `std.convert` | `toInt`, `toFloat`, `toBool`, `base64Encode`, `base64Decode`, `hexEncode`, `hexDecode` (texto UTF-8 / `List[Int]` 0..255; sem tipo `Bytes`) | ⬜ |

**T3 — extra**

| Módulo | Funções | Estado |
| --- | --- | --- |
| `std.timex` | `iso`, `parseIso`, `daysFromCivil`, `civilFromDays`, `addDays`, `parts` (**UTC-only**) | ⬜ |
| `std.rand` | `seed`, `int`, `float`, `bool`, `shuffle` (PRNG em Lox, determinístico com semente) | ⬜ |
| `std.hash` | `fnv1a32`, `fnv1a64`, `djb2` (sobre `String`; não é cripto) | ⬜ |
| `std.collections` | `Stack`, `Queue`, `Deque`, `PriorityQueue` (classes em módulo) | ⬜ |
| `std.log` | níveis, `writeErr`, sem timestamp por padrão | ⬜ |
| `std.test` | `describe`, `it`, `expect`, `run` (mini-harness; usa `os.exit`) | ⬜ |

**Fora da stdlib:** a linha do topo da §13 (motivos no [ADR-0072](docs/adr/0072-stdlib-batteries.md)).

### 13.7 Ordem de entrega

| # | Passo | Esforço | Depende de |
| --- | --- | --- | --- |
| 1 | **13.3** — cache de offsets + `substr`/`join`/`charCodeAt`/`fromCodePoint` + bench | M | — |
| 2 | **13.4** — tabela única de primitivas | S | 1 |
| 3 | **13.2** — kernel de SO: `args`, `io.*`, `os.*` + `main(argc, argv)` + exit code | M | 2 |
| 4 | **13.5** — imports fase A + `std/strings` + `std/lists` | M | 3 |
| 5 | **T1** restante (`maps`, `numeric`, `asserts`, `results`) + `json`, `fmt` | M | 4 |
| 6 | **T2** restante (`paths`, `fs`, `io`, `cli`, `sets`, `csv`, `convert`) | M | 5 |
| 7 | **T3** + dogfooding: `lox fmt` em Lox, depois front-end self-hosted (§10) | L/XL | 6 |

O passo 1 é independente do backend e pode começar já. O passo 3 mexe no `main` gerado
(`i32 main(void)` → `argc/argv`), mas não muda o ABI de funções — os casos atuais do I1
continuam valendo; o programa que não usa `args()` não muda de saída.

### 13.8 Critério de pronto por módulo

- [ ] programa real em `exemplos/` ou caso que o use (não simetria com outra linguagem);
- [ ] golden em `tests/cases/std/<modulo>/` + `--check` limpo;
- [ ] determinismo declarado (função ambiente ≠ corpus I1);
- [ ] doc na spec quando o módulo estabilizar (e `sources:` válido);
- [ ] zero sintaxe nova — se precisar, é ADR-0066, não stdlib;
- [ ] `make check` verde; `make bench` se tocar caminho quente.
