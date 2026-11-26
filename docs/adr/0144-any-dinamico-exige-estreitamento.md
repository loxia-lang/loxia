# ADR-0144 — `Any` dinâmico exige estreitamento (`is`/`as`)

> **Atualização (2026-11-25):** o narrowing cobre classe concreta, tupla, enum, escalares, containers e **interface** ([ADR-0146](0146-is-as-interface.md)). `is`/`as` para **função e objeto de classe** ainda não existem (`E3013`/`E3007`); está na issue [#213](https://github.com/loxia-lang/loxia/issues/213). Um `Any` que guarda uma função ou um objeto de classe só pode ser estreitado para a classe concreta.

- **Status:** accepted
- **Data:** 2026-11-25
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0055](0055-l6-any-casts.md) (`Any` boxeado), [ADR-0059](0059-i4-check-limpo-compila.md)
  (I4), [ADR-0142](0142-check-por-fases.md) (check obrigatório), [ADR-0079](0079-stdlib-t2.md)
  (campos-container), [ADR-0087](0087-heap-cap-e-self-hosting.md) (self-hosting),
  [ADR-0045](0045-narrowing-representacao.md) (narrowing e tipos de representação)
- **Implementação:** `loxia_core/diagnostics/codes.py` (`E3025`),
  `loxia_core/semantics/checker.py` (get/set/call/index), `loxia_core/backend/lower_optionals.py`
  (`_narrowed`), `loxia_core/backend/lower_instances.py`, `lower_containers.py`,
  `lower_calls.py`, `lower_range.py`, `lower_strings.py`, `loxia/engine.py` (publica
  `checker.types` como `flow_types`), `tests/cases/any_narrowing.lx`,
  `tests/cases/errors/any_*.lx`

## Contexto

`Any` é o top type ([ADR-0055](0055-l6-any-casts.md)) e o backend o representa como um box
`{i64 tag, i64 payload}`. O checker tipava **acesso dinâmico** em `Any` como `Any`: membro
(`a.m`, `a.m()`), escrita (`a.x = v`), chamada (`a()`) e índice (`a[i]`). O backend não tem
como resolver isso sem despacho por nome em runtime; o resultado era sempre ruim:

| Programa com `--check` limpo | Tree-walk | Binário |
| --- | --- | --- |
| `val a: Any = C(); a.m()` | `<fn m>` | `R1014` (panic incondicional) |
| `a.x = 2` | grava | `R1014` (`Only instances have fields.`) |
| `f()` com `f: Any` chamável | chama | `R1001` |
| `a[0]` com `List`/`Map` em `Any` | indexa | `R1000` ou `E4002` |
| `if (a is C) { a.m() }` | chama | `R1014` — o checker estreita, o backend ignorava |

Os três primeiros violam I1 (mesmo programa, resultados diferentes); o `E4002` viola I4 (check
limpo nunca vira erro de tipo no lowering). O padrão `if (a is C) { ... }` é o mais grave: é a
forma natural de usar `Any` e o binário divergia sempre.

## Decisão

**1. Acesso que depende da forma exige estreitamento no checker.** Quando o receptor é `Any`
(não estreitado), `Get`, `Set`, `Call` (callee `Any`) e `Index` são erro `E3025`:

```
Can't access a member of `Any`; narrow it with `is` or cast it with `as` first.
Can't assign a field on `Any`; cast the receiver with `as` first.
Can't call a value of type `Any`; cast it with `as` first.
Can't index a value of type `Any`; cast it with `as` first.
```

O estreitamento (`if (a is C)`, `(a as C)`) é suficiente: o tipo de fluxo do checker passa a
ser concreto e o acesso é checado normalmente.

**2. O backend honra o tipo de fluxo.** O engine publica `checker.storage_types` (representação,
como antes) **e** `checker.types` (fluxo, com narrowing). `_narrowed(expr, value)` desembrulha
o box `Any` para a representação do tipo estreitado no ponto de uso: receptor de membro/escrita,
callee, índice, iterável de `for-in`, argumento de `len` e descrição de elemento de
`List`/`Map`. O slot continua guardando `Any`; o unbox é local e não muda a ABI.

**3. O que continua dinâmico.** Operações de **valor** não precisam da forma e seguem
funcionando sobre `Any` sem estreitamento: aritmética, comparação, igualdade, `is`/`as`,
`print`/`str`/interpolação, `not`/unário, `??` e `and`/`or`. `for-in` sobre `Any` não
estreitado, `len` sobre `Any` não estreitado (`len of non-String`) e ternário com braço `Any`
continuam lacunas declaradas (`E4001`).

