# Loxia 1.0.0

**Loxia** é um dialeto de **Lox**: interpretador tree-walk em Python, nascido em
*Crafting Interpreters* (Parte II — jlox) e evoluído para linguagem própria, com backend
**LLVM** opcional.

- ✅ Parte II concluída: scanner, parser, resolver, funções/closures, classes e herança.
- ✅ Sintaxe própria: `fn`, `elif`, `;` opcional, `val`/`var`, campos declarados e `--check`.
- ✅ Expressões: ternário `a if c else b`, `??`, `?.`, negação `not`, interpolação
  `"${expr}"`, escapes, string multilinha `"""..."""` e raw `r"..."`.
- ✅ Narrowing de `T?`: `if (x != nil)`, `if (x == nil)`/early return e truthiness no `--check`.
- ✅ `x is T`: primitivos, classes/subclasses, `List[T]`/`Map[K, V]` e uniões; narrowing em
  `if`/`else`, `while` e `and`/`or`.
- ✅ Listas tipadas `List[T]`: literal, indexação, `push`/`pop`, `len` e `for-in`.
- ✅ Iterador de usuário: `for x in e` aceita `iter()` + `next() -> T?` (classe, interface
  ou iterador genérico), sem precisar de `implements` ([ADR-0082](docs/adr/0082-iterador-de-usuario.md)).
- ✅ Variádicos `...args` e spread final `f(...lista)` em funções/métodos/lambdas
  ([ADR-0083](docs/adr/0083-variadicos.md)); `fmt.format` usa o novo protocolo.
- ✅ `type Nome = Tipo` transparente e não-genérico, com forward references e imports
  ([ADR-0084](docs/adr/0084-type-alias.md)).
- ✅ `print(valor)` é função builtin `Any -> Nil`; o statement `print expr` foi removido
  ([ADR-0085](docs/adr/0085-print-como-funcao.md)).
- ✅ Mapas tipados `Map[K, V]`: literal `{ "a": 1 }`, `get`/`has`/`remove`/`keys`/`values`,
  igualdade estrutural e `for-in` de chaves.
- ✅ API híbrida: `len`/`str`/`repr` globais e métodos específicos de lista/mapa.
- ✅ Tipos de função nas anotações: `fn(Int) -> Int`, callbacks, variância e classe como
  construtor.
- ✅ Lambdas `fn(x) => ...` e `fn(x) { ... }`, com tipagem contextual e retorno inferido.
- ✅ Funções genéricas `fn id[T] (x: T) -> T`, `map`/`filter`, inferência na chamada e
  monomorfização planejada no backend ([ADR-0027](docs/adr/0027-generics-t3b.md)).
- ✅ Casts explícitos com `as`, `Int.parse`/`Float.parse` → `T?` e `math.*` determinístico
  ([ADR-0029](docs/adr/0029-conversoes-math.md)).
- ✅ Overflow checado com `--debug`; release continua wrapping
  ([ADR-0028](docs/adr/0028-overflow-debug.md)).
- ✅ Checker valida retorno em todos os caminhos, inicialização de campos e override
  compatível.
- 🧪 Suíte pytest com golden cases `.lx`, testes unitários e benchmarks com baseline.
- 🌍 Suíte oficial do Crafting Interpreters (caps. 10–13) adaptada em `tests/official/`.
- 🏷️ **Versão 1.0.0**: release local da linguagem no tree-walk; backend nativo é
  pós-1.0. Ver [`CHANGELOG.md`](CHANGELOG.md).
- 🧊 **Escopo da 1.0 congelado** ([ADR-0026](docs/adr/0026-freeze-1.0.md), com T3b e D-8
  como exceções): erros de runtime fatais, `clock` removido do prelúdio, strings UTF-8
  com identificadores ASCII, `print` como função `Any -> Nil` e escopo single-file. O mapa
  **1.0 × pós-1.0** está em [`ESCOPO.md`](ESCOPO.md).
