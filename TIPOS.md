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
[ADR-0081](docs/adr/0081-constraints-generics.md)); faltam constraints em classes/enums.

## 2. Checker

- **Narrowing**: invalidação em chamada/atribuição a campo/índice, `var` capturado e merge
  de fluxo estão implementados ([ADR-0045](docs/adr/0045-narrowing-representacao.md),
  [ADR-0086](docs/adr/0086-narrowing-captura-e-merge.md)). O **soundness de fluxo** está
  implementado ([ADR-0141](docs/adr/0141-soundness-de-fluxo-do-checker.md)): `break`/`continue`
  terminam o refino pós-laço, `match` faz fork/join por braço e todo nó de AST declara sua
  política de fluxo (teste de cobertura). Restam **aliasing, efeitos e CFG completo**,
  declarados fora do escopo atual ([ADR-0032](docs/adr/0032-narrowing-campos-indices.md));
  gatilhos no [ADR-0107](docs/adr/0107-adiados-e-nao-objetivos.md).
- **Check obrigatório**: o [ADR-0142](docs/adr/0142-check-por-fases.md) liga o check em
  fases — a **fase 1 está implementada** (`check --gradual` e pre-check do `loxia test`);
  a fase 2 (`run` checando e bloqueando) é trabalho aberto, não uma lacuna de tipo.
- **Enum genérico em lambda/match**: `fn(x) => Result.Ok(x)` ainda exige função nomeada
  com retorno anotado para inferir `U`/`E`; `T?` contra `Int?` já unifica `T = Int`.

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
