# ADR-0122 — Contrato de data e instante: milissegundos, tupla civil e `timex` v2

- **Status:** accepted
- **Data:** 2026-11-20
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0029](0029-conversoes-math.md) (números e math),
  [ADR-0036](0036-tuplas-implementacao.md) (tuplas), [ADR-0044](0044-identidade-classe.md)
  (identidade de classe), [ADR-0072](0072-stdlib-batteries.md) (§5 unidades e ambiente),
  [ADR-0119](0119-fs-open-handles-e-erro-de-host.md) (erro de host como `Result`)
- **Implementação:** `std/timex.lx`, `docs/stdlib/timex.md`,
  `tests/cases/std_timex.lx`, `tests/cases/std_timex_v2.lx`, `tests/test_std_timex.py`

## Contexto

O `std.timex` ([`std/timex.lx`](../../std/timex.lx)) resolve bem a parte difícil: as
conversões civil ↔ dias usam os algoritmos de Howard Hinnant, valem para todo o domínio de
`Int`, o `parts` usa divisão por piso (instantes pré-epoch continuam corretos) e o
`parseIsoResult` valida por round-trip, rejeitando `2023-02-29`.

O que ele não resolve é o **contrato**:

- **Três unidades no mesmo `Int`.** `timex` trabalha em segundos desde a época,
  `time.now()` devolve **milissegundos** e `daysFromCivil` devolve **dias**. A composição
  mais natural, `timex.iso(time.now())`, estoura `year out of range`; e comparar
  `parseIso(s)` com `time.now()` é sempre verdadeiro, **sem erro**. O [ADR-0072 §5](0072-stdlib-batteries.md)
  registra ms; o código e a página gerada dizem segundos — a decisão registrada e o código
  divergem, e o código é o que roda.
- **Sem validação na construção.** `daysFromCivil(2023, 2, 30)` devolve 2 de março em
  silêncio; só o parse valida. Isso contraria o I2 na prática: um valor impossível vira
  outro valor sem aviso.
- **Sem abstração de data.** Não há data civil como valor, nem `weekday`, `dayOfYear`,
  `isLeapYear`, `daysInMonth`, `addMonths`/`addYears` (calendário, com clamp) ou `diffDays`.
- **Sem offset.** Só `Z`; não há `±HH:MM` no parse nem na formatação, e não há como
  formatar "hora local" sem inventar offset na mão.
- **Sem tipo — e um tipo de classe não é gratuito aqui.** Instâncias comparam por
  **identidade** ([`docs/spec/semantica.md`](../spec/semantica.md)), então `d1 == d2` seria
  falso para a mesma data; e `Map` só aceita `Bool`/`Int`/`String`
  ([`lox_map.py`](../../loxia_core/execution/lox_map.py)), então uma data não indexa mapa.
  Um `Date` classe compraria métodos e pagaria com dois tropeços silenciosos.

Se nada for decidido, cada programa adota a sua convenção (`time.now() // 1000` espalhado),
a divergência com o ADR-0072 continua e toda função nova de data inventa a sua própria
regra de unidade e de validação.

## Decisão

### 1. Milissegundos são a unidade canônica do instante

Todo o `std.timex` passa a receber e devolver **milissegundos** desde
`1970-01-01T00:00:00Z`. `time.now()` já é ms e não muda.

O motivo é o I2: a composição óbvia tem que ser a correta. `timex.iso(time.now())` passa a
funcionar sem conversão, e deixa de existir uma segunda unidade escondida na API.

É uma quebra intencional de uma API T3, nova e sem consumidor interno (nenhum módulo de
`std/` importa `timex`; só `std/proc` usa `time.now()`). A migração é uma linha:
`iso(s * 1000)` para quem tinha segundos. A quebra entra na 1.3 com nota no `CHANGELOG.md`;
não haverá aliases em segundos, porque duas unidades é exatamente o problema que este ADR
resolve.

### 2. Instante é `Int` (ms); data civil é `(Int, Int, Int)`

- **Instante**: `Int` em milissegundos.
- **Data civil**: tupla `(year, month, day)`, covariante e com igualdade estrutural.

