# ADR-0135 — Política de erro: defeito, falha esperada e exceção

- **Status:** accepted — decisão fechada, implementação em migração rastreada
- **Data:** 2026-11-23
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0042](0042-excecoes.md) (exceções), [ADR-0041](0041-enums-match.md)
  (`Result` embutido), [ADR-0072](0072-stdlib-batteries.md) (stdlib — §6 superseded por este),
  [ADR-0026](0026-freeze-1.0.md) (freeze), [ADR-0077](0077-limite-de-pilha.md) (`R1015`),
  [ADR-0089](0089-stack-trace-de-runtime.md) (stack trace), [ADR-0066](0066-orcamento-e-gate-sintatico.md)
  (gate de sintaxe), [ADR-0107](0107-adiados-e-nao-objetivos.md)
- **Implementação:** `std/*.lx` (migração), `tests/test_stdlib_error_policy.py` (ratchet),
  `docs/spec/semantica.md` §Execution

## Contexto

A linguagem tem **dois** canais de erro, ambos implementados e ambos no corpus diferencial:

1. **Exceções** — `try`/`except`/`finally`/`raise`, com `Exception`/`RuntimeError` embutidas e
   `LoxRuntimeError` como subclasse de runtime ([ADR-0042](0042-excecoes.md)); erros de runtime
   (divisão por zero, `R1015`, índice) são capturáveis como `RuntimeError` e o backend LLVM baixa
   `try` ([`lower_exceptions.py`](../../loxia_core/backend/lower_exceptions.py)).
2. **Valores** — `Result[T, E]`, enum embutido com `Ok`/`Err` ([ADR-0041](0041-enums-match.md)),
   combinadores em [`std/results.lx`](../../std/results.lx), e `T?` como opcional.

O que faltava era a **fronteira**. E a documentação já mentia:

- O [ADR-0072 §6](0072-stdlib-batteries.md) afirma "**nenhuma função da stdlib lança exceção na v1** —
  o backend ainda não tem unwinding (L6j)". Hoje o backend **tem** unwinding e a stdlib tem **86
  comandos `raise`** em 13 módulos.
- A auditoria de 2026-11-23 conta, em `std/`: **44** retornos `Result[...]`, **40** funções com
  retorno `T?`, **86** `raise` e `try`/`except` em 7 módulos.

Sem regra escrita, cada módulo escolheu um estilo: `fs` devolve `Result` no nome simples; `json`
devolve `JsonResult` (porque `Result[Any, E]` é recusado pelo checker — `E3011`) e tem `parse`
lançando como casca. O resultado é uma stdlib com três dialetos.

## Decisão

**Três categorias, um veículo por categoria, e a assinatura declara o canal.**

| Categoria | Exemplos | Veículo | Tratamento |
| --- | --- | --- | --- |
| **A. Defeito** (bug do programa ou da VM) | divisão por zero, índice inválido, `R1015`, overflow no `--debug` | `RuntimeError` → fatal por padrão (exit 70) | `try`/`except RuntimeError` existe para depurar e para a borda; **não é API** |
| **B. Falha esperada** (faz parte do contrato) | arquivo ausente, JSON inválido, parse falhou | `Result[T, E]` | chamador, via `match` |
| **C. Fluxo do usuário** (controle entre frames) | abortar um parser recursivo, cancelar um laço | `raise` + `except` declarados pelo usuário | quem escreveu o `try` |

### Regras

1. **Lei da não-sobreposição.** Uma função declara **um** canal. Se retorna `Result`, não lança para
   a mesma condição de falha. Se lança, não retorna `Result`.
2. **Núcleo e casca.** A função que retorna `Result` usa o **nome simples**; a que lança é uma casca
   fina, com sufixo `OrRaise`, documentada, testada e sem lógica própria.
   - Consequência: `json.parseResult` → `json.parse` (núcleo) e `json.parse` → `json.parseOrRaise`
     (casca). `fs` já obedece ao nome simples.
   - **Estado:** a regra vale para as cascas novas. Nenhuma função usa `OrRaise` ainda; a migração
     do `json` é o lote M2 (a stdlib continua com `parse` lançando até lá).
3. **A stdlib não lança por falha esperada — regra-alvo, com migração rastreada.** Hoje restam
   86 `raise` em 13 módulos (M2/M3); o ratchet impede crescimento. A allowlist por natureza é
   exatamente `asserts`, `contracts`, `test`, `property` — o contrato delas *é* falhar.
