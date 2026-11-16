# ADR-0072 — Stdlib: kernel nativo, biblioteca em Lox e política de batteries

> **Atualizado por** [ADR-0078](0078-nome-loxia-extensao-lx.md): o `LoxRuntimeError` do
> prelúdio passou a se chamar `RuntimeError`. O corpo abaixo é o registro histórico da decisão
> da época.

- **Status:** accepted (plano; implementação pendente)
- **Data:** 2026-11-14
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0014](0014-identidade-e-invariantes.md) (portão de admissão),
  [ADR-0016](0016-api-stdlib-hibrida.md) (API híbrida),
  [ADR-0026](0026-freeze-1.0.md) (freeze), [ADR-0035](0035-strings-texto.md),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md) (gate sintático),
  [ADR-0071](0071-primitivas-de-runtime.md) (primitivas),
  [ADR-0073](0073-imports-modulos.md) (imports), [`../../TODO.md`](../../TODO.md) §13
- **Implementação:** `std/*.lox` (novo), `loxia_core/loader/` (novo), casos em
  `tests/cases/std/`, manifesto em `tests/corpus_manifest.py`

## Contexto

Hoje o prelúdio tem 11 nomes: `chars`, `len`, `range`, `repr`, `str`, `Int`, `Float`,
`math`, `Result`, `Exception`, `LoxRuntimeError`. Não há `io`, `string`, `collections` nem
módulos: o programa é um arquivo só. Para um compilador, uma ferramenta ou um script real,
falta quase tudo.

A tentação é escrever a stdlib como nativas em Python (e depois em C). Isso duplica cada
função — e a duplicação não é de digitação, é de **semântica**: cada nativa precisa de uma
segunda implementação em C, de um teste diferencial manual e de uma decisão de tipo no
checker. A stdlib cresce, a dívida cresce junto, e a divergência é silenciosa.

O caminho oposto funciona: uma função escrita em **Lox** existe uma vez e roda nos dois
motores, então o I1 a cobre de graça. Para isso ela precisa de primitivas baratas
([ADR-0071](0071-primitivas-de-runtime.md)) e de um jeito de organizar código em módulos
([ADR-0073](0073-imports-modulos.md), proposto).

"Batteries included" também tensiona a identidade: o [ADR-0014](0014-identidade-e-invariantes.md)
exige dor real, não simetria com outra linguagem. A resposta é tratar a stdlib como
**capacidade opt-in por `import`**, com critério de admissão por módulo — não como
prelúdio sempre carregado.

## Decisão

### 1. Três camadas, uma implementação por função

| Camada | O que entra | Quantas implementações |
| --- | --- | --- |
| **Kernel** | syscalls e representação (ADR-0071) | Python (oráculo) + C (binário) |
| **std em Lox** | todo o resto | **uma** (o texto Lox) |
| **Módulos** | nomeação e carregamento (ADR-0073) | uma por motor (loader), sem lógica de biblioteca |

Regra de bolso para decidir a camada: se a função precisa de SO, de bytes/pontadores ou
seria assintoticamente pior em Lox, é kernel; caso contrário, é Lox. **Nenhuma lógica de
negócio entra em primitiva** — adaptador Python só converte, corpo C só faz syscall.

### 2. Módulos da stdlib

- Fonte em `std/<module>.lox` na raiz do repositório; nome público `std.<module>`.
- **Plano (um nível):** `std.strings`, `std.lists`, `std.json`; sem submódulos em v1.
- **Só declarações:** `fn`, `class` e `enum`. Sem statement de topo e sem `val` de topo —
  não há ordem de inicialização, não há efeito colateral no `import`, e o `import` é
  puramente estático.
- **Privacidade:** identificador que começa com `_` é privado do módulo; usá-lo de fora é
  erro de `--check`.
- Módulos da stdlib podem importar outros módulos da stdlib; ciclo é erro de compilação.
- O loader lê do **bundle** (`Path(__file__).parents[...]/"std"`), nunca de caminho do
  usuário, env ou CWD. Isso mantém o I3 e impede que o programa mude o que é importado.

### 3. Tiers (o que é "batteries")

| Tier | Módulos | Critério |
| --- | --- | --- |
| **T0 — kernel** | `args`, `io.*`, `os.*`, `time.*`, `substr`, `join`, `charCodeAt`, `fromCodePoint` | syscalls/representação; teto de 15 (ADR-0071) |
| **T1 — núcleo** | `strings`, `lists`, `maps`, `numeric`, `asserts`, `results` | quase todo programa usa |
| **T2 — comum** | `json`, `fmt`, `paths`, `fs`, `io`, `cli`, `sets`, `csv`, `convert` | programa real de CLI/arquivo |
| **T3 — extra** | `timex`, `rand`, `hash`, `collections`, `log`, `test` | conforto; entra com caso de uso |

**Fora da stdlib (não-objetivos declarados):** regex, criptografia (hash criptográfico,
AES), rede/HTTP, subprocesso, async, banco de timezone, locale/i18n, TOML/YAML (JSON
cobre), UUID (precisa de entropia) e inteiros grandes (o `Int` é i64; seria tipo novo, não
biblioteca). Motivos: custo no kernel, risco ao I3 (locale/ordem/tempo) ou escopo que
pertence a um pacote externo futuro.

### 4. Critério de admissão por módulo

Um módulo só entra se tiver **todos**:

1. um programa real (em `exemplos/` ou caso golden) que o use — não simetria com outra
   linguagem;
2. funções marcadas como determinísticas ou ambientes (ver §5);
3. casos golden em `tests/cases/std/<modulo>/` e checagem em `--check`;
4. documentação na spec correspondente quando o módulo estabilizar;
5. **zero sintaxe nova** — se precisar de sintaxe, é ADR-0066, não stdlib.