**4. Precisão do refino de caminho.** Chamadas que podem executar código do usuário e
escritas de campo/índice invalidam os refinos de campo/índice ([ADR-0086](0086-narrowing-captura-e-merge.md),
[ADR-0141](0141-soundness-de-fluxo-do-checker.md); não há análise de aliasing). Nativas puras
(`print`, `len`, `str`, `repr`, `chars`, `range` e métodos de `List`/`Map`) **não** invalidam.
Depois de uma chamada de usuário ou escrita, reestreite o caminho. Precisão de
efeitos/aliasing fica em [#216](https://github.com/loxia-lang/loxia/issues/216).

## Consequências

### Positivas

- Fecha os furos de I1 e I4 acima: o programa check-limpo ou compila igual ao tree-walk, ou é
  recusado no check com uma mensagem acionável.
- `if (a is C) { a.m() }` passa a funcionar no binário; o narrow do checker deixou de ser
  decorativo.
- O campo `Any` (ADR-0145, PR seguinte) nasce usável: `c.x.m()` vira
  `(c.x as C).m()` ou `if (c.x is C)`, em vez de descobrir o problema no binário.
- `Any` deixa de ser um "escape dinâmico" para membro/chamada/índice; continua dinâmico para
  valor. A regra é a mesma do [ADR-0142](0142-check-por-fases.md): não há conversão implícita.

### Negativas / custos

- **Quebra:** programas que passavam no `--check` acessando membro/índice/chamada em `Any`
  agora saem 65. A migração é `is`/`as`. A varredura do corpus, `examples/`, `std/` e
  `bundled/` encontrou **zero** ocorrências antes da regra.
- A suíte oficial do livro é dinâmica e a camada de anotação usa `Any` em retornos/parâmetros;
  10 positivos passam a ser bloqueados pelo checker. O oráculo de runtime do livro continua
  verificado com `Loxia(check_on_run=False)` (`CHECK_BLOCKED`), e os `--check` desses casos
  ficam `xfail` estrito.
- O backend consulta dois mapas de tipos (armazenamento e fluxo). É a materialização do
  [ADR-0045](0045-narrowing-representacao.md); a regra "o checker é a fonte única" continua
  valendo — o backend não infere nada, só consome o tipo de fluxo publicado.
- Um unbox por uso estreitado adiciona IR (`extractvalue` + checagem de tag); não é hot path
  fora de código que já usa `Any`.

### Neutras

- `E3025` é código novo e estável; `docs/spec/erros.md` é gerado por `make codes`.
- As limitações de `std.jsonrpc` ([ADR-0113](0113-protocolo-stdio-jsonrpc-framing-documents.md))
  e de `expect` ([ADR-0096](0096-testes-biblioteca-e-runner.md)) deixam de ser técnicas; a
  migração da stdlib foi concluída na issue
  [#215](https://github.com/loxia-lang/loxia/issues/215) (`RpcFailure.data` e `Expectation`
  com `Any`).
- O pré-requisito de self-hosting do [ADR-0087](0087-heap-cap-e-self-hosting.md) (classe
  recursiva) não muda; o campo `Any` sai da lista no ADR-0145.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Despacho dinâmico em `Any` (buscar campo/método por nome em runtime) | Exige tabela nome→slot no descritor, mantém o resultado sem tipo estático e contradiz I2; o checker continuaria publicando `Any`, então o programa não teria contrato |
| Declarar as lacunas como `E4001` no lowering, sem mexer no checker | Honesto para I4, mas deixa `if (a is C) { a.m() }` divergindo e mantém `Any` inutilizável para o uso natural de campo; o erro chegaria longe da causa |
| Exigir `as` e **não** honrar o narrowing do checker | O checker estreita `if (a is C)`; recusar mesmo estreitado tornaria `is` inútil para membro e seria uma regra pior que a do ADR-0142 |
| Só a regra de checker, sem unbox no backend | Programa estreitado continua check-limpo e continua emitindo `R1014` no binário (I1); foi exatamente o bug medido |
| Estreitar o tipo de armazenamento do `Any` | O slot é `{tag, payload}` fixo; mudar a representação no meio do fluxo exigiria dois layouts para a mesma variável |

## Como verificar

- `tests/cases/any_narrowing.lx` (diferencial l6): membro, escrita, índice, `List`, `Map`,
  tupla e `len` depois de `is`/`as`, com stdout igual nos dois canais.
- `tests/cases/errors/any_{member,set,call,index}.lx` (`COMPILE_ERRORS`): os quatro `E3025`.
- `tests/test_backend.py::test_i4_check_limpo_nunca_vira_erro_de_tipo_no_lowering` varre o
  corpus e exige que a única recusa de um check limpo seja a lacuna declarada.
- `tests/test_official_suite.py` (`CHECK_BLOCKED`) e `tests/test_official_check.py` (xfail
  estrito) documentam os 10 positivos do livro bloqueados pela regra.
- Revisitar se o despacho dinâmico entrar como feature; nesse caso o `E3025` vira o caminho
  explícito e o `Any` dinâmico precisaria de ADR próprio.

## Referências

- [ADR-0055](0055-l6-any-casts.md) — `Any` boxeado, `is`/`as`.
- [ADR-0059](0059-i4-check-limpo-compila.md) — check limpo compila.
- [ADR-0142](0142-check-por-fases.md) — check obrigatório e modo gradual.
- [ADR-0045](0045-narrowing-representacao.md) — narrowing e tipos de representação.
- [ADR-0079](0079-stdlib-t2.md) — containers em campo e o box de `Any`.