Sem classe nesta rodada. A tupla dá igualdade estrutural, destructuring (`val (y, m, d) = t`)
e `match` de graça, custo zero no backend e nenhum valor impossível *criado pelo tipo* — a
validação fica na fábrica (item 3). A classe fica adiada com gatilho explícito: **três ou
mais call sites precisando de método**, ou a decisão de igualdade estrutural para classes
([ADR-0044](0044-identidade-classe.md)) mudar. Quando entrar, entra com `equals`/`compare`
documentados e sem virar chave de `Map`.

### 3. Validação explícita, sem normalizar em silêncio

- `daysFromCivil` continua aritmético e rápido, mas o doc passa a dizer, sem rodeio, que
  **não valida** e normaliza datas impossíveis (é a primitiva de quem já sabe o que faz).
- `date(year: Int, month: Int, day: Int) -> Result[(Int, Int, Int), TimeError]` valida mês
  `1..12`, dia `1..daysInMonth(year, month)` e ano `0..9999`, devolvendo a data civil ou
  `TimeError("invalidDate", ...)`.
- `isLeapYear(year) -> Bool` e `daysInMonth(year, month) -> Int` são públicos: são a base
  da validação e o que um programa de calendário precisa.
- `parseIsoResult` valida com `date` e mantém o round-trip como segunda barreira.

### 4. Operações de calendário

| Função | Contrato |
| --- | --- |
| `weekday(ms) -> Int` | ISO: 1 = segunda … 7 = domingo; piso antes de calcular |
| `dayOfYear(ms) -> Int` | 1..365/366, no calendário civil UTC |
| `addDays(ms, n) -> Int` | dias exatos de 86.400.000 ms |
| `addMonths(ms, n) -> Int` | calendário: preserva a hora e **faz clamp** do dia (31/01 + 1 mês = 28/02; ano bissexto respeita) |
| `addYears(ms, n) -> Int` | calendário, com clamp de 29/02 em ano não bissexto |
| `diffDays(a, b) -> Int` | diferença em **dias civis** (piso), não em períodos de 24 h |

`addMonths`/`addYears` são a razão de existir do módulo: são a operação que "somar 86.400.000
ms" não consegue expressar.

### 5. Formatação e parse

- `iso(ms) -> String` mantém `YYYY-MM-DDTHH:MM:SSZ`, com o instante **truncado para baixo**
  no segundo (então `-1` ms ainda é `…T23:59:59Z`, e a ordem é preservada).
- `isoMillis(ms) -> String` acrescenta `.mmm`; `isoDate(ms) -> String` devolve `YYYY-MM-DD`.
- `parts(ms) -> (Int, Int, Int, Int, Int, Int)` continua a 6-tupla; `partsIn(ms, offsetMinutes)`
  devolve os mesmos campos no offset pedido.
- `isoIn(ms, offsetMinutes) -> String` formata com `Z` quando o offset é 0 e `±HH:MM` caso
  contrário; offset fora de `-720..840` é `RuntimeError`.
- `parseIsoResult(text)` aceita `YYYY-MM-DD`, `YYYY-MM-DDTHH:MM:SSZ` e
  `YYYY-MM-DDTHH:MM:SS[.mmm](Z|±HH:MM)`; rejeita o resto. Offset é aplicado na conversão
  para instante (o instante devolvido é sempre UTC).
- `parseIso(text)` continua o atalho `T?` via `results.toOptional`.

### 6. Offset explícito, nunca banco de fuso

Offset é **parâmetro** de parse e formatação, não um valor guardado: não existe `Zoned`,
nem `DateTime` com fuso, nem tabela IANA. Regra de DST é o que quebra o I3 e não tem
consumidor; um dia, um consumidor real pede um ADR próprio.

### 7. Faixa e erros

- Formatação aceita ano `0..9999`; fora disso é `RuntimeError` (`timex.iso() year out of
  range.`), como hoje.
- Parse de ano é só de 4 dígitos; anos negativos existem no domínio aritmético mas não são
  formatáveis nem parseáveis.
