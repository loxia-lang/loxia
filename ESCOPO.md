# Escopo — 1.0 vs pós-1.0

Esta é a página para responder uma pergunta só: **isto entra na 1.0 ou fica para depois?**

## Regra de leitura

- **1.0** = o que está no [ADR-0026](docs/adr/0026-freeze-1.0.md) + as exceções explícitas
  registradas abaixo. O escopo está **congelado**: nada novo entra sem um ADR que o
  altere.
- **[`docs/spec/`](docs/spec/)** e os ADRs descrevem o que **existe/foi decidido**.
- **[`TODO.md`](TODO.md)**, **[`TIPOS.md`](TIPOS.md)** e **[`IDEIAS.md`](IDEIAS.md)** são
  **pós-1.0**. Se uma ideia está lá, ela **não** é 1.0.
- **1.0 é o congelamento da linguagem/tree-walk**, não um build nativo. O backend LLVM é
  pós-1.0. **1.0 ≠ MVP do backend**: o MVP compilado é o L0–L3, depois da 1.0.

| Documento | Responde |
| --- | --- |
| [`docs/spec/`](docs/spec/) | o que a linguagem faz hoje |
| [`docs/adr/`](docs/adr/) | por que uma decisão foi tomada |
| [`docs/decisoes.md`](docs/decisoes.md) | resumo das decisões fechadas |
| [`TODO.md`](TODO.md) | o que fazer depois da 1.0 |
| [`TIPOS.md`](TIPOS.md) | pendências e decisões de tipo pós-1.0 |
| [`IDEIAS.md`](IDEIAS.md) | ideias ainda em avaliação (pós-1.0) |

**Hoje:** a linguagem 1.0 está implementada no tree-walk e o backend nativo existe em
**L0–L3** (ADR-0031). O que está em [`TODO.md`](TODO.md) é o que vem **depois** dela; o
próximo marco é o **M5 (tipos v2)** e o codegen fica pausado no L4 até lá.

## Status da entrega

| Camada | Estado |
| --- | --- |
| Escopo/linguagem 1.0 | ✅ congelado e implementado |
| Runtime tree-walk | ✅ |
| Suíte e docs | ✅ `make check` verde; 861 pass + 8 `xfail` intencionais |
| Backend nativo | 🟡 pós-1.0: L0–L3 entregues (Int/Float/Bool/nil/String, funções, açúcar, arena); L4+ pausado até o M5 |
| **Publicação 1.0** | 🟡 **release local preparado**: versão `1.0.0`, [`CHANGELOG.md`](CHANGELOG.md) e tag `v1.0.0`; nada publicado externamente |

**Nenhuma feature de linguagem da 1.0 está pendente.** A release local está preparada;
publicar (push/tag remota/pacote) fica para quando você decidir. O backend começou sem
esperar publicação; a continuação depende do M5, não da release.

## 1.0 — dentro

### Linguagem

- Caps. 4–13 do livro: scanner, parser, resolver, funções/closures, classes/herança,
  `this`, `super`, `init`.
- `val`/`var`, parâmetros imutáveis, `fn`, `elif`, `;` opcional, comentários `#`/`/* */`.
- `Int`/`Float` separados, promoção só `Int → Float`, `/` sempre `Float`, `//`, `%`, `**`,
  bits i64, `--debug` para overflow.
- Ternário, `??`, `?.`, interpolação, escapes, `print` statement.
- Ranges, `for-in` (`Range`/`String`/`List`/`Map`), `List[T]`, `Map[K, V]`.
- Defaults e campos, `class B(A)`, lambdas.
- Anotações de tipo, `--check`, inferência local, `T?`, uniões, `is T`, narrowing.
- Generics T3b: funções `fn id[T]`, inferência, sem constraints, monomorfização no backend.
- D-8: `as` explícito, `Int.parse`/`Float.parse` → `T?` e `math.*` determinístico.
- Freeze: erro de runtime fatal (exit 70), sem `try`/`Result`; `clock` fora; strings UTF-8
  com `len` em code points e identificadores ASCII; single-file.
