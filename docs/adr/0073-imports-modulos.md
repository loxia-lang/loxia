# ADR-0073 — Imports: `import std.<módulo>` e módulos só de declarações

- **Status:** proposed (aguarda aprovação humana do gate do
  [ADR-0066](0066-orcamento-e-gate-sintatico.md))
- **Data:** 2026-11-14
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH) — **pendente**
- **Relacionados:** [ADR-0066](0066-orcamento-e-gate-sintatico.md) (gate e orçamento),
  [ADR-0072](0072-stdlib-batteries.md) (stdlib),
  [ADR-0071](0071-primitivas-de-runtime.md) (primitivas),
  [ADR-0020](0020-assinaturas-explicitas.md) (declarações de topo),
  [`../../TODO.md`](../../TODO.md) §13
- **Implementação:** `src/frontend/token_type.py` (`IMPORT`), `src/frontend/parser.py`,
  `src/loader/` (novo), `tests/cases/imports/`

## Contexto

A stdlib do [ADR-0072](0072-stdlib-batteries.md) não cabe em um arquivo: `split`, `map`,
`join` e `parse` colidiriam como globais, e o usuário não teria como saber o que veio de
onde. Sem módulos, "batteries included" vira um prelúdio gigante sempre carregado — que é
o oposto de opt-in.

O `TODO.md` §1 lista namespaces/imports como `P3` e o §8 como "necessário com stdlib".
Este ADR fecha **só a fase A**: módulos da stdlib. Módulos do usuário (arquivos) ficam
para um ADR próprio, com resolução de caminho, ciclos e diagnóstico de arquivo.

Alternativa sem sintaxe: um prelúdio único concatenado. Funciona como fase 0, mas obriga
todo programa a pagar o parse da stdlib inteira, não tem privacidade e não permite ao
checker saber o que está em uso. Fica registrada como paliativo, não como destino.

## As quatro perguntas do gate

1. **Substituição.** Não substitui grafia existente. É capacidade nova exigida pela
   stdlib (ADR-0072) e **não** cria segunda forma de dizer nada: sem `as`, sem `from`,
   sem `*`, sem chaves, sem injeção de nome curto.
2. **Decidibilidade local.** `import` é palavra-chave no início de um statement; a forma é
   `import std . IDENT` (um token de lookahead para `std`). Só é válido no **topo do
   arquivo**, antes de qualquer outro statement. A resolução do módulo é estática, vem do
   bundle, sem tocar o filesystem em runtime. Casos negativos cobrem cada recusa.
3. **Precedência.** Nenhuma: é statement de topo, não expressão. Não cria nível.
4. **Forma canônica.** Uma: `import std.strings`. O binding é o **caminho completo**
   (`std.strings.split`), nunca o nome curto `split` ou `strings`. Import repetido é
   idempotente (não é uma segunda forma).

### Custo no orçamento do ADR-0066

| Métrica | Antes | Depois | Teto |
| --- | --- | --- | --- |
| palavras-chave | 25 | **26** | 28 |
| formas de statement | 9 | **10** | 12 |
| formas de declaração | 5 | 5 | 6 |
| níveis de precedência | 19 | 19 | 19 |
| construções sensíveis a newline | ~6 | ~6 (usa a regra de `;` opcional) | não crescer |
| grafias por conceito | 1 | 1 | 1 |

Cabe no teto. Quando implementado, a linha "palavras-chave | 25" do ADR-0066 vira 26 (o
teste `test_scoreboard_de_keywords_bate_com_keywords` obriga a atualização).

## Decisão

### 1. Sintaxe

```lox
import std.strings
import std.json

fn main() {
  val partes = std.strings.split("a,b,c", ",")
  print std.json.stringify(partes)
}
```

- `import` só no topo, antes de qualquer outro statement (bloco de imports);
- nome de módulo é `std` + um identificador; sem submódulo, sem alias, sem seletor;
- `;` opcional como nos demais statements;
- `std` é **identificador reservado** (não pode ser declarado nem sombreado); nomes de
  módulo importados não são injetados no escopo;
- usar módulo não importado é erro (`module 'std.lists' is not imported`);
- módulo é **namespace de compilação**, não valor: `val m = std.strings` é erro;
- o helper privado (`_x`) de outro módulo é erro.

### 2. Módulos só de declarações

Um módulo `std/<nome>.lox` contém apenas `fn`, `class` e `enum` de topo. **Sem**
statement de topo e **sem** `val` de topo. Consequências, todas desejadas:

- não existe ordem de inicialização nem efeito colateral no `import`;
- o `import` é puramente estático: resolver, checar e desugar;
- `_nome` é privado do módulo; fora dele, erro de `--check`;
- um módulo pode importar outro da stdlib; ciclo é erro de carregamento com caminho
  determinístico na mensagem.

### 3. Implementação: desugar para um programa plano

Import não vira tipo novo nem objeto de runtime. O loader:

1. resolve `import std.x` contra a lista bundled (`std/x.lox`), deduplicando;
2. parseia o módulo uma vez e **mangla** cada declaração com um separador que não é
   lexável em identificador (`std$strings$split`);