- 📐 A stdlib **T2** está completa ([ADR-0079](docs/adr/0079-stdlib-t2.md)): `json`,
  `fmt`, `paths`, `fs`, `io`, `cli`, `sets`, `csv` e `convert`, além da T1
  (`strings`, `lists`, `maps`, `numeric`, `asserts`, `results`). Os casos determinísticos
  entram no corpus `t2`; `fs` e leitura de `io` são ambiente e têm teste próprio.
  Próximo passo: **limite de pilha** ([ADR-0077](docs/adr/0077-limite-de-pilha.md)).
  L7b (revisão das mensagens de erro de codegen) segue como pendência de qualidade; JIT
  no REPL fica para depois. O L5, o T7 e o L6a–L6k já entregaram classes, herança,
  closures, `is`/`as`, optionais escalares, `Range`/`for-in`, listas, mapas, tuplas,
  `Any`, `math`/parse e defaults como valor; interfaces nominais estão no tree-walk, no
  checker e no backend (`itab`), e constraints de função (`T: Ord + Num + Interface`)
  também ([ADR-0038](docs/adr/0038-traits-nominais.md),
  [ADR-0080](docs/adr/0080-interfaces-nominais-implementacao.md),
  [ADR-0081](docs/adr/0081-constraints-generics.md)).

## O que esta linguagem promete

A identidade não é o catálogo de features (todas são emprestadas, e isso é normal) — é o
que se promete e se verifica em CI ([ADR-0014](docs/adr/0014-identidade-e-invariantes.md)):

- **I1 — o interpretador é a especificação.** O mesmo programa, interpretado e compilado,
  dá o mesmo stdout, stderr e exit code, byte a byte, para o corpus declarado por nível
  (hoje L0–L6 + T7 + `k0`/`t1`/`t2` em `tests/test_backend.py`; o status por nível é
  gerado em [`docs/spec/garantias.md`](docs/spec/garantias.md)).
- **I2 — nada acontece implicitamente.** Sem coerção entre `Int`/`Float`/`String`, sem
  truthiness exótica, sem `nil` surpresa.
- **I3 — determinismo observável.** Mesma entrada ⇒ mesmos bytes de saída e de
  diagnóstico: sem endereço, timestamp, PID ou caminho absoluto.
- **I4 — `--check` limpo compila.** Se o checker aceita, o binário compila; a única recusa
  aceitável é a lacuna declarada (`... is not supported by the backend yet.`). O checker é
  a fonte única dos tipos.
- **Memória é contrato.** O binário usa GC Boehm ([ADR-0074](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md),
  [ADR-0087](docs/adr/0087-heap-cap-e-self-hosting.md)): hard cap default de 512 MiB
  (`--max-heap` no build) e I1 até 64 MiB de memória viva; estourar é `exit 70` +
  `Out of memory.`. A pilha tem contrato próprio ([ADR-0077](docs/adr/0077-limite-de-pilha.md)):
  10.000 chamadas / 64 MiB e `Stack overflow.` (R1015, com posição e stack trace desde o
  [ADR-0089](docs/adr/0089-stack-trace-de-runtime.md)). O interpretador não tem teto — o
  I1 vale dentro do orçamento.

Detalhes e o que **não** é prometido: [`docs/spec/garantias.md`](docs/spec/garantias.md).

## Instalar

```bash
uv tool install loxia       # comando `loxia` isolado
# ou
pip install loxia           # em um ambiente qualquer (Python >= 3.13)
loxia --version             # loxia 1.0.0
```

O wheel leva a linguagem, o CLI, a **stdlib** e o `runtime.c` — não é preciso clonar o
repo. Para o backend nativo, instale o extra `llvm` (`pip install "loxia[llvm]"`) mais um
compilador C e a `libgc` (Boehm); o interpretador não precisa de nada disso.

## Rodar

