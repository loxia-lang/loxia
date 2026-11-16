# ADR-0091 — Documentação: doc comments `///`, formato e geração

- **Status:** accepted (plano; implementação pendente)
- **Data:** 2026-11-15
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0066](0066-orcamento-e-gate-sintatico.md) (gate sintático),
  [ADR-0075](0075-diagnosticos-estruturados.md) (diagnóstico; `help`/`labels`),
  [ADR-0090](0090-lsp-escopo-e-hospedagem.md) (hover), [ADR-0016](0016-api-stdlib-hibrida.md)
  (API da stdlib), [ADR-0072](0072-stdlib-batteries.md) (batteries),
  [`../../TODO.md`](../../TODO.md) §10 e §14.2, [`../../IDEIAS.md`](../../IDEIAS.md) I-4
- **Implementação (a criar):** `loxia_core/frontend/scanner.py` (doc comments),
  `loxia_core/frontend/parser.py` e nós de AST (`doc`), `loxia_core/frontend/ast_printer.py`,
  `loxia/cli.py` (`doc`), `docs/stdlib/` gerado, `editors/` (grammar), `tests/test_docs.py`.
  Nada implementado neste ADR.

## Contexto

Hoje a linguagem tem só comentários livres: `#` até o fim da linha e `/* ... */` aninhado
([ADR-0012](0012-comentarios-divisao-potencia-bits.md)). O scanner os descarta; o parser e
a AST não guardam nada. A stdlib é documentada **à mão** na lista de
[`../spec/semantica.md`](../spec/semantica.md), e os builtins no README/spec. Isso já
mostra o problema: a assinatura vive no código, a descrição vive em outro arquivo, e
qualquer mudança exige editar os dois.

O TODO §10 já registrava a ideia de `lox doc` gerando documentação a partir de comentários
(`##`). A pergunta agora é a forma canônica, o formato e a fonte de verdade para stdlib,
builtins e código de usuário.

Restrições:

- **I1**: documentação é metadado de compilação; não pode alterar runtime, bytecode nem
  stderr.
- **ADR-0066**: uma grafia nova de doc comment é sintaxe nova (lexical) e precisa das
  quatro respostas + aprovação humana.
- **LSP/editor**: hover de código de usuário só existe se a doc estiver no AST/índice de
  símbolos.
- **Determinismo/I3**: doc gerada não pode conter caminho absoluto, timestamp ou ordem
  instável.
- O idioma da spec/ADRs é pt-BR; o código usa identificadores em inglês (AGENTS §4).

## Decisão

### 1. Sintaxe: `///` (doc comment)

Um bloco de linhas consecutivas `///` imediatamente antes de uma declaração vira a doc
dela. `///` é **um lexema novo de comentário**, não uma segunda forma de escrever `#`:

```lox
/// Soma dois inteiros e devolve o resultado.
///
/// ```lox
/// print(add(1, 2))
/// ```
fn add(a: Int, b: Int) -> Int {
  return a + b
}
```

- `#` continua sendo o comentário livre de implementação; `/* ... */` continua para bloco/
  desabilitar. **`/** ... */` não é doc comment** (ver alternativas).
- `///` só é doc quando o bloco precede uma **declaração nomeada** (função/método, classe,
  interface, enum, variante, campo, type alias, `val`/`var` de topo). Local functions/
  classes também podem ter doc; o `lox doc` decide o que é API.
- Linha em branco, outro comentário (`#`) ou uma declaração entre o bloco e o alvo quebram
  o vínculo. Doc órfão é ignorada (o `lox doc` pode avisar no futuro; não é erro de
  compilação).
- A doc é **apagada no runtime/backend**: não entra em código gerado, não muda I1.

### 2. Gate sintático (ADR-0066)

As quatro respostas, com aprovação humana registrada nesta decisão:

1. **Substituição** — `///` não substitui `#` e não é uma segunda forma de escrever um
   comentário comum: é **metadado de documentação**, com consumidor (`lox doc`, LSP hover,
   site). Não há programa válido hoje que use `///` (o scanner atual veria `//` divisão
   seguida de `/`, inválido), então nenhum código existente muda.
