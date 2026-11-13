# ADR-0039 — Decisões de tipos pendentes: sufixos, chave Float, Option/Result, alias e throw

- **Status:** accepted
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0006](0006-int-float-separados.md),
  [ADR-0010](0010-tipagem-estatica.md), [ADR-0017](0017-mapas-hash.md),
  [ADR-0026](0026-freeze-1.0.md), [ADR-0029](0029-conversoes-math.md),
  [ADR-0030](0030-tuplas.md), [ADR-0038](0038-traits-nominais.md),
  [`../../TIPOS.md`](../../TIPOS.md), [`../../TODO.md`](../../TODO.md) §11

## Contexto

O `TIPOS.md` ainda listava cinco decisões pequenas, mas soltas: sufixos de literal
(`D-2`), `Float` como chave de `Map`, `Option`/`Result` explícitos, `type` alias e
`throw`/`Never` público. Nenhuma exige implementação grande agora; o custo de deixá-las
abertas é reabrir a mesma conversa a cada feature.

## Decisões

1. **Sem sufixos de literal (`D-2` fechado).** `1` é sempre `Int` (i64) e `1.0` é sempre
   `Float` (f64). Não haverá `1i64`/`1.0f32`: um único tipo inteiro e um único float
   bastam, e `as`/`Int.parse`/`Float.parse` cobrem conversão. Sufixo adicionaria lexer,
   regras de promoção e ruído sem caso de uso.
2. **`Float` não é chave de `Map` — e não há plano de canonicalização.** `Map` exige hash
   consistente com `==`; `1 == 1.0` é `true`, mas os hashes diferem. Canonicalizar números
   dentro da chave (converter `Float` integral para `Int`) quebraria `NaN`/`-0.0`/precisão
   e não paga o custo. Chaves continuam `String`/`Int`/`Bool`; para float, use `String` ou
   `Int` escalado. O checker e o runtime já rejeitam `Map` de chave `Float`.
3. **`Option[T]` é alias de `T?`; `Result[T, E]` será enum/ADT, com T6c.** Não há tipo
   `Option` separado: `T?` já é a representação e evita duas formas de dizer `nil`. `Result`
   (`Ok`/`Err`) só entra junto de enums e `match` exaustivo; até lá, erro é fatal
   ([ADR-0026](0026-freeze-1.0.md)). Não haverá `throw` recuperável e `Result` ao mesmo
   tempo para o mesmo caso: `throw` fica para falha fatal, `Result` para erro esperado.
4. **`type` alias é transparente, não genérico, P3.** `type UserId = Int` será apenas outro
   nome para o mesmo tipo (erased); não cria tipo nominal novo, não tem generics na v1 e
   não muda a identidade de classes. Implementação fica no P3 do `TODO.md`.
5. **`throw` público continua fora da 1.0; `Never` é interno.** Erro de runtime é fatal
   (exit 70); `Never` segue como tipo de fluxo para `return`/loop e para o caminho que
   lança, sem `throw` público. Quando `Result` entrar, `throw` continua reservado a
   invariantes/falhas fatais.

## Consequências

- `TIPOS.md` perde a seção de decisões em aberto: sobra só implementação pendente.
- `docs/decisoes.md` ganha as cinco linhas; `D-2` deixa de existir como pendência.
- `Float` como chave não volta a ser pergunta: a resposta é "não" enquanto `==` numérico
  não tiver canonicalização (e não há planos).
- `type` alias e `Result` ficam no `TODO.md` com escopo e pré-requisitos explícitos.
- Nenhum código muda neste ADR.

## Alternativas rejeitadas

- **Sufixos de literal:** custo de lexer/checker e nenhuma necessidade com `Int`=i64.
- **Canonicalizar `Float` para chave:** `NaN`, `-0.0` e precisão > 2^53 tornam a relação
  frágil; o ganho não paga.
- **`Option` como tipo próprio:** duplicaria `T?` e criaria duas representações de ausência.
- **`Result` como classe agora:** dependeria de enums depois; o desenho certo é ADT com
  `match`.
- **Alias nominal:** `UserId` como tipo distinto exigiria conversão explícita e não é o
  que "alias" significa; fica transparente.
- **`throw` recuperável:** mistura com `Result` e com o modelo fatal da 1.0.
