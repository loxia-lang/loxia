# ADR-0092 — Estilo e formatter: convenções, perfil e dogfood

> **Implementação parcial (2026-11-16):** `docs/guia-estilo.md` e `lox fmt` mínimo
> (indentação de bloco, `;` de fim de linha, newline final, preservação de strings/
> comentários), `fmt --check`/`--stdin` e testes de idempotência. Pendentes: inserir
> `fn` em método, trailing comma, reflow, paridade Lox após a T3.

- **Status:** accepted (implementação parcial)
- **Data:** 2026-11-15
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0066](0066-orcamento-e-gate-sintatico.md) (forma canônica e gate),
  [ADR-0011](0011-fn-elif-ponto-e-virgula.md) (`fn`/`;` opcionais),
  [ADR-0067](0067-desambiguacao-sintatica.md) (desambiguação),
  [ADR-0091](0091-doc-comments-e-geracao-de-docs.md) (doc comments),
  [ADR-0093](0093-cli-agent-friendly-e-reparo.md) (subcomando `fmt`),
  [`../../TODO.md`](../../TODO.md) §7, §10, §13.7
- **Implementação:** `docs/guia-estilo.md`, `loxia/formatter.py` (referência Python),
  `loxia/cli.py` (`fmt`), `tests/test_formatter.py` (idempotência/check/stdin) e
  `docs/spec/lexico.md`/grammar para doc comments. Pendentes: `fn`/trailing comma/
  reflow e o dogfood Lox após a T3.

## Contexto

O [ADR-0066](0066-orcamento-e-gate-sintatico.md) exige **uma forma canônica** para cada
construção e manda o style guide/formatter impor o que o parser aceita em duas formas
(`fn` opcional em método, `;` opcional). O TODO §7 já pede `lox fmt` com teste de
idempotência; o §13.7 passo 7 planeja `lox fmt` em Lox **depois da T3**, seguido do
front-end self-hosted; o §10 registra o parser + AST printer em Lox.

O código atual não é consistente: a stdlib usa 2 espaços, `camelCase` para funções,
`PascalCase` para tipos/variantes, **sem** `;` e `fn` em métodos; exemplos antigos usam
`;` e omitem `fn` em métodos. O style guide precisa decidir o que é norma e o formatter
precisa de um subconjunto que consiga impor sem reescrever semântica.

## Decisão

### 1. Guia normativo

As regras abaixo são o **guia de estilo** (documento normativo `docs/guia-estilo.md` a
criar na implementação). O formatter impõe o subconjunto mecânico; **nomes não são
renomeados** — isso é revisão e, no futuro, lint/aviso (ADR-0093).

#### Nomes

| Construção | Convenção | Exemplo |
| --- | --- | --- |
| classe, interface, enum, type alias | `PascalCase` | `Result`, `Shape`, `UserId` |
| função, método, lambda nomeada, variável, parâmetro, campo | `camelCase` | `isEmpty`, `transform`, `items` |
| **enum de constantes** (todas as variantes sem payload) | variantes `UPPER_SNAKE` | `Cor.AMARELO` |
| **enum soma** (alguma variante com payload) | **todas** as variantes `PascalCase` | `Result.Ok`, `Shape.Circle` |
| parâmetro de tipo | uma letra maiúscula (`T`, `K`, `V`, `E`, `U`) | `Box[T]` |
| membro privado | prefixo `_` | `_isSpace` |
| arquivo/módulo | `snake_case.lx` | `std/json.lx`, `meu_modulo.lx` |

- A regra de enum é **por enum**, não por variante: `Result` (payload) fica `Ok`/`Err`;
  `Cor` (sem payload) fica `AMARELO`/`VERMELHO`. Enum misto é soma e usa `PascalCase`.
- `UpperCamel`/`snake_case` em funções/vars não é canônico; a stdlib atual já segue
  `camelCase`.
- `UPPER_SNAKE` é reservado a variantes de enum constante; `val`/`var` usam `camelCase` mesmo
  quando são constantes de módulo.