- `Any` existe no tree-walk; o backend L0–L3 o rejeita.

### Tooling 1.0

`--version`, `--dump-ast`, `--check`, `--debug` e o REPL. Diagnósticos com spans/caret/JSON
e LSP **não** fazem parte da 1.0; são pós-1.0 (tooling).

### Exceções explícitas ao freeze

| Exceção | ADR | O que entrou |
| --- | --- | --- |
| T3b | [ADR-0027](docs/adr/0027-generics-t3b.md) | funções genéricas, sem constraints |
| D-8 | [ADR-0029](docs/adr/0029-conversoes-math.md) | `as`, parse e `math.*` determinístico |
| D-5 | [ADR-0028](docs/adr/0028-overflow-debug.md) | `--debug` checando overflow (não muda o release) |

## Pós-1.0 — fora do freeze

| Item | Ordem | Observação |
| --- | --- | --- |
| Backend LLVM L0–L3 | ✅ feito | objetivo do projeto; não muda a linguagem 1.0 |
| M5 — Tipos v2 (T3c/T4/T5/T6a/T6c) | **próximo** | bloqueia L4+ do codegen (TODO §9); traits/constraints pós-MVP ([ADR-0038](docs/adr/0038-traits-nominais.md)) |
| Diagnósticos (spans/caret/stack trace/JSON) | próximo (tooling) | não bloqueia a linguagem; pode vir antes do backend |
| Tuplas | ✅ feito | implementadas ([ADR-0036](docs/adr/0036-tuplas-implementacao.md)); `for-in`/`is` e backend L6 pendentes |
| Classes/métodos genéricos | M5 | extensão do T3b |
| Traits nominais + constraints | pós-MVP | nominal, `implements`, métodos default ([ADR-0038](docs/adr/0038-traits-nominais.md)) |
| `match`/enums, exaustividade | M5 | depois de uniões |
| Módulos/imports, `std.*`, `io`, `string`, `collections`, `time` | pós | single-file fica na 1.0 |
| Async/await (`Task[T]`) | depois do M7 + I/O | direção no [ADR-0037](docs/adr/0037-async-direcao.md); colored, determinístico; não é paralelismo (IDEIAS I-7) |
| Contratos (`requires`/`ensures`/`invariant`) e JSON | pós | ver I-4 no [`IDEIAS.md`](IDEIAS.md) |
| `Result`/`Option`, `try`/`throw` | pós | 1.0 é erro fatal |
| Variádicos, trailing closure, named args, destructuring de campos | pós | ver [`IDEIAS.md`](IDEIAS.md) |
| `type` alias, derive, operator overloading, extension methods | pós | — |
| `if`/bloco como expressão, `println` função, `loop`/`break` rotulado | pós | — |
| Strings multilinha/raw, indexação de string, UTF-8 em identificadores | pós | — |
| `log`/`exp`/`sin`/`cos`/`tan`/`pow`/`math.pi` | pós | libm não garante I3 |
| Formatter, LSP, fuzz, site, REPL multiline | pós | tooling |

**Fora por enquanto:** VM própria/bytecode, `Object` raiz, GC geracional,
JIT tracing, metaclasses, `UInt`/`f32`/`Decimal`/`BigInt`, coerção implícita.

## Como decidir um item novo

1. Ele é necessário para a **linguagem 1.0** já congelada? Se sim, só entra com ADR novo
   que revise o [ADR-0026](docs/adr/0026-freeze-1.0.md) e diga o custo no backend.
2. Senão, vai para [`TODO.md`](TODO.md) (ou [`IDEIAS.md`](IDEIAS.md) se ainda é ideia).
3. Se for decisão de tipo, o id `D-n` fica em [`TIPOS.md`](TIPOS.md) até fechar; depois
   vira ADR + [`docs/decisoes.md`](docs/decisoes.md).

> Regra prática: **se a dúvida é “entra na 1.0?”, a resposta é não** — a menos que seja
> uma das três exceções acima ou um ADR novo que substitua o freeze.
