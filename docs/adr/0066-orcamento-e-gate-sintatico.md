# ADR-0066 — Orçamento e gate sintático

- **Status:** accepted
- **Data:** 2026-11-13
- **Decisores:** Cassio Dalla (dono do projeto) e agente
- **Relacionados:** [ADR-0014](0014-identidade-e-invariantes.md),
  [ADR-0011](0011-fn-elif-ponto-e-virgula.md),
  [ADR-0013](0013-ternario-nil-aware-escapes.md),
  [ADR-0067](0067-desambiguacao-sintatica.md),
  [`AGENTS.md`](../../AGENTS.md) §1/§4/§7, [`../../TODO.md`](../../TODO.md) §1
- **Implementação:** [`../spec/sintaxe.md`](../spec/sintaxe.md),
  [`../../.dsh/skills/lox-syntax/SKILL.md`](../../.dsh/skills/lox-syntax/SKILL.md),
  `tests/test_docs_consistency.py` (frases defasadas) e os casos golden citados no
  ADR-0067

## Contexto

O portão do [ADR-0014](0014-identidade-e-invariantes.md) julga **semântica**: I1–I4,
LLVM, dor real e teste que policia. Ele não julga **superfície sintática**. O resultado é
que uma feature semanticamente boa ainda pode custar caro em legibilidade: mais uma
grafia para o mesmo conceito, mais um contexto em que a quebra de linha muda o
significado, mais um nível de precedência ou mais um construtor que o parser, o checker,
o backend, o formatter e o LSP precisam entender.

A análise sintática de 2026-11-13 mediu o estado da linguagem:

| Métrica | Valor |
| --- | --- |
| palavras-chave | 25 |
| níveis de precedência | 19 (18 de operadores + primário) |
| formas de statement | 9 |
| formas de declaração | 5 |
| construções sensíveis a newline | ~6 |
| grafias canônicas por conceito | 1 (regra, com exceções documentadas) |

**O que conta como palavra-chave:** todo lexema de `KEYWORDS` **menos** os literais
(`true`, `false`, `nil`) e as reservas sem sintaxe (`async`, `await`). Hoje são 30
lexemas − 5 = **25**; a conta é verificada por
`tests/test_docs_consistency.py::test_scoreboard_de_keywords_bate_com_keywords`. `not`
entrou em 2026-11-13 ([ADR-0068](0068-not-substitui-bang.md)); sem essa regra explícita o
teto não era verificável.