Requisitos: Python 3.13 e [`uv`](https://docs.astral.sh/uv/). O backend nativo (`--emit`)
pede `llvmlite` (`uv sync --extra llvm`), um compilador C e, para `--emit=exe`, a `libgc`
(Boehm; `libgc-dev` no Debian/Ubuntu, `bdw-gc` no Homebrew). O interpretador não precisa de
nada disso.

```bash
uv run main.py                 # REPL (Ctrl+C/Ctrl+D para sair)
uv run main.py programa.lx    # executa um arquivo
uv run python -m loxia           # mesma coisa, via pacote
uv run main.py --version       # loxia 1.0.0
uv run main.py --dump-ast prog.lx   # imprime a AST (S-expression), não executa
uv run main.py --check prog.lx      # checa os tipos, não executa
uv run main.py --debug prog.lx      # checa overflow de Int em runtime (release faz wrap)
uv sync --extra llvm                 # habilita o backend nativo (llvmlite)
uv run main.py --emit=ll prog.lx    # IR do LLVM (inspeção)
uv run main.py --emit=obj prog.lx   # .o para linkar
uv run main.py --emit=exe -o app prog.lx   # binário nativo
uv run main.py --emit=exe --max-heap=2G -o app prog.lx  # teto de heap do binário
uv run main.py --emit=ll --output prog.ll prog.lx  # IR em arquivo (--output)
# o runtime C é compilado uma vez e cacheado (LOX_BUILD_CACHE=<dir> isola o cache)
make test                      # pytest (inclui os testes nativos)
make test-fast                 # pytest sem os testes nativos (loop local)
make check                     # ruff + mypy strict + pytest (gate completo)
make check-fast                # ruff + mypy strict + pytest sem nativos
make hooks                     # instala o hook de pre-commit
make bench                     # benchmarks do interpretador vs baseline
make bench-native              # benchmarks do binário nativo (speedup vs baseline)
# resultados e metodologia: bench/README.md
```

### Subcomandos

As flags antigas continuam valendo; os subcomandos são aliases explícitos:

```bash
uv run main.py run prog.lx                 # executa
uv run main.py check prog.lx               # checa (como --check)
uv run main.py build prog.lx --emit=exe -o app
uv run main.py ast prog.lx                 # como --dump-ast
uv run main.py fmt prog.lx                 # formatter mínimo (ADR-0092)
uv run main.py fmt --check prog.lx         # exit 1 se mudaria
uv run main.py doc prog.lx --json          # doc comments /// (ADR-0091)
uv run main.py explain E2001               # família do código
uv run main.py capabilities --json         # versão, comandos, códigos e limites
uv run main.py lsp                         # servidor LSP em stdio (ADR-0090)
```

`--json` é alias de `--error-format=json`; `--json-lines` emite um objeto por linha
(`start`, `diagnostic`, `summary`) para agentes, com `revision` determinística e sem
timestamp. `--stdin` lê o programa de stdin (`--file-name` define o nome exibido e a raiz
de módulos); `--timeout=MS` limita `run`/`check` (exit `124` + `C0001`); `--watch` só vale
para `check`, rechecando o arquivo e os módulos a cada mudança (SIGINT = `130`).
`--no-progress` é aceito e hoje é no-op. `-Werror` transforma warnings em erros (só
`check`/`build`; `run` nunca emite warnings). `doc` gera Markdown (padrão) ou JSON a
partir dos comentários `///` de funções, classes, interfaces, enums, variantes, campos,
tipos e `val`/`var`; não executa o programa. `lsp` sobe o servidor JSON-RPC em stdio
(LSP-0: diagnostics/documentSymbol; LSP-1 básico: hover/definition).

Exit codes do CLI: `65` erro de compilação, `70` erro de runtime, `66` arquivo ausente,
`2` uso inválido, `124` timeout, `130` `--watch` interrompido. O binário gerado por
`--emit=exe` segue o mesmo contrato: `0` no sucesso e `70` no erro de runtime, com o mesmo
stderr.

### Diagnósticos

Diagnósticos de compilação vão para stderr no formato
`arquivo:linha:col: error[CODIGO]: mensagem` + trecho com caret; erros de runtime usam o
mesmo cabeçalho, sem caret, seguidos do **stack trace** (`  at f (arquivo:linha:col)`, com
nome e call site de cada ativação; [ADR-0089](docs/adr/0089-stack-trace-de-runtime.md)).
O arquivo é o real, inclusive para código em módulo. O formato é determinístico (caminho
relativo ao CWD, ordem fixa, sem timestamp/endereço, trace recortado em 5+5+elisão) e os
códigos são estáveis — catálogo em [`docs/spec/erros.md`](docs/spec/erros.md).

```bash
uv run main.py --check --error-format=short prog.lx  # uma linha por diagnóstico
uv run main.py --check --error-format=json prog.lx   # envelope JSON v1 (stdout)
uv run main.py --error-format=json prog.lx           # diagnósticos JSON (stderr)
uv run main.py --color=never prog.lx                 # sem ANSI (também respeita NO_COLOR)
uv run main.py --max-errors=5 prog.lx                # limita (0 = sem limite)
uv run main.py check --json-lines prog.lx            # stream para agente
uv run main.py check --watch --json-lines prog.lx    # recheca a cada mudança
uv run main.py check -Werror prog.lx                 # warning vira erro
uv run main.py run --stdin --file-name prog.lx < prog.lx
```

`--error-format=human` (padrão) mostra o trecho; `short` é o cabeçalho; `json` traz
`schema_version`, `code`, `phase`, `span` (linha/coluna em code points e `offset` em bytes),
`trace` (frames do runtime) e `summary`. Em `--check` o JSON vai para **stdout**; em
`run`/`build` vai para **stderr** (o programa/IR já usam stdout). `--color` aceita
`auto|always|never` e `NO_COLOR` desliga a cor no modo `auto`.

O backend nativo cobre **L0–L6**: `Int`/`Float`/`Bool`/`nil`/`String`, optionais escalares (`Int?`/`Float?`/`Bool?`), `if`/`while`,
variáveis, funções com recursão, ternário/`and`/`or`/`??`, concatenação, interpolação,
`len`/`str`/`repr`, funções locais/lambdas, closures (células e `env`), valores de
função (`<fn f>`/`<lambda>`), classes/campos/métodos/herança, monomorfização de funções e
classes genéricas, containers, `Any`, tuplas, enums e exceções. O que resta é qualidade de
L7 (passes/benchmarks); o backend sem representação falha com erro explícito, nunca com
lowering silencioso. Contratos em
[`docs/adr/0031-backend-nativo.md`](docs/adr/0031-backend-nativo.md),
[`docs/adr/0046-closures-celulas-l4.md`](docs/adr/0046-closures-celulas-l4.md) e
[`docs/adr/0074-gc-boehm-e-contrato-de-memoria.md`](docs/adr/0074-gc-boehm-e-contrato-de-memoria.md).

## Exemplo

```lox
class Conta {
  var saldo;

  init(saldo) {
    this.saldo = saldo;
  }

  deposita(valor) {
    this.saldo = this.saldo + valor;
  }
}

var c = Conta(10);
c.deposita(5);
print(c.saldo);  # 15
```

## Tipos

Funções anotadas e inferência nos locais; o checker é opt-in (`--check`) e os tipos são
apagados em runtime. `;` é opcional no fim da linha e `elif` substitui `else if`:

```lox
fn soma(a: Int, b: Int) -> Int {
  return a + b
}

val total = soma(1, 2)      # Int inferido
val talvez: String? = nil   # String | Nil

val xs: List[Int] = [3, 1, 2]
xs.push(4)
print(len(xs))               # 4
print(xs[0])                 # 3
for x in xs { print(x) }

val idades: Map[String, Int] = {"Ana": 32}
print(idades["Ana"])          # 32
print(idades.get("Bia") ?? 0) # 0 (get devolve Int?)
idades["Bia"] = 28
for nome in idades { print(nome) }   # chaves, em ordem de inserção

val saudacao: String? = "Ana"
if (saudacao != nil) {
  print("Oi, ${saudacao}!")   # narrowing: saudacao é String aqui
}
```

Conversões são explícitas: `3.9 as Int`, `Int.parse("42")` (devolve `Int?`) e
`math.floor(3.9)`; não há coerção implícita nem `42.toString()` (use `str(42)`).

Listas e mapas são **homogêneos** e **invariantes**: `List[Int]` não é `List[Float]`, e
`[1, "a"]` é erro no `--check` (a heterogeneidade exige `List[Int | String]` ou
`List[Any]`). Mapas aceitam chaves `String`, `Int` e `Bool`; `m["ausente"]` é erro e
`m.get("ausente")` devolve `nil`. `val` congela o binding, não o conteúdo: `xs.push(4)` e
`idades["Bia"] = 28` são permitidos.

Aritmética inclui `//` (divisão inteira), `**` (potência) e bits
`& | ^ ~ << >> >>>`; comentários usam `#` e `/* */` (aninhado).

```lox
val rotulo = nome ?? "sem nome"          # default só para nil
val cidade = pessoa?.endereco?.cidade    # acesso seguro
val status = "adulto" if idade >= 18 else "menor"
print("linha 1\nlinha 2")                 # escapes
print("""texto em
duas linhas""")                         # string multilinha (aspas livres)
print(r"c:\temp\novo")                   # raw: `\` literal, sem interpolação
if (not pessoa?.nome) print("sem nome")   # `not` no lugar de `!`
```

## Estrutura

```
main.py          entrypoint compatível (delega para loxia/cli.py)
loxia/           pacote do CLI: `python -m loxia`, --version, --dump-ast
loxia_core/             núcleo em pacotes por fase
loxia_core/frontend/    lexing, AST, parser, tipos de anotação e ast_printer
loxia_core/semantics/   resolver de escopos e checker gradual
loxia_core/execution/   valores, ambiente, objetos, nativos e interpreter
loxia_core/diagnostics/ erros e ErrorReporter
loxia_core/backend/     backend LLVM (llvm_ir isolando a lib, lowering, driver de build)
runtime/         runtime C do código gerado (print, panic, casos de borda de // e %)
exemplos/        programas de exemplo (fib, fizzbuzz, closures, classes, primos, quicksort)
tests/           pytest + golden cases (.lx)
tests/official/  suíte oficial do livro (caps. 10–13), adaptada
bench/           harness de performance e baseline
docs/            especificação, arquitetura e ADRs
TODO.md          roadmap e decisões em aberto
TIPOS.md         pendências de tipos
IDEIAS.md        discussões de design (parking lot)
```

`AGENTS.md` é local (não versionado), com regras de contribuição para agentes/devs.

A suíte oficial do livro roda com:

```bash
uv run pytest tests/test_official_suite.py -q
```

Ela é mantida separada dos golden cases; detalhes de adaptação e `xfail` em
[`tests/official/README.md`](tests/official/README.md).

## Editores

O GitHub **ainda não** destaca `.lx`: o [linguist](https://github.com/github-linguist/linguist)
exige adoção (2.000 arquivos por extensão indexados em repos públicos) e uma grammar
TextMate vendorizada. Por isso o `.gitattributes` mantém os fontes fora do breakdown do
repo (`linguist-detectable=false`) em vez de marcá-los como outra linguagem.

O destaque real vem da grammar TextMate de [`editors/`](editors/) — a mesma que VS Code,
Sublime e TextMate usam, e a que um PR futuro no linguist vai exigir. Ela é **gerada** de
`loxia_core/frontend/` (keywords e tokens) e `loxia_core/execution/prelude.py` (nomes embutidos), então
não descola do scanner:

```bash
make grammar     # regera editors/vscode/syntaxes/loxia.tmLanguage.json
```

Instalação, troubleshooting e limitações: [`editors/README.md`](editors/README.md).
Para Shiki (site de docs e viewer do harness), `editors/shiki/loxia.mjs` entrega a mesma
grammar no formato que ele consome — também gerado por `make grammar`.

## Documentação

- **Especificação atual**: [`docs/spec/`](docs/spec/) — [garantias](docs/spec/garantias.md),
  [léxico](docs/spec/lexico.md), [sintaxe](docs/spec/sintaxe.md),
  [semântica](docs/spec/semantica.md), [erros](docs/spec/erros.md).
- **Documentação técnica**: [`docs/tech/arquitetura.md`](docs/tech/arquitetura.md).
- **Estilo**: [`docs/guia-estilo.md`](docs/guia-estilo.md).
- **Decisões de design (ADRs)**: [`docs/adr/`](docs/adr/).
- **Roadmap**: [`TODO.md`](TODO.md) · **tipos**: [`TIPOS.md`](TIPOS.md) ·
  **ideias**: [`IDEIAS.md`](IDEIAS.md).

> A especificação descreve o que o código faz **hoje** (Lox do livro + `val`/`var`,
> `Int`/`Float`, ranges/`for-in`, listas, mapas, tuplas, herança `class B(A)`,
> defaults/campos, checker `--check`, `fn`/`elif`/`;` opcional, ternário/`??`/`?.`,
> `not`, escapes, `"""`/raw, narrowing e generics). O que falta — o resto do L6/L7 no
> backend (enums/`match`, exceções), `break`/`continue`, spread/variádicos e imports — está
> nos documentos de roadmap e ainda **não** está implementado.