- Identificadores públicos da stdlib/builtins são em inglês (AGENTS §4; ADR-0091 para docs);
  código de usuário pode usar o idioma do domínio.
- Código existente com variantes `PascalCase` em enum de constantes (ex.: `Status.Ativo`
  em testes) **não é renomeado automaticamente**; a norma vale para código novo e a
  migração é oportunista. `Result.Ok` continua canônico (enum soma).

#### Formatação

| Regra | Canônico |
| --- | --- |
| codificação/linhas | UTF-8, LF, newline final, sem espaços no fim da linha |
| indentação | **2 espaços**, nunca tabs |
| largura | **100 colunas**; strings/imports/doc podem exceder (não quebrar string) |
| chaves | K&R: `{` na mesma linha; `}` sozinho; `} elif (c) {`, `} else {` |
| `;` | **omitido** no fim de linha; duas instruções na mesma linha não são canônicas (o formatter preserva o `;` e não divide a linha na fase 1) |
| `fn` em método | **mantido** (`fn metodo(...)`), canônico; topo exige `fn` |
| aspas | `"` duplas; raw/multilinha só quando necessário |
| vírgulas | trailing comma em lista/mapa/tupla/params/call multiline |
| linhas em branco | 1 entre declarações/membros; no máximo 2 entre seções; nenhuma imediatamente após `{` ou antes de `}` |
| imports | topo, antes de declarações (loader); grupos std → locais; **sem reordenar** na fase 1 |
| comentários | `#` para implementação; `///` para doc (ADR-0091); `/* */` para bloco/desabilitar |
| `match` | um braço por linha, `=>`, sem vírgula |
| literais | sem espaço interno em `[]`/`{}`; `{ chave: valor }` com espaço depois de `:` |

#### O que o formatter **não** faz

- Não renomeia identificador, não muda tipo, não reordena imports/declarações, não altera
  string/número, não remove código, não avalia nada.
- Não reflow de linhas longas na fase 1 (quebras existentes são preservadas).
- Não formata o conteúdo da doc/comentário além de normalizar `///`/indentação (ADR-0091).

### 2. Contrato do formatter

- **Determinístico e idempotente**: `fmt(fmt(x)) == fmt(x)`; mesmo input ⇒ mesmos bytes.
- **Preserva comportamento**: o programa antes e depois produz o mesmo stdout/stderr/exit
  (o teste roda os dois no interpretador; no backend quando aplicável).
- **Preserva comentários e doc**, inclusive posição relativa; comentário não pode sumir.
- **Sem alteração semântica**: só tokens de formatação (espaços, linhas, `;` opcional,
  `fn` canônico em método, vírgulas/blank lines do subconjunto).
- **Fase 1 (minimal)**: normaliza espaços/indentação, linhas em branco, `;` de fim de
  linha, insere `fn` em método sem `fn`, trailing comma multiline e newline final;
  **preserva** quebras de linha, posição de chaves e ordem.
- **`fmt --check`**: não escreve; exit **1** se o arquivo mudaria, 0 se está canônico; a
  saída humana/JSON lista os arquivos (o CLI decide o formato).
- **`fmt`**: escreve o resultado; `--stdin` lê de stdin e escreve em stdout (ADR-0093).
- Sem opções de estilo/configuração na v1: um perfil canônico. Config por projeto fica
  fora (evita fragmentação).

### 3. Duas fases e dogfood

1. **Python agora** (referência): em `loxia_core/fmt.py`, reusando o scanner (com
   comentários/doc preservados) e o parser/AST para estrutura. É o comando `lox fmt`
   shipped. Golden pairs + idempotência + equivalência de execução.
2. **Lox depois da T3**: parser + AST printer na própria linguagem (TODO §10/§13.7),
   produzindo **bytes idênticos** ao Python em `std/`, `tests/cases/` e `exemplos/`. O Lox
   é dogfood/conformance; o Python continua o comando até a paridade. Depois disso, um
   ADR/flag decide o default (`--engine=py|lox` ou troca), com o Python como oráculo.
