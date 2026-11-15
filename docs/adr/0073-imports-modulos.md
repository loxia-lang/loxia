# ADR-0073 — Imports, módulos-arquivo e privacidade `_`

- **Status:** accepted (implementado)
- **Data:** 2026-11-14
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0066](0066-orcamento-e-gate-sintatico.md),
  [ADR-0072](0072-stdlib-batteries.md), [ADR-0071](0071-primitivas-de-runtime.md),
  [ADR-0020](0020-assinaturas-explicitas.md), [`../../TODO.md`](../../TODO.md) §13
- **Implementação:** [`src/loader/loader.py`](../../src/loader/loader.py),
  [`src/frontend/parser.py`](../../src/frontend/parser.py),
  [`src/frontend/stmt.py`](../../src/frontend/stmt.py) (`Import`),
  [`tests/test_modules.py`](../../tests/test_modules.py), `std/*.lox`

## Contexto

A stdlib do [ADR-0072](0072-stdlib-batteries.md) não cabe num prelúdio único: `split`,
`map`, `join` e `parse` colidiriam como globais, e não haveria privacidade nem opt-in.

A discussão de 2026-11-14 rejeitou três heranças do Python/Java:

- `__init__.py`/`index.lox`: pasta não vira módulo por mágica;
- `from dtos import dtoA` ambíguo (módulo ou declaração?);
- `private`/package-private: mais um eixo de visibilidade sem dor real.

Decisão: **arquivo é módulo; pasta é só namespace; `_` é privado verificado**.

## As quatro perguntas do gate

1. **Substituição.** Capacidade nova exigida pela stdlib; não substitui grafia.
2. **Decidibilidade local.** `import`/`from` são statements de topo; o caminho é composto
   por identificadores; não há expressão de módulo. O loader resolve sem CWD/env.
3. **Precedência.** Nenhuma: statements de topo.
4. **Forma canônica.** Um módulo é um arquivo `.lox`; um nome público é acessado por alias
   de namespace ou importado por `from`; sem `*`, sem reexportação, sem módulo como valor.

### Custo no orçamento do ADR-0066

| Métrica | Antes | Depois | Teto |
| --- | --- | --- | --- |
| palavras-chave | 25 | **27** | 28 |
| formas de statement | 9 | **11** (`import`, `from`) | 12 |
| formas de declaração | 5 | 5 | 6 |
| níveis de precedência | 19 | 19 | 19 |
| construções sensíveis a newline | ~6 | ~6 | não crescer |
| grafias por conceito | 1 | 1 (namespace/import seletivo são conceitos distintos) | 1 |

## Decisão

### 1. Módulo é arquivo; pasta é namespace

```text
projeto/
  main.lox
  dtos/
    dtoA.lox
```

- `dtos/dtoA.lox` é o módulo `dtos.dtoA`.
- `dtos/` **não** é módulo; não existe `__init__.py`, `index.lox` ou arquivo de pacote.
- `from dtos import dtoA` é erro: o caminho tem que chegar ao arquivo.
- Raiz de resolução: diretório do arquivo de entrada; `..` e caminho absoluto são erros.
- `std.` é root reservado: resolve no bundle `std/`, nunca no projeto.
- O usuário não pode criar `std/`.

### 2. Sintaxe

```lox
import std.lists
import dtos.dtoA as dto
from std.strings import trim
from dtos.dtoA import DtoA as Dto
```

- `import caminho [as alias]`: liga o último segmento (ou o alias) como namespace.
- `from caminho import nome [as alias] [, nome ...]`: liga nomes públicos no escopo.
- Imports só no topo, antes de qualquer outro statement.
- Sem `*`; sem reexportação; sem import dentro de função/classe.
- Módulo é namespace de compilação, não valor: `val m = std.lists` é erro.

### 3. Declarações e privacidade

Módulos contêm apenas `fn`, `class` e `enum` de topo (além de imports). Sem `val`/`var` de
topo e sem statement de topo: import é puramente estático, sem ordem de inicialização.

- Nome de topo que começa com `_` é privado do módulo.
- Fora do módulo, `m._x` e `from m import _x` são erros de compilação/interpretação.
- Dentro do módulo, privado é acessível normalmente.
- `_` em script de arquivo único continua sendo nome comum: a regra é de fronteira de
  módulo.
- A checagem fica no **loader/resolver**, que roda nos dois motores; não é só `--check`.
- Métodos de classe não são reexportados individualmente; a classe é importada inteira.
  Privacidade de método fica como decisão separada.

### 4. Desugar

O loader resolve o grafo, rejeita ciclo e produz um programa plano:

1. cada declaração de módulo vira `modulo$decl` (separador não lexável);
2. referências a nomes importados e `alias.nome` são reescritas para o nome manglado;
3. nomes locais/parâmetros são preservados por escopo (shadowing não é tocado);
4. `display_name` preserva `DtoA`, `Status.Ativo` e `<fn helper>` na saída;
5. declarações dos módulos entram antes do código do entry.

O backend/resolver/checker veem um programa plano; não há ABI, tag ou lowering novo.
`--dump-ast` mostra o programa desugarizado.

### 5. Diagnósticos

O loader empilha o nome relativo da fonte ao parsear cada módulo (`dtos/dtoA.lox:3: ...`),
sem caminho absoluto. Erros de runtime/checker posteriores ainda usam a linha do entry;
a pilha de fontes completa é dívida declarada (não muda I1).

## Consequências

### Positivas

- Namespace e privacidade reais com uma marca só: `_`.
- Opt-in: módulo não importado não é parseado/checado.
- Zero ABI nova e risco baixo no I1; o desugar é testável isoladamente.
- Sem `__init__`/`index` e sem precedência implícita entre arquivo local e stdlib.

### Negativas / custos

- Mais duas palavras-chave e duas formas de statement (dentro do teto).
- Caminho completo até o arquivo é mais verboso que Python; alias atenua.
- Sem constantes de topo em módulo na v1 (`val PI`); usar `fn pi()`.
- Funções não usadas podem aparecer no `-O0`; `-O2` remove.
- Diagnósticos de checker em módulo ainda apontam o entry.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| `__init__.py`/`index.lox` | Pasta vira módulo por regra especial; não agrega. |
| `from dtos import dtoA` | Ambíguo entre submódulo e declaração. |
| `private`/`public` | Segundo vocabulário para a mesma ideia; `_` já basta. |
| `import *` | Poluição, ambiguidade e quebra do I2. |
| Módulo como valor | Tipos/runtime/backend novos; desugar resolve. |
| Resolver em runtime pelo FS | I3 e portabilidade; loader é estático. |

## Como verificar

- `tests/test_modules.py`: from, namespace, alias, privado, pasta não módulo, ciclo,
  módulo só de declarações e display.
- `test_backend.py::test_modulos_nativos`: mesmo resultado no binário.
- `tests/cases/` e `tests/test_docs_consistency.py` verdes; scoreboard de keywords em 27.

## Referências

- [ADR-0066](0066-orcamento-e-gate-sintatico.md) — gate, orçamento e forma canônica.
- [ADR-0072](0072-stdlib-batteries.md) — stdlib em Lox.
- [`../spec/sintaxe.md`](../spec/sintaxe.md) e [`../spec/semantica.md`](../spec/semantica.md)
