# ADR-0099 — Notas de proveniência em erros de tipo

- **Status:** accepted (implementado)
- **Data:** 2026-11-16
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0075](0075-diagnosticos-estruturados.md) (modelo de
  diagnóstico e `notes`), [ADR-0090](0090-lsp-escopo-e-hospedagem.md) (spans de
  expressão/`SourceIndex`), [`../../TODO.md`](../../TODO.md) §3.1
- **Implementação:** `loxia_core/frontend/source_index.py`,
  `loxia_core/semantics/checker.py`, `loxia/cli.py`,
  `tests/test_provenance.py` e `tests/test_source_index.py`

## Contexto

O [ADR-0075](0075-diagnosticos-estruturados.md) entregou `Diagnostic.notes`, mas deixou
a proveniência sem produtor: "o valor vem de `pessoa.nome` (linha 7)". O checker já
sabia o tipo de cada expressão, não **de onde** o valor veio. O
[ADR-0090](0090-lsp-escopo-e-hospedagem.md) criou o `SourceIndex` de spans de expressão
para hover/definition, mas ele vivia no pacote `loxia` (CLI) e o checker não podia
consumi-lo sem inverter a dependência.

O diagnóstico de tipo frequentemente aponta o **destino** — o nome da variável em
`val total: Int = pessoa.nome` ou o parêntese em `f(pessoa.nome)` — e não a expressão que
produziu o valor. Sem a nota, o usuário precisa reconstruir a origem a partir do caret.

## Decisão

**O checker emite uma nota de proveniência no erro de tipo quando o valor tem nome ou
caminho, usando o `SourceIndex` para recuperar o texto e a linha da expressão.**

### 1. O índice mora no core e sabe ler a fonte

`SourceIndex` passa a `loxia_core/frontend/source_index.py` (o caminho antigo,
`loxia/source_index.py`, vira re-export). Ele ganha:

- `span_of(expression)`: span da expressão indexada;
- `text_of(span)` e `line_of(span)`: texto-fonte e linha 1-based;
- `sources: SourceMap` opcional no construtor, para resolver o arquivo do token (módulos
  incluídos). Sem `SourceMap`, o comportamento antigo (uma fonte) é preservado.

O `Loxia` passa o `SourceMap` da execução ao construir o índice e injeta o índice no
`Checker`. O parâmetro é opcional: quem constrói `Checker` diretamente continua sem notas.

### 2. Quando a nota aparece

Só em diagnósticos de **tipo** e só quando a expressão do valor é "nomeada":

- `Variable`, `Get`, `Index` e `Call` (com `Grouping` desembrulhado);
- literais, lambdas, listas/mapas/tuplas e expressões compostas ficam de fora — nesses
  casos a nota só repetiria o caret;
- se o diagnóstico já começa no início da expressão, a nota é omitida.

A nota cobre os pontos em que o erro aponta o destino e não o valor:

- `val`/`var` anotado, destructuring, campo, `return` e atribuição (via `_check`);
- argumentos de chamada (fixos, variádicos e spread);
- `len`, `chars` e `math.*`;
- chave/valor de `Map` e índice de `List` em leitura/atribuição;
- `raise` com valor que não é `Exception`.

Erros de aridade, nome indefinido, propriedade inexistente, override e erro de runtime
não ganham a nota: não há um valor de origem a apontar.

### 3. Formato

Uma linha, em inglês como o resto do diagnóstico, com o texto-fonte normalizado
(espaços/quebras colapsados) e truncado em 80 caracteres:

```text
exemplo.lx:6:5: error[E3001]: Expected Int, found String.
  |
6 | val total: Int = pessoa.nome
  |     ^^^^^
note: the value comes from `pessoa.nome` (line 6)
```

A linha é a do **início da expressão**, não a da declaração da variável. Sem a fonte
carregada (token sintético), nenhuma nota é emitida. O texto nunca contém caminho
absoluto, timestamp ou endereço (I3).

## Consequências

### Positivas

- O erro de tipo fica autoexplicativo quando o destino e a origem estão em pontos
  diferentes do código.
- O checker reusa a mesma infraestrutura de spans do LSP, sem duplicar derivação de
  offsets nem inventar um segundo modelo.
- A nota é texto determinístico no `Diagnostic`; `human` já imprime `note:` e `json` já
  exporta `notes[]`, sem mudança de schema.

### Negativas / custos

- O diagnóstico de tipo ganha mais uma linha; `short` continua de uma linha e não mostra
  notas.
- O `SourceIndex` agora conhece `SourceMap`; arquivos fora do mapa não produzem nota
  (degrada em silêncio, de propósito).
- A nota depende de o consumidor construir o checker com o índice; `Checker` avulso não
  a produz.

### Neutras

- `loxia/source_index.py` permanece como re-export de compatibilidade.
- A semântica da linguagem e o I1 não mudam: a nota é diagnóstico de compilação, não
  saída de programa.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Reconstruir o texto concatenando lexemas da AST | Perde parênteses, `?.` e espaçamento original; diverge da fonte. |
| Nota em todo erro de tipo, inclusive literais | Ruído: `the value comes from \`"a"\` (line 7)` não ajuda. |
| Nota em erros de runtime | O runtime não tem AST nem fonte; o binário precisa do mesmo stderr (I1). |
| Deixar o `SourceIndex` no pacote `loxia` e importar no checker | Inverte a dependência (core → CLI) e quebra a arquitetura por fases. |
| Emitir label secundário em vez de nota | Exigiria um span por diagnóstico; o modelo atual já suporta `notes` e o `SourceIndex` só precisa do texto. |

## Como verificar

- `uv run pytest tests/test_provenance.py` — nota em variável, argumento, atribuição,
  módulo e ausência em literal.
- `uv run pytest tests/test_source_index.py` — `span_of`/`text_of`/`line_of`.
- `uv run main.py --check --error-format=json arquivo.lx` — `notes[]` preenchido.
- `make check` — suíte, determinismo e docs consistentes.

Critério para revisitar: quando outro produtor de notas precisar de spans (ex.: hover ou
`loxia doc`); se a nota aparecer em erros onde atrapalha, restringir os tipos de
expressão em vez de desligar o mecanismo.

## Referências

- [`../spec/erros.md`](../spec/erros.md) — formato e catálogo.
- [`../spec/semantica.md`](../spec/semantica.md) — erros de compilação.
- [ADR-0075](0075-diagnosticos-estruturados.md), [ADR-0090](0090-lsp-escopo-e-hospedagem.md).