3. reescreve as referências `std.strings.split` para o nome manglado;
4. anexa as declarações do módulo ao AST do programa, antes do código do usuário.

O resto do pipeline (resolver, checker, backend) **não sabe que módulos existem**: vê um
programa plano com funções de topo. Por isso:

- nenhuma ABI nova, nenhuma tag de valor, nenhum lowering novo;
- genéricos em módulo instanciam como qualquer função de topo ([ADR-0050](0050-monomorfizacao-t7.md));
- funções não usadas de um módulo importado são emitidas no `-O0` e removidas no `-O2`;
- `--dump-ast` mostra o programa desugarizado (documentado; não é o dump do arquivo
  fonte).

### 4. Diagnósticos

O reporter passa a carregar o **nome da fonte corrente** (pilha de fontes), para que erro
em módulo saia como `std/strings.lox:12: ...` em vez de `[line 12]` ambíguo — sem mudar
`Token` nem o I3 (o nome é relativo e determinístico; caminho absoluto continua proibido).
O loader empilha/desempilha a fonte ao parsear cada módulo.

### 5. Fase B (fora deste ADR)

Módulos do usuário ficam para ADR próprio, com estas restrições já decididas: caminho
relativo ao importador, sem caminho absoluto, sem busca por env/CWD, sem ciclo, só
declarações, e a mesma forma canônica. Não serão `import std.*` — o root será diferente.

## Consequências

### Positivas

- Stdlib organizada e opt-in; o prelúdio não cresce.
- Zero mudança no backend e no ABI: o risco no I1 é baixo.
- Privacidade por `_` e namespace explícito, sem injeção de nomes.
- O caminho de implementação é pequeno (loader + desugar), não um sistema de módulos
  completo.

### Negativas / custos

- Mais uma palavra-chave e mais uma forma de statement (dentro do teto).
- O AST desugarizado pode ficar grande; erro em módulo precisa do nome da fonte para não
  virar `[line 12]` ambíguo — mexer no reporter.
- `import` não é valor: quem quiser passar funções de módulo precisa de um `fn` que as
  embrulhe (limitação declarada).
- Módulos só de declaração impedem constantes de topo (`val PI = ...`); viram `fn pi()`.
- O `-O0` emite funções não usadas dos módulos importados (tamanho de binário).
- Fase B (arquivos do usuário) fica em aberto por mais tempo.

### Neutras

- `std` reservado é a única exclusão nova de nome; builtins continuam sombreáveis em
  escopo local.
- Sem impacto no I1 enquanto os casos de módulo só usarem features já baixadas.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| `import std.strings as s` | Segunda forma do mesmo conceito; o ADR-0066 exige uma grafia. |
| `from std.strings import split` | Injeta nomes no escopo do usuário (colisão e "de onde veio?"), e é segunda forma. |
| `import std.*` | Import implícito de nomes; contraria o I2. |
| `std.strings` disponível sem `import` | Todo programa paga o parse/check de tudo e não há como saber o que está em uso; prelúdio gigante. |
| Módulo como valor (`LoxModule`, `ModuleTy`) | Mais tipos, mais runtime, mais backend; o desugar entrega o mesmo resultado com uma fração do custo. |
| Resolver módulos em runtime pelo filesystem | I3, portabilidade e superfície de erro; a stdlib é bundled. |
| Fase B junto (arquivos do usuário) | Resolução de caminho, ciclos e diagnóstico de arquivo são um ADR inteiro; a stdlib não precisa disso para começar. |

## Como verificar

- Golden: `tests/cases/imports/std_basic.lox` (importa `std.strings` e usa `split`),
  `std_two_modules.lox` (dois imports, ordem trocada, mesmo resultado),
  `std_generic.lox` (função genérica de módulo).
- Negativos: import depois de statement, `import strings` sem `std`, módulo inexistente,
  `val m = std.strings`, `_privado` de fora, ciclo entre módulos, `std` redeclarado.
- `--check` valida as assinaturas públicas dos módulos; `--dump-ast` é documentado como
  desugarizado.
- `tests/test_docs_consistency.py::test_scoreboard_de_keywords_bate_com_keywords` verde
  depois de `import` entrar em `KEYWORDS` (25 → 26) e no ADR-0066.
- **Revisitar** se a fase B exigir outra forma sintática: aí este ADR é estendido ou
  substituído, não emendado em silêncio.

## Aprovação pendente (humano)

1. `import` como palavra-chave e 10ª forma de statement? (cabe no teto)
2. Binding pelo caminho completo (`std.strings.split`) com `std` reservado?
3. v1 só com módulos da stdlib, arquivos do usuário em ADR separado?
4. Módulos só de declaração (sem `val` de topo, sem statement de topo)?

## Referências

- [ADR-0066](0066-orcamento-e-gate-sintatico.md) — gate, orçamento e forma canônica.
- [ADR-0072](0072-stdlib-batteries.md) — o que a stdlib precisa.
- [ADR-0020](0020-assinaturas-explicitas.md) — declarações de topo e ordem.
- [`../spec/sintaxe.md`](../spec/sintaxe.md) — a atualizar quando aprovado.