### 5. Determinismo e ambiente

- Cada função é determinística ou **ambiente**. Ambiente: relógio, stdin, argv, env,
  listagem de diretório, aleatório não semeado.
- Função ambiente nunca aparece no corpus I1; teste usa entrada fixa e não imprime
  caminho absoluto, PID, timestamp nem ordem de diretório.
- `std.timex` é **UTC-only** e trabalha com `Int` (ms desde a época); não há banco de
  timezone. `std.paths` é **POSIX-only** e documentado assim.
- Ordenação é sempre explícita (chave ou comparador); nada depende de ordem de hash.
- `std.rand` é **semeado** (`rand.seed(n)`) e determinístico; sem semente, é ambiente.

### 6. Erros e variádicos

- Falha esperada devolve `T?` (ausência) ou `Result[T, E]` (detalhe). **Nenhuma função da
  stdlib lança exceção na v1** — o backend ainda não tem unwinding (L6j) e a stdlib tem
  que rodar nos dois motores.
- Variádicos existem desde o [ADR-0083](0083-variadicos.md): `fmt.format` recebe
  `...values: Any` e a chamada é `fmt.format("{} + {} = {}", a, b, c)`; `...args`
  (spread) também vale. APIs anteriores que recebiam `List[Any]` mantêm o corpo usando a
  lista, agora ligada ao rest.
- Sem tipo `Bytes`: `base64`/`hex` operam sobre texto (UTF-8) e `List[Int]` de 0..255,
  documentado em `std.convert`.

### 7. Nomes e API

- Módulos no plural (`strings`, `lists`, `maps`) e namespace `std.` — evita colisão com
  os builtins reservados (`str`, `len`, `math`). Por isso é `std.numeric`, não
  `std.math`.
- Segue o modelo híbrido do [ADR-0016](0016-api-stdlib-hibrida.md): função livre para
  operação genérica (`len`, `join`), método só em tipo da linguagem (`xs.push`), namespace
  para biblioteca (`std.strings.split`).
- Nada de `import` implícito nem prelúdio gigante: se o programa não importa, o módulo
  não existe naquele programa.

### 8. Versionamento

A stdlib tem a **versão da linguagem** (hoje 1.0.0); não há registry, semver por pacote
nem carregamento dinâmico. `std` é congelado por release; mudança incompatível segue o
mesmo processo de ADR.

## Consequências

### Positivas

- "Batteries" sem crescer a gramática: o teto do ADR-0066 não é tocado por módulo novo.
- Uma implementação por função; o I1 cobre a stdlib de graça.
- O kernel fica pequeno (≤ 15), o que mantém a duplicação Python×C sob controle.
- A própria stdlib vira o dogfooding que revela features faltantes com dor real.

### Negativas / custos

- Superfície grande: cada módulo exige golden, revisão de determinismo e documentação.
- Depende de imports (ADR-0073, proposto) e de classes em módulo para `std.sets`/
  `std.collections`.
- O interpretador passa a carregar e checar módulos; `import` mal usado encarece o
  startup — mitigação: carregar só o importado, uma vez por programa.
- Nomes como `std.lists.map` são mais verbosos que `map` global; é o preço de não poluir o
  escopo e de não ter injeção implícita.

### Neutras

- Módulos só de declaração eliminam ordem de inicialização; não há "top-level script" na
  stdlib.
- `std.json` e `std.csv` são Lox puro: nenhum parser nativo, nenhuma dependência.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Tudo nativo (Python/C) | Duplica cada função e cria uma obrigação permanente de teste diferencial; é a dívida que o ADR-0071 tenta limitar. |
| Prelúdio único sempre carregado (`std.lox` concatenado) | Serve como fase 0, não como destino: todo programa paga o parse da stdlib inteira e não há como o checker saber o que está em uso. |
| Módulos como valores dinâmicos (`val s = std.strings`, `s["split"]`) | Exige `Any` chamável, apaga tipos e contraria o I2; namespace é estático. |
| `from std.strings import split` / `import *` | Duas formas de dizer a mesma coisa e injeção implícita de nomes; o ADR-0066 exige forma canônica. |
| Pacotes de terceiros/registry na v1 | Escopo e segurança; a stdlib é bundled e congelada. |
| Regex e cripto "porque toda stdlib tem" | Custo alto, risco ao I3 (locale/ordem) e nenhum programa real do projeto usa; ficam fora até doer. |

## Como verificar

- `tests/cases/std/<modulo>/*.lox` com `# expect:` e rodada no interpretador **e** no
  backend pelo manifesto (`k0`/`l6`), quando o módulo usar só features já baixadas.
- `--check` cobre cada assinatura pública; usar `_privado` de fora é caso negativo.
- `bench/cases/std_pipeline.lox` (split → parse → sort → join) para não deixar a stdlib
  quadraticamente pior no interpretador.
- Auditoria de determinismo: nenhum caso do corpus chama função ambiente; as de ambiente
  têm teste próprio com entrada fixa.
- Critério para revisitar: se um módulo precisar de primitiva nova, ela passa pelo teto do
  ADR-0071 primeiro; se precisar de sintaxe, é ADR-0066.

## Referências

- [ADR-0016](0016-api-stdlib-hibrida.md) — modelo híbrido de API.
- [ADR-0014](0014-identidade-e-invariantes.md) — portão de admissão.
- [ADR-0071](0071-primitivas-de-runtime.md) — kernel e complexidade.
- [ADR-0073](0073-imports-modulos.md) — `import std.<modulo>` (proposto).
- [`../../TODO.md`](../../TODO.md) §13 — inventário por módulo e ordem de entrega.