3. O formatter Lox **não** é pré-requisito do formatter Python; não bloqueia T3 nem o CLI.
   Ele depende do parser self-hosted, que é o exercício maior.

Bootstrap: se o Lox virar o comando shipped, `lox fmt` precisará executar um programa
Loxia (interpretador/binário embarcado). Isso não é decidido agora; o default continua
Python e a troca exige ADR próprio.

### 4. Onde a norma vive

- `docs/guia-estilo.md` — norma para humanos (nomes, formatação, imports, comentários,
  exemplos). Página de documentação, não spec de comportamento.
- Este ADR — decisão, escopo do formatter, fases e critérios.
- O formatter — implementação do subconjunto; `tests/test_fmt.py` policia o contrato.
- Naming não é policiado pelo formatter; um lint/aviso de naming fica para depois
  (ADR-0093, warnings), se doer.

## Consequências

### Positivas

- Uma forma canônica escrita e testada; o parser pode continuar aceitando `fn`/`;`
  opcionais sem ambiguidade de estilo.
- `lox fmt` cedo dá valor e cria o oráculo para o dogfood em Lox.
- Regras de nomes resolvem `cor.AMARELO` sem quebrar `Result.Ok`.
- Idempotência + equivalência de execução dão confiança para formatar o repo inteiro.

### Negativas / custos

- O formatter minimal não entrega o visual final (K&R/line wrapping) na fase 1; a norma
  fica à frente da ferramenta.
- `fn` canônico em método gera churn nos exemplos/testes que o omitem.
- A fase Lox é L/XL e depende do parser self-hosted; o dogfood pode demorar.
- Um formatter que preserva comentários exige o scanner reter comentários/doc; é mais
  trabalho do que um pretty-printer de AST.
- Sem config, projetos com estilo próprio não têm escape (é intencional).

### Neutras

- Formatação não muda I1/I4; o teste de equivalência é comportamental.
- O guia não renomeia código existente; a migração é incremental.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Só Lox depois da T3 | Sem formatter até lá e sem oráculo; o Lox fica mais difícil de validar. |
| Só Python | Não dá o dogfood que o TODO §13.7 quer. |
| Lox como comando desde já | Bootstrap (como `lox fmt` executa Lox) e paridade sem referência. |
| Full reflow já | Muito caso de borda (comentários, strings, lambdas) antes de ter o básico. |
| Preservar escolhas do autor | Não é forma canônica; o ADR-0066 exige uma. |
| 4 espaços/88 col | Destoa dos fontes Loxia atuais; o Python do repo não é o estilo da linguagem. |
| Formatter renomeia | Renomear é refactor semântico/risco; nomes são guia/lint, não formatter. |
| Config por projeto (`.loxiafmt`) | Fragmenta estilo antes de haver demanda; reavaliar com usuários. |

## Como verificar

- `uv run pytest tests/test_fmt.py` — golden pairs, idempotência (`fmt(fmt(x))`), comentários/
  doc preservados, `;`/`fn` canônicos, newline final, CRLF→LF.
- Teste de equivalência: rodar o programa antes/depois no interpretador (stdout/stderr/
  exit idênticos); no backend quando o caso for compilável.
- `uv run main.py fmt --check std/ exemplos/` limpo depois da migração; CI roda `--check`.
- Dogfood Lox: `fmt --engine=lox` (ou ferramenta de conformance) comparado byte a byte com
  o Python no corpus.
- `make check`; `make bench` não é necessário (formatter é offline), mas medir em `std/`.
- Critério para revisitar: necessidade de reflow/config; dogfood Lox empatar; naming lint.

## Referências

- [`../spec/sintaxe.md`](../spec/sintaxe.md) — sintaxe e formas opcionais.
- [`../../std/`](../../std/) — estilo atual da stdlib.
- [`../../exemplos/`](../../exemplos/) — exemplos com `;`/`fn` antigos.
- [`../../TODO.md`](../../TODO.md) §7, §10, §13.7.
- gofmt/rustfmt — formatter canônico, sem config, idempotente (inspiração).
