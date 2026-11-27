# TIPOS — pendências de tipos

Só o que ainda está **pendente**. O comportamento atual está em [`docs/spec/`](docs/spec/);
decisões fechadas, em [`docs/decisoes.md`](docs/decisoes.md) e nos [ADRs](docs/adr/). Este
arquivo não descreve o que já funciona.

> Atualizado em 2026-11-21: o backend **L0–L6 + T7** está fechado. O `PENDING` do corpus
> tem **1** caso (`bytes_method_value`, method value sem ABI nativa); não há lacuna de tipo
> no lowering. O que resta abaixo é checker/generics além do MVP ou performance (L7).

## 1. Generics além do MVP

Decididos como adiados no [ADR-0040](docs/adr/0040-generics-classes-desenho.md) e no
[ADR-0107](docs/adr/0107-adiados-e-nao-objetivos.md); cada um exige um programa real e um
ADR próprio:

- métodos genéricos (`fn map[U]`);
- herança de `Box[Int]` e interfaces genéricas;
- `is`/`as` reificado e type application explícita;
- função genérica como valor (`val f = id` continua erro; [semântica](docs/spec/semantica.md));
- recursão polimórfica e variance.

As **constraints** existem em funções (`T: Ord + Num + Interface`,
[ADR-0081](docs/adr/0081-constraints-generics.md)). Constraints em classes/enums/interfaces
estão **adiadas** ([ADR-0107](docs/adr/0107-adiados-e-nao-objetivos.md)): `class C[T: Ord]`
e `enum E[T: Ord]` seguem `E1005`, e interfaces genéricas seguem `E3012`; reabrir com
programa real + ADR e plano de monomorfização.

## 2. Checker

- **Narrowing**: invalidação por raiz, por escrita no caminho (regra de *shape*: o refino de
  tipo do pai sobrevive, o mesmo caminho por outra raiz cai, índice dinâmico cai inteiro), por
  chamada de usuário, `var` capturado e merge de fluxo estão implementados
  ([ADR-0045](docs/adr/0045-narrowing-representacao.md),
  [ADR-0086](docs/adr/0086-narrowing-captura-e-merge.md)). `this.campo` estreita como qualquer
  campo e o diagnóstico de refino derrubado cita a chamada/escrita que o derrubou, a linha e o
  tipo anterior ([ADR-0141](docs/adr/0141-soundness-de-fluxo-do-checker.md), emenda de
  2026-11-26). O **soundness de fluxo** está
  implementado ([ADR-0141](docs/adr/0141-soundness-de-fluxo-do-checker.md)): `break`/`continue`
  terminam o refino pós-laço, `match` faz fork/join por braço e todo nó de AST declara sua
  política de fluxo (teste de cobertura). Restam **escape/aliasing de chamadas, efeitos e CFG
  completo**, declarados fora do escopo atual ([ADR-0032](docs/adr/0032-narrowing-campos-indices.md));
  gatilho no [ADR-0107](docs/adr/0107-adiados-e-nao-objetivos.md): três programas reais **e**
  checker em Loxia (F6 do [ADR-0149](docs/adr/0149-motores-primarios-thir-e-congelamento.md)).
- **Check obrigatório**: o [ADR-0142](docs/adr/0142-check-por-fases.md) liga o check em
  fases — **fases 1–3 implementadas**: `check --gradual`, pre-check do `loxia test` e `run`
  checando no modo gradual antes de executar e bloqueando erro de tipo. Não há escape de
  check; não é lacuna de tipo.
- **Enum genérico em lambda/match**: o tipo esperado é propagado aos braços de `match`
  (inclusive quando o `match` é o corpo de uma lambda ou argumento de chamada) e um contexto
  união (`Result[Int, String]?`) também infere `E`; `Result.Ok(1)` infere do contexto. Uma lambda genérica **sem contexto** (`val g = fn(x) => Result.Ok(x)`) continua
  exigindo anotação/função nomeada, porque lambda genérica como valor segue adiada
  ([ADR-0107](docs/adr/0107-adiados-e-nao-objetivos.md)). Argumento de chamada também
  infere do parâmetro (inclusive `Result[T, E]?`, pelo único enum da união); `T?` contra
  `Int?` já unifica `T = Int`.

## 3. Backend

Sem lacunas de tipo: `L0–L6 + T7` cobre escalares, classes/herança, closures, containers,
tuplas, enums, exceções, `Any`, generics monomorfizados e `T?`. O `PENDING` do corpus tem
**1** caso (`bytes_method_value`: method value é interpreter-only até a ABI nativa;
[`tests/corpus_manifest.py`](tests/corpus_manifest.py)). O próximo passo do backend é **L7**
(passes/benchmarks), não uma regra de tipo.

## 4. Como reabrir

Um item só volta a esta lista com issue de decisão e o portão do
[ADR-0014](docs/adr/0014-identidade-e-invariantes.md); se mexer em sintaxe, também o
[ADR-0066](docs/adr/0066-orcamento-e-gate-sintatico.md). Ao fechar uma lacuna, remova o
bullet e atualize o caso diferencial no mesmo commit.