2. **Decidibilidade local** — o scanner reconhece `///` antes de `//`; sem lookahead, sem
   contexto de statement e sem depender de newline além da regra "linhas consecutivas
   imediatamente antes da declaração".
3. **Precedência** — não cria nível de expressão; é lexical.
4. **Forma canônica** — `///` é a **única** forma de doc comment; `#` é comentário livre;
   `/** */` é rejeitado para não termos duas formas de doc. O style guide/formatter
   ([ADR-0092](0092-estilo-e-formatter.md)) normaliza o texto.

Orçamento do ADR-0066: não muda keywords (27), níveis (19), formas de statement/declaração
nem construções sensíveis a newline; acrescenta uma **forma lexical de comentário**,
documentada em `docs/spec/lexico.md` e na grammar do editor no commit de implementação.

### 3. Formato e anexação

- **Markdown puro**, sem tags `@param`/`@returns`: os tipos já estão na assinatura; tags
  duplicariam informação e exigiriam parser próprio. Primeira linha é o resumo (usado no
  hover/índice); o resto é Markdown (parágrafos, listas, títulos, cercas de código `lox`).
- Normalização: remover `///` e **no máximo um espaço** seguinte; preservar a indentação
  restante (importante para blocos de código); juntar com `\n`; remover linhas vazias no
  começo/fim; normalizar CRLF para LF.
- No AST, `doc: str | None` nos nós de declaração; o parser anexa o bloco; `--dump-ast`
  pode omitir a doc (não é parte da árvore semântica) e o `AstPrinter` a mostra só se um
  flag futuro pedir.
- A doc não é avaliada nem interpolada: é texto literal (Markdown), como comentário.

### 4. Idioma

- **API pública da stdlib e builtins: inglês.** É a decisão de produto para alcançar quem
  lê a referência sem tradução; combina com identificadores em inglês (AGENTS §4).
- **Spec, ADRs, tutoriais e docs de projeto: pt-BR** (fonte), com tradução en-US depois
  (TODO §14.2). O site terá `/stdlib` em inglês e `/reference` em pt-BR até a tradução.
- **Código de usuário**: a doc pode estar no idioma do projeto; `lox doc` não impõe idioma.
  Bibliotecas publicadas são encorajadas a usar inglês.
- A mistura é aceita e declarada; não haverá dois arquivos de doc por símbolo.

### 5. Fonte de verdade e ferramenta `lox doc`

- **Stdlib**: a doc vem de `std/*.lx` (`///`), não de lista manual. A API pública (sem `_`)
  é obrigatória; o teste de docs falha se faltar.
- **Builtins**: um **registry de doc** na tabela de primitivas/nativas (Python), com texto
  em inglês e assinatura. A geração usa esse registry; `docs/spec/semantica.md` passa a
  **linkar** a referência gerada em vez de repetir a lista.
- **Código de usuário**: `lox doc` gera a referência do projeto (Markdown/JSON) a partir
  das declarações e docs; sem doc, o símbolo aparece com assinatura e sem descrição.
- **`lox doc`** (subcomando do ADR-0093):
  - `lox doc [caminho]` → Markdown (padrão), um arquivo por módulo + índice;
  - `lox doc --json` → JSON determinístico (schema versionado) para agentes/LSP;
  - `--out DIR`; sem rede; caminhos relativos; ordem por módulo/nome.
  - O JSON inclui `name`, `kind`, `signature`, `doc`, `module`, `span` (linha/coluna) e
    `visibility` (`public`/`private`). É consumido pelo LSP hover e pelo site.
- **Site**: `docs/stdlib/` é **gerado** (não editado à mão), com `sources:`/frescor; o
  build da §14.2 consome. `make docs-sync` ou um `make doc` gate falha se a doc gerada
  estiver defasada.
- **LSP**: hover mostra assinatura + doc do `SymbolIndex`; o `lox doc --json` e o LSP devem
  concordar (teste de paridade, como o CLI×MCP).