- Falha esperada (texto malformado, data impossível) é `Result`; violação de contrato de
  formatação é `RuntimeError`. É o mesmo padrão do [ADR-0119](0119-fs-open-handles-e-erro-de-host.md).

## Consequências

### Positivas

- A composição com `time.now()` passa a ser correta; some a unidade escondida.
- Data inválida deixa de ser normalizada em silêncio.
- Calendário de verdade (mês/ano com clamp) sem tipo novo e sem custo no backend.
- Nenhuma sintaxe nova; `timex` é Lox puro, então o I1 cobre o módulo de graça.
- O [ADR-0072 §5](0072-stdlib-batteries.md) deixa de estar errado: o código passa a cumprir
  o que já estava registrado.

### Negativas / custos

- Quebra de API na 1.3 (T3, sem consumidor interno, mas é quebra e precisa de CHANGELOG).
- Sem métodos: `timex.addMonths(t, 1)` é mais verboso que `t.addMonths(1)`.
- Data civil não é chave de `Map`; quem precisa agrupar usa `isoDate` como chave.
- Precisão de milissegundo é o teto; não há microssegundo nem nanossegundo.
- `iso` trunca ms; quem quer o instante exato usa `isoMillis` — duas funções donde poderia
  haver uma.
- Um offset mal documentado vira "quase timezone" na cabeça do usuário; a doc precisa ser
  explícita sobre o que não existe.

### Neutras

- `daysFromCivil` continua cru, rápido e sem validação: é a camada de quem implementa
  calendário, não a API de quem escreve relatório.
- O módulo continua UTC-only; a mudança de unidade não muda a semântica civil.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Manter segundos e documentar a divisão por 1000 | A composição com `time.now()` continua errada e o erro é silencioso na comparação; documentar não conserta o I2. |
| `Date`/`DateTime` como classe agora | Igualdade por identidade e `Map` sem chave de data; boxe e superfície sem consumidor que peça métodos. Fica adiada com gatilho. |
| Enum de um variant como record (`enum Date { Of(Int, Int, Int) }`) | Dá igualdade estrutural e `match`, mas a variante é construível com data inválida e o padrão não é óbvio para quem chega. |
| Tipo `Duration` separado | Não há operação que `Int` ms não expresse; mês/ano são calendário, não duração. |
| Banco de timezone (IANA) | I3 (regra muda com o tempo), tamanho e escopo; offset explícito cobre o caso real. |
| Deixar como está e só corrigir a doc do ADR-0072 | Mantém o erro de composição, a normalização silenciosa e a falta de calendário. |

## Como verificar

- `tests/cases/std_timex.lx` migrado para ms e ampliado: bissexto (`2000`, `2024`, `1900`),
  clamp de mês (`31/01 + 1` = `28/02`, `29/02 + 1 ano` = `28/02`), `weekday` de datas
  conhecidas, offset `-03:00`, `parseIso("2024-01-01")`, inválidos (`2023-02-29`,
  `2024-13-01`, `24:00:00`), pré-epoch (`-1` ms) e limites `0`/`9999`/fora.
- Property test (`std.property`): `civilFromDays(daysFromCivil(y, m, d)) == (y, m, d)` para
  datas válidas, e `parseIsoResult(isoMillis(t)) == t` para instantes no domínio formatável.
- `--check` limpo e caso diferencial no backend (`timex` só usa features já baixadas).
- `docs/stdlib/timex.md` regenerado e `ADR-0072` anotado como cumprido por este ADR.

Critério para revisitar: um consumidor que precise de métodos em data (três call sites) ou
a decisão de igualdade estrutural para classes ([ADR-0044](0044-identidade-classe.md));
nesse momento a classe entra sem quebrar as funções.

## Referências

- Howard Hinnant, *chrono-Compatible Low-Level Date Algorithms*.
- [ADR-0072](0072-stdlib-batteries.md) — unidades, ambiente e tiers da stdlib.
- [ADR-0036](0036-tuplas-implementacao.md) — tuplas, igualdade e destructuring.
- [ADR-0044](0044-identidade-classe.md) — identidade de classe.
- [`docs/spec/semantica.md`](../spec/semantica.md) — igualdade e chaves de `Map`.