O número de features não é o problema: o custo está em **grafias duplicadas** e em
**ambiguidade local**. O projeto já recusou o alias `fun` ("duas grafias para a mesma
declaração só aumentariam a superfície", ADR-0011) e o elvis `?:` (ADR-0013). Falta
transformar esse instinto em regra escrita — e impedir que um agente, ao implementar uma
feature, amplie a linguagem por conta própria.

## Decisão

### 1. O gate sintático

Toda **adição ou mudança de sintaxe** precisa passar por quatro perguntas antes de
qualquer código:

1. **Substituição** — a sintaxe nova substitui uma grafia existente, vem da stdlib, ou
   adiciona uma segunda forma de dizer a mesma coisa? Só a primeira e a segunda passam
   sem justificativa forte.
2. **Decidibilidade local** — o parser decide sem lookahead arbitrário, sem depender de
   newline fora das regras já documentadas e sem contexto de statement? Se depende,
   precisa de um argumento explícito e de um caso negativo.
3. **Precedência** — cabe na tabela atual ou cria um nível novo? Nível novo exige
   justificativa e testes de AST.
4. **Forma canônica** — existe **uma** forma de escrever? Se o parser aceita duas, qual é
   a canônica e como o style guide/formatter a impõe?

Além disso, a mudança precisa de **dor real** (caso no corpus ou programa concreto), de
**teste que a policia** e de **impacto declarado** no backend LLVM (I1/I4). Sem isso, a
resposta é não.

### 2. O agente pergunta antes

Agente **não** adiciona sintaxe por iniciativa própria, mesmo que a feature pareça
pequena ou "obviamente útil". O procedimento é:

1. apresentar a proposta com as quatro respostas, o custo no scoreboard e a alternativa
   via stdlib;
2. esperar a decisão humana;
3. se aceita, registrar ADR + spec + golden + entrada na skill; se recusada, registrar em
   [`../../IDEIAS.md`](../../IDEIAS.md) ou `TODO.md` §11, **não** em ADR.

Diagnóstico melhorado (mensagem dirigida, sem mudar a gramática) não conta como sintaxe
nova e pode ser feito direto — mas ainda ganha caso de teste.

### 3. Orçamento e tetos

Os tetos são um alarme, não uma proibição absoluta: ultrapassar exige ADR que revise o
orçamento.

| Métrica | Teto | Revisão |
| --- | --- | --- |
| palavras-chave | 28 | ADR |
| níveis de precedência | 19 | ADR |
| formas de statement | 12 | ADR |
| formas de declaração | 6 | ADR |
| construções sensíveis a newline | não crescer | ADR |
| grafias por conceito | 1 | exceção documentada no ADR da feature |

### 4. Não-objetivos

Recusados por padrão; reabrir exige ADR e dor demonstrada:

- `//` como comentário (colide com divisão inteira);
- `?:` (o ternário `a if c else b` existe);
- `&&`/`||` (o `and`/`or` existe; `not` cobre a negação — [ADR-0068](0068-not-substitui-bang.md));
- `++`/`--` (o `i = i + 1` existe);
- `switch` (o `match` existe);
- declaração estilo C (`int (*f)(int)`) e conversão implícita;
- argumentos nomeados, extension methods, operator overloading e trailing closure antes
  do LLVM MVP (já no portão do ADR-0014);
- duas grafias para a mesma declaração (o precedente é o `fun` recusado);
- parênteses opcionais na condição do `if` — exigiria regra de newline nova (ou `then`)
  para separar condição e corpo e manteria duas grafias do mesmo `if`;
- corpo de expressão em `fn` (`fn f(x) -> x * 2`) — segunda forma de corpo, e o `->`
  fica ambíguo com tipo-tupla (`-> (A, B)`) e com corpo de bloco (`-> Ident {`);
- bloco como expressão — `{` já é bloco, mapa e braço de `match`; "último valor
  implícito" contraria o I2;
- `loop { }` — duplica `while (true)`, mesma lógica de `++`/`--`;
- `match` estrutural sobre uniões — exige tipos em runtime (*witnesses*), contra o
  erasure do [ADR-0040](0040-generics-classes-desenho.md) e do [ADR-0041](0041-enums-match.md);
- `!` como negação — substituído por `not` ([ADR-0068](0068-not-substitui-bang.md)).

### 5. Onde a regra mora

- [`AGENTS.md`](../../AGENTS.md) §1 (portão), §4 (convenções), §7 (DoD) e §11 (onde
  decidir);
- skill `lox-syntax` (procedimento operacional);
- `tests/test_docs_consistency.py` (frases que já foram verdadeiras e hoje mentem);
- este ADR (a decisão).

## Consequências

### Positivas

- A linguagem cresce por **capacidade** (stdlib, tipos, backend) sem crescer
  proporcionalmente em gramática.
- O parser continua decidível localmente; formatter, LSP e backend não herdam contextos
  novos sem decisão explícita.
- O agente para de "melhorar" a sintaxe por conta própria: a autonomia fica na
  implementação, não na expansão da superfície.
- Recusar fica barato e registrado: a lista de não-objetivos evita rediscutir o mesmo
  pedido a cada sessão.

### Negativas / custos

- Features ergonômicas legítimas vão demorar mais (ou serão recusadas).
- Os tetos são julgamento; podem envelhecer e precisam de revisão com ADR.
- Exceções como `fn` opcional em método (ADR-0067) mostram que "uma grafia" é regra com
  exceção documentada, não dogma.

### Neutras

- O scoreboard é uma fotografia; atualize quando a decisão mudar, não a cada feature.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Deixar caso a caso, sem gate | Foi o que produziu as dívidas do ADR-0067; decisão fica invisível e o agente não sabe perguntar. |
| Limitar o número de features | O limite errado: capacidade deve poder crescer na stdlib sem tocar na gramática. |
| Copiar a gramática de outra linguagem | Importa também os defeitos (precedência de bits do C, `?:` aninhado, `switch` com fallthrough). |
| Só confiar no ADR-0014 | O portão é semântico; não mede newline, precedência nem grafia duplicada. |

## Como verificar

- `AGENTS.md` §1/§4/§7/§11 e a skill `lox-syntax` existem e citam este ADR.
- Toda mudança de sintaxe futura cita o checklist das quatro perguntas no ADR da feature.
- `tests/test_docs_consistency.py` continua verde, incluindo as frases defasadas.
- Revisitar o orçamento quando uma dor real não couber nos tetos; nesse caso, ADR de
  revisão, não exceção silenciosa.

## Referências

- [ADR-0014](0014-identidade-e-invariantes.md) — identidade e portão de admissão.
- [ADR-0011](0011-fn-elif-ponto-e-virgula.md) — precedente de recusar alias.
- [ADR-0013](0013-ternario-nil-aware-escapes.md) — precedente de recusar elvis.
- [ADR-0067](0067-desambiguacao-sintatica.md) — primeira aplicação do gate.