- `lox explain` continua sendo catálogo de **códigos de erro**; não é doc de API.

### 6. Política

- **Obrigatório**: toda função/classe/interface/enum/type alias **pública** da stdlib
  (`T1`, `T2`, `T3`) tem `///`; builtins têm entrada no registry.
- **Recomendado**: campos e variantes públicos; funções privadas (`_`) quando a intenção
  não é óbvia.
- **Opcional**: código de usuário; `lox doc` funciona sem.
- O critério de pronto por módulo da stdlib (§13.8) ganha "doc pública em inglês e gerada";
  o teste de docs é o portão.
- Não haverá doctest nesta decisão; exemplos em cerca de código são texto até um runner
  futuro.

## Consequências

### Positivas

- Uma fonte de verdade por símbolo: assinatura e doc no código; site/LSP/`lox doc` derivam.
- Hover de código de usuário e referência da stdlib deixam de ser listas manuais que
  apodrecem.
- `///` é familiar (Rust/C#), combina com Markdown e não conflita com `//` divisão em
  código válido.
- O custo no I1 é zero: comentário não entra no runtime.

### Negativas / custos

- Um lexema novo, scanner/parser/AST/grammar e testes; o gate do ADR-0066 foi exercido.
- Mistura de idiomas: API em inglês, spec/tutoriais em pt-BR; a tradução do site fica
  assimétrica até a §14.2.
- Doc pública obrigatória aumenta o custo de fechar T3; o teste de docs pode ser chato.
- O registry de builtins é uma migração da lista manual; até lá a spec e o registry podem
  divergir (o teste de paridade fecha isso).
- Markdown sem tags é menos estruturado para gerar formulários; é uma escolha por
  legibilidade.

### Neutras

- `lox doc` e o LSP não mudam a linguagem; só consomem a AST/doc.
- A doc pode ser multilíngue no código de usuário; o gerador preserva.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| `##` como doc | Zero sintaxe nova, mas headings Markdown viram `## ###`, é não-padrão e mistura o marcador de comentário livre com doc. |
| `/** ... */` | Bloco de doc exigiria modo específico no lexer de bloco aninhado e daria duas formas de doc (`///` e `/** */`). |
| Doc como string (`"""..."""`) | Seria valor/expressão, não metadado; muda semântica e AST; docstring Python não tem equivalente direto. |
| Docs externas/manuais | Já é o status quo; drift e hover vazio para código de usuário. |
| Markdown + tags `@param`/`@returns` | Duplica a assinatura tipada e exige parser de tags; não paga. |
| pt-BR na API pública | Consistente com a spec, mas limita a referência a quem lê português; a decisão foi inglês. |
| `lox doc` em HTML próprio | O site (§14.2) já é o consumidor; Markdown/JSON evita um renderizador a mais. |

## Como verificar

- `uv run pytest tests/test_docs.py` — anexação (linha em branco quebra), normalização,
  vários `///`, doc em método/campo/variante, doc órfã.
- `uv run main.py doc std/strings.lx --json` — schema e determinismo (ordem, sem caminho
  absoluto); `--format=markdown` idempotente.
- Teste que toda função pública de `std/*.lx` tem doc em inglês e aparece na referência
  gerada; builtins no registry.
- Paridade hover do LSP × `lox doc --json` (quando LSP-1 existir).
- `make check` e `make docs-sync`; `tests/test_docs_consistency.py`/links verdes.
- Critério para revisitar: doc obrigatória gerar atrito; Markdown sem tags limitar o site;
  necessidade de doctest; tradução en-US mudar a estratégia.

## Referências

- Rustdoc — <https://doc.rust-lang.org/rustdoc/how-to-write-documentation.html>
- Markdown — <https://commonmark.org/>
- [`../spec/lexico.md`](../spec/lexico.md) — comentários atuais.
- [`../spec/semantica.md`](../spec/semantica.md) — lista manual da stdlib.
- [`../../TODO.md`](../../TODO.md) §10 (`lox doc`), §13.8 (pronto por módulo), §14.2 (site).