4. **`T?` sobrevive como casca ergonômica**, sob a regra determinística da seção "Casca `T?`"
   abaixo. `Result` é o veículo de falha com detalhe; `T?` fica onde a ausência é a resposta
   inteira e o uso típico é uma linha. Auditoria desta data: **40 funções** com retorno `T?` em
   `std/` — 26 cascas puras, 10 cascas com irmã `Result` (todas implementadas), 4 helpers privados.
5. **Borda do processo — alvo, não contrato observável.** A linguagem executa statements: não há
   `main` e um `Err` descartado é só um valor (exit 0, hoje). Quando existir um ponto de entrada
   que devolva `Result` ([issue #142](https://github.com/loxia-lang/loxia/issues/142), `needs-adr`),
   o `Err` não tratado imprime `error: <msg>` em **stderr** e sai **70** (mesmo código do erro de
   runtime não capturado), sem caminho absoluto, timestamp ou PID (I3). Até lá, esta regra é a
   direção decidida, não uma promessa verificável — e `docs/spec/semantica.md` diz isso.
6. **Fora de escopo.** O operador de propagação em posição de expressão (`expr?`, estilo Rust/Swift)
   **não** entra aqui: é sintaxe nova e passa pelo [ADR-0066](0066-orcamento-e-gate-sintatico.md),
   em ADR próprio. O `?` que existe hoje é **de tipo** (`String?` = pode ser `nil`), não de
   expressão.

### Casca `T?` — regra determinística

Uma função **pública** pode devolver `T?` somente se as quatro condições valerem:

1. **Ausência é a resposta inteira** — não há código, posição ou `errno` que o chamador vá usar.
2. **Não é fronteira de host** — I/O, OS, processo, rede. Exceção: **EOF**, que é ausência legítima
   (não é erro).
3. **O uso típico cabe em uma linha** — `?? padrão` ou `if x == nil`.
4. **Quando houver detalhe, existe a irmã `<nome>Result`** que o carrega. Enquanto a irmã não
   existir, a entrada fica em `SIBLING_DEBT` (dívida declarada e só decrescente).

O inverso também é regra: detalhe acionável (offset, posição de erro, `errno`), fronteira de host ou
encadeamento que precisa do motivo **forçam** `Result` — a casca não é permitida.

Funções privadas (`_nome`) ficam fora da regra, desde que não virem API exportada.

Auditoria completa de `std/` (2026-11-23):

| Módulo | Função | Decisão |
| --- | --- | --- |
| `bytes` | `readU16be`, `readU16le`, `readU32be`, `readU32le`, `readU64be`, `readU64le` | casca + irmã `readXResult` (implementadas; `BytesError` com offset/wanted/length) |
| `cli` | `option`, `positional` | casca pura |
| `convert` | `toInt`, `toFloat`, `toBool` | casca pura |
| `convert` | `base64Decode`, `hexDecode` | casca + irmã (implementadas; `DecodeError` com kind/index; `index == len(text)` quando a falha é de comprimento) |
| `convert` | `_utf8Text` | privada |
| `csv` | `parse` | casca + irmã `parseResult` (já existe; `results.toOptional`) |
| `framing` | `readStdin` | casca pura (EOF) |
| `framing` | `_contentLength` | privada |
| `io` | `readLine`, `prompt` | casca pura (EOF / entrada vazia) |
| `iter` | `find` | casca pura |
| `json` | `error` | casca pura |
| `jsonrpc` | `methodOf`, `errorOf` | casca pura |
| `lists` | `first`, `last`, `find`, `reduce`, `min`, `max` | casca pura |
| `numeric` | `mean`, `median`, `mode`, `variance`, `stddev`, `fromBase` | casca pura |
| `results` | `errorOf`, `toOptional` | casca pura |
| `timex` | `parseIso` | casca + irmã `parseIsoResult` (já existe; `results.toOptional`) |
| `timex` | `_parseOffset`, `_digits` | privadas |

Resumo: **26 cascas puras**, **10 cascas com irmã** (todas implementadas; `SIBLING_DEBT` vazio),
**4 privadas**.

A implementação canônica da casca já existe no `std`:

```lox
fn parse(text: String) -> List[List[String]]? {
  return results.toOptional(parseResult(text))
}
```

Ou seja: a casca não duplica lógica; ela só apaga o motivo. As 8 irmãs criadas nesta migração
(`bytes.read*`, `convert.base64DecodeResult`/`hexDecodeResult`) seguem esse molde.

`Int.parse`/`Float.parse` (namespace nativo) mantêm `T?`: são o caso canônico da casca — ausência
sem detalhe, uso com `??`. Quem precisa do motivo usa a irmã `parseResult`, se/quando existir.

### Migração rastreada

| Lote | Escopo | Critério |
| --- | --- | --- |
| M1 | Ratchet test + este ADR | `tests/test_stdlib_error_policy.py` verde; orçamento por módulo congelado |
| M2 | Cascas de `Result` (`json`, `csv`, `framing`) | cada `raise` público tem irmã `Result`; sufixo `OrRaise` |
| M3 | Triagem dos 33 restantes (`fmt`, `cli`, `numeric`, `timex`, `rand`, `bytes`, `utf8`, `sets`) | cada um vira `Result`, vira defeito (categoria A) ou entra na allowlist com motivo |
| M4 | Irmãs `Result` das 10 cascas `T?` | ✅ feito: `bytes.read*Result`, `convert.{base64,hex}DecodeResult`; `SIBLING_DEBT` vazio |
| M5 | Corrigir [ADR-0072 §6](0072-stdlib-batteries.md) | §6 marcado como superseded |

Cada lote diminui o orçamento no ratchet; o teste falha se um módulo **aumentar** a contagem de
`raise` ou se um módulo fora da allowlist passar a lançar.

## Consequências

### Positivas

- Uma regra auditável, com teste que policia — e um número que só desce.
- O backend não paga unwinding para falha esperada: `Result` é um enum, baixa como tag + payload.
- I2 ("nada acontece implicitamente") passa a valer também para erro: `Result` é explícito e o
  `match` é exaustivo.
- A borda do processo fica determinística e especificada (I1/I3).

### Negativas / custos

- **Duas ferramentas mentais.** Mitigado pela lei da não-sobreposição, mas exceção continua existindo
  e precisa ser ensinada como "defeito e fluxo do usuário", não como tratamento de falha esperada.
- **Quebra de API** em pré-1.0: `json.parse`/`parseResult` trocam de nome; `Int.parse`/`Float.parse`
  **não** mudam (seguem `T?`, casca canônica).
- **8 irmãs `Result` novas** (as outras 2, `csv.parseResult` e `timex.parseIsoResult`, já existiam):
  `bytes.read*Result` e `convert.{base64,hex}DecodeResult`, com `BytesError`/`DecodeError` e
  golden de erro.
- `Result[Any, E]` continua limitado por `E3011`; até o checker relaxar, módulos com `Any` mantêm
  enum de domínio próprio (padrão permitido, mas declarado).

### Neutras

- `T?` permanece na linguagem e nos operadores; só a stdlib deixa de usá-lo em API pública.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Só `Result`, aposentar `raise` | `a / b` não pode devolver `Result` sem mudar o modelo de expressão; defeitos de VM não têm canal de retorno. Revogaria o ADR-0042 e tornaria `RuntimeError` não capturável. |
| Só exceções, aposentar `Result` | Perde composição (`map`/`andThen`), encarece o backend (unwinding em todo call) e contradiz o uso atual em `fs`/`proc`. |
| Congelar e só documentar | Barato, mas mantém a ambiguidade e não impede um módulo novo de lançar por falha esperada. |
| Renomear a casca para o nome simples (casca `parse`, núcleo `parseResult`) | Contradiz `fs` (núcleo no nome simples) e perpetua dois dialetos. |
| Incluir `expr?` neste ADR | Mistura política com gramática; o gate do ADR-0066 exige decisão própria (e aprovação humana). |

## Como verificar

- `tests/test_stdlib_error_policy.py` — ratchet: módulo → orçamento de `raise`; falha ao aumentar,
  falha em módulo fora da allowlist. Verde no M1 e só desce depois.
- `tests/test_determinism.py` — a borda `error: <msg>` não pode introduzir caminho/PID/timestamp.
- Corpus diferencial (`pytest -m backend`) — qualquer `Result`/`try` novo tem caso no `LEVELS`.
- `--check` limpo compila (I4): `Result` novo não pode virar erro de tipo no lowering.

Revisitar se: o `expr?` for aceito (aí a ergonomia de `Result` muda), ou se `E3011` for relaxado
(o padrão `JsonResult` deixa de ser necessário).

## Referências

- [ADR-0042](0042-excecoes.md) — exceções, classes e captura de `RuntimeError`.
- [ADR-0041](0041-enums-match.md) — `Result[T, E]` como enum embutido.
- [ADR-0072](0072-stdlib-batteries.md) — regra original da stdlib (§6 superseded).
- [`docs/spec/semantica.md`](../spec/semantica.md) — modelo de execução e erro.
- [`std/results.lx`](../../std/results.lx) — combinadores.
