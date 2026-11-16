# ADR-0096 — Testes: biblioteca (`std.test`) e runner (`lox test`)

- **Status:** accepted (implementado em 2026-11-16)
- **Data:** 2026-11-16
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0093](0093-cli-agent-friendly-e-reparo.md) (CLI/JSON),
  [ADR-0095](0095-processos-streams-poll.md) (`proc`/`poll`, base do runner em Lox),
  [ADR-0080](0080-interfaces-nominais-implementacao.md) (interfaces para fakes),
  [ADR-0089](0089-stack-trace-de-runtime.md) (trace de diagnóstico; **não** exposto),
  [`../../IDEIAS.md`](../../IDEIAS.md) I-13, `R3` no [`../../TODO.md`](../../TODO.md) §9.1
- **Implementação:** `std/test.lx`, `loxia/test_runner.py` + subcomando `test` em
  `loxia/cli.py`, `tests/test_std_test.py`, `tests/test_test_runner.py`,
  `tests/cases/std_test.lx` (corpus `t3`) e `docs/stdlib/test.md` gerado

## Contexto

O `std.asserts` atual serve contrato de produção (`RuntimeError`), não uma suíte: falta
`describe`/`it`, relatório, skip, filtro e isolamento. A linguagem impõe restrições que
descartam o desenho "de framework" usual:

- **sem reflection/anotação:** não há como descobrir testes em runtime nem `#[test]`;
- **`R3`:** closure guardada em `List[fn]` não é chamável no binário, então registry de
  testes não é portável;
- **classe não aceita constraint:** `<=` dentro de `class Expectation[T]` falha no
  checker; matchers de ordem precisam ser funções livres com `T: Ord`;
- **`not` é keyword:** não dá para ter `.not` como propriedade;
- **`Any` como campo** não existe no backend: `expect(x)` só serve para tipo concreto.

Os probes (I-13) mostram o que **funciona** nos dois motores: `it(name, fn(){...})`
executado na hora, `class TestFailure(Exception)`, `Expectation[T]` com `toBe`, e closure
em global (hook de um nível).

## Decisão

### 1. Duas camadas

- **`std.test`** — biblioteca em Lox puro, determinística: registrar/executar/relatar no
  próprio processo.
- **`lox test`** — runner na CLI: descobre arquivos, roda cada um em subprocesso, agrega.

Os dois são independentes: um arquivo de teste pode ser rodado com `loxia run
tests/foo_test.lx` (chama `t.done()`), e o runner só orquestra.

### 2. `Suite` explícita; `it` executa na hora; sem registry

Módulo não aceita `var` top-level (`E1001`), então o estado não pode morar em
`std.test`: ele vive em `val suite = t.Suite()`. `suite.it(name, body)` incrementa o
contador, executa `body()` imediatamente e captura a exceção por teste, imprimindo TAP:

```lox
import std.test as t

val suite = t.Suite()
suite.describe("soma", fn() {
  suite.it("inteiros", fn() { t.expect(1 + 1).toBe(2) })
  suite.it("skip", fn() { suite.skip("sem rede") })
})
suite.done()
```

```
ok 1 - soma inteiros
not ok 2 - divide por zero
  # expected 3, got 4
1..2
```

Ordem = ordem do fonte (determinística). Sem `List[fn]` (R3), sem descoberta em runtime.
`describe` empilha só o prefixo do nome (uma `List[String]`), não closures.

### 3. Asserções híbridas

- `expect[T](value) -> Expectation[T]` com `toBe`/`notToBe` (igualdade universal, serve
  para escalares, strings, listas, mapas, tuplas);
- funções livres para o resto, porque precisam de constraint ou de tipo específico:
  `expectGt[T: Ord]`, `expectGe`, `expectLt`, `expectLe`, `expectNil[T](T?)`,
  `expectNotNil[T](T?) -> T`, `expectList[T](List[T])` com `toContain`,
  `expectString(s)` com `contains`, `expectRaise(fn() -> Nil) -> String`;
- `fail(message)` é livre; `skip(reason)` é método da `Suite` (marca `skipRequested` e
  levanta `Skip`), porque a `Suite` guarda o estado do teste atual;
- `class TestFailure(Exception)` e `class Skip(Exception)` separados de `RuntimeError`
  (o runner distingue falha de teste de bug de infraestrutura).

Sem matcher fluente completo (uma classe por tipo); sem `.not` (keyword).

### 4. Runner em Python agora, Lox depois

`lox test [paths]` em Python (stdlib só), com:

- descoberta: `tests/**/*_test.lx` (ou os caminhos passados) — **só** esse padrão;
- **um subprocesso por arquivo** (`loxia run <file> -- <flags>`): `os.exit`, panic ou
  stack overflow de um teste não matam a suíte; `--timeout` é por arquivo;
- `--filter SUB` e `--only NAME` repassados como `-- --filter=...`; a lib ignora o que não
  casa;
- `--jobs N` (arquivos em paralelo), `--fail-fast`, `--json`, `--native` (compila e roda o
  binário);
- `--json`: envelope estável (`schema_version`, `tests[]` com `file`, `name`, `status`,
  `message`), **sem duração/timestamp** por padrão (I3);
- exit code: 0 se todos passaram, 1 se algum falhou, 2 para erro do runner (path inválido).

O runner em Lox (dogfooding com `proc` + `poll`) fica para quando houver uso real; a lib já
roda nos dois motores, então o custo de trocar é só o orquestrador.

### 5. Mocks: `Recorder` na lib; fakes no usuário

Sem reflection não há monkey-patching. Os padrões suportados:

1. **injeção por função** — a produção recebe `fn(...) -> ...`; stub é closure, spy é
   closure que grava num `Recorder`;
2. **interface + fake** — `interface Mailer` + `class FakeMailer implements Mailer`
   (ADR-0080), com `List[...]` para as chamadas;
3. **fake de capacidade** — a produção recebe `fn(List[String]) -> Output?`,
   `fn(String) -> String?`, `fn() -> Int`; o teste devolve `Output`, mapa em memória ou
   relógio fixo.

`std.test` só shipa `Recorder` (`record`, `count`, `order`, `clear`). Fakes específicos
(clock, runner, fs) ficam no usuário para não acoplar a lib a `proc`/`fs`/`time` nem criar
dependência de teste no código de produção.

### 6. Encerramento

`report() -> Int` imprime plano/resumo e devolve o código de saída (puro, testável);
`done()` é o atalho `os.exit(report())`. O runner usa o exit code do processo.

### 7. Localização de falha fica para depois

O trace de diagnóstico ([ADR-0089](0089-stack-trace-de-runtime.md)) existe, mas não é
exposto à linguagem: exceção capturada só tem `message`. No MVP o relatório aponta
**arquivo + nome do teste + mensagem**. Expor `e.trace` (frames nome/arquivo/linha/coluna)
é feature própria — mexe no checker (campos em `Exception`), no tree-walk e no backend —
e entra depois, quando a linha do `expect` doer de verdade.

## Nota de implementação: exceção de classe de módulo

O `suite.skip` usa um campo (`skipRequested`) em vez de `except Skip` porque o backend
**não casa** `except` de uma classe definida em módulo: o loader reescreve o nome para
`modulo$Classe` e o descritor guarda o nome simples, então `lox_exception_matches` compara
strings diferentes (o interpretador casa por objeto). O bug é anterior a este ADR e está
registrado como `R4` no [`../../TODO.md`](../../TODO.md) §9.1, com teste `xfail`; quando
for corrigido, `suite.skip` pode voltar a ser um `except Skip` normal.

## Consequências

### Positivas

- Testável hoje nos dois motores, sem sintaxe nova e sem reflection.
- Um teste que chama `os.exit` ou estoura a pilha não derruba a suíte (subprocesso).
- A lib não depende de `proc`/`fs`/`time`; o runner não depende do backend nativo.
- TAP + JSON dão relatório para humano, CI e agente sem inventar formato.

### Negativas / custos

- Sem `beforeEach`/`afterEach` aninhados (R3); no MVP, no máximo um hook global.
- Sem localização de linha no relatório até expor trace; o nome do teste é o elo.
- Um processo por arquivo: arquivo com muitos testes paga o boot uma vez; isolamento por
  teste só com `--only` + N processos (depois).
- `std.test` vira API pública com regras próprias (`TestFailure`/`Skip`) que precisam de
  doc e teste de compatibilidade.
- Matchers de ordem em funções livres: menos "bonito" que `expect(3).toBeGreaterThan(2)`.

### Neutras

- `std.asserts` não muda (continua `RuntimeError`).
- O corpus dourado (`tests/runner.py`) não muda; `lox test` é para testes de usuário.
- Testes que usam `proc`/`fs`/`time` são `ambient` e ficam fora do corpus I1.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Fluente completo (`IntExpectation`, `ListExpectation`, …) | Duplica matchers e cresce a superfície; constraints não cabem em classe. |
| Só funções livres (`expectEq`, …) | Menos parecido com o que as pessoas conhecem; `expect(x).toBe(y)` é o núcleo barato. |
| Registry de closures / anotação `#[test]` | R3 (não chama no binário) e sintaxe nova (gate ADR-0066). |
| Runner em Lox desde o início | Mais lento e depende de `proc` estável; o orquestrador é a parte menos arriscada. |
| Fakes prontos em `std.test` | Acopla a lib a capacidades e coloca dependência de teste no código de produção. |
| `done()` com exit embutido | A lib controlaria o processo e o resumo não seria reutilizável. |
| Expor trace agora | Atrasa o MVP e mexe nos dois motores por polish de relatório. |

## Como verificar

- `uv run pytest tests/test_std_test.py` — `Suite`/`describe`/`it`/matchers/skip/`report`
  em interpretador e binário; TAP byte a byte.
- `uv run pytest tests/test_test_runner.py` — descoberta, isolamento (`os.exit`), timeout,
  filtro, `--jobs`, `--json`; projeto temporário.
- `tests/cases/std_test.lx` no corpus `t3` (subconjunto determinístico), já no
  diferencial (`pytest tests/test_backend.py -k std_test`).
- `make check` verde; `make bench` se o runner entrar em caminho quente (não entra).
- **Critério para revisitar:** necessidade de hooks aninhados/isolamento por teste
  (`R3`/`--only`), ou de linha no relatório (`e.trace`).

## Referências

- [`../../IDEIAS.md`](../../IDEIAS.md) I-13 — desenho e probes.
- [`../../TODO.md`](../../TODO.md) §9.1 (`R3`) e §13.6 (`std.test`).
- TAP (Test Anything Protocol) — <https://testanything.org/>
