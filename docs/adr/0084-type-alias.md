# ADR-0084 — `type` alias transparente (implementação)

- **Status:** accepted (implementado: parser, checker, tree-walk, backend e módulos)
- **Data:** 2026-11-15
- **Decisão original:** [ADR-0039](0039-decisoes-tipos-pendentes.md) §4
- **Relaciona:** [ADR-0010](0010-tipagem-estatica.md) (checker),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md) (orçamento),
  [ADR-0073](0073-imports-modulos.md) (módulos)

## Contexto

O [ADR-0039](0039-decisoes-tipos-pendentes.md) decidiu que `type UserId = Int` seria um
alias **transparente, não-genérico** (P3): outro nome para o mesmo tipo, sem tipo nominal
novo, sem custo de runtime. A decisão estava registrada, mas a implementação não existia;
assinaturas com `UserId`, `List[String]` nomeada, callbacks e tuplas repetiam a mesma
anotação longa em todos os módulos.

## Decisão

### 1. Sintaxe e escopo

```
type UserId = Int
type Nomes = List[String]
type Callback = fn(Int) -> Int
type MaybeNome = String?
type Par = (Int, String)
```

- `type` é **contextual**, não palavra-chave: o parser reconhece
  `type IDENTIFIER =` / `type IDENTIFIER [` no início de uma declaração. Nenhuma palavra
  nova entra no orçamento do ADR-0066 e `type` continua um identificador comum fora desse
  contexto (`type = 1` é atribuição).
- Declaração **top-level**; dentro de função/bloco o checker recusa
  (`Type aliases must be declared at the top level.`).
- Sem genéricos: `type BoxAlias[T] = List[T]` é erro de parser
  (`Type aliases can't be generic yet.`); o alvo pode usar tipos genéricos concretos
  (`List[Int]`, `Box[Int]`), mas o alias não recebe parâmetros.
- O nome do alias não pode colidir com classe, interface, enum, builtin ou outro alias.
- Não é um valor: `print UserId` é `Undefined variable`, como qualquer nome de tipo.

### 2. Resolução e transparência

O checker **pré-declara** todos os aliases top-level antes de resolver assinaturas, então
aliases podem se referir a classes/interfaces/enums declarados depois e a outros aliases
(forward references). A resolução:

- expande o alias para o tipo alvo (recursivamente em `List`, `Map`, tupla, união,
  `T?` e tipos de função);
- detecta ciclos (`type A = B; type B = A`) com
  `Type alias 'A' is recursive.` e não entra em loop;
- mantém a transparência: `UserId` e `Int` são o **mesmo** tipo para atribuição,
  `is`, `as`, mensagens e backend; não há conversão nem identidade nominal.

Aliases valem em anotações de variável, campo, parâmetro, retorno, `List`/`Map`, tuplas,
uniões, `is`/`as`, tipos de função e bounds de interface (`T: Ali` quando `Ali` aponta
para uma interface).

**Fora da v1:** `class C(Alias)` (superclasse é um nome/valor de classe, não uma
anotação) e `class C implements Alias` — nomes nominais continuam sendo a interface
declarada, não o alias. Essas posições não passam pela gramática de tipos; usar o nome
real. O alias também não cria tipo nominal, então não há `UserId(1)` nem distinção em
runtime.

### 3. Runtime e backend

- O interpretador coleta os aliases top-level antes de executar e expande o alvo em
  `is`/`as`; `visit_type_alias_stmt` é no-op e só mantém o mapa para o REPL.
- O checker publica `type_aliases()` (mapa já resolvido); o backend recebe esse mapa e
  `_type_desc`/`_type_text` expandem o alias. O resto da ABI não muda: `type` não gera
  código, não entra em vtable, descritor ou lista de campos.
- Em módulos, o loader trata `TypeAlias` como declaração pública (ou `_privada`), renomeia
  o nome e expande os nomes de tipo do alvo; `from m import UserId` funciona e o alias
  mantém a transparência depois do mangling.

## Consequências

- Assinaturas ficam curtas e a mudança de representação (ex.: `UserId = Int` para outra
  coisa) é local ao alias.
- O checker ganha uma noção de resolução de nome de tipo com forward reference e ciclo;
  o backend só precisa de um mapa adicional.
- Como é transparente, `UserId` não impede passar um `Int` arbitrário: para tipo nominal
  seria outro recurso (não decidido e fora do escopo).
- A limitação em `implements`/superclasse é explícita e não afeta anotações, que é o caso
  de uso do ADR-0039.

## Alternativas

| Alternativa | Por que não |
| --- | --- |
| `type` como palavra-chave | Estouraria o orçamento e reservaria um identificador útil sem necessidade |
| Alias nominal (`newtype`) | Exigiria conversão explícita e não é o que “alias” significa (ADR-0039) |
| Alias genérico já | Abre substituição, aridade e unificação; não há dor demonstrada |
| Resolver alias só no backend | O tree-walk sem `--check` precisa expandir `is`/`as`; duas fontes divergiriam |
| Aliases locais | Escopo e sombra complicariam sem caso de uso; top-level cobre módulos |

## Como Verificar

- `tests/cases/type_alias.lx` no `l6`: primitivo, lista, função, opcional, tupla, campo de
  classe, `is`/`as`, `List[UserId]`, spread não envolvido; tree-walk e backend.
- `tests/test_checker.py::test_type_aliases_are_transparent` e
  `test_type_alias_errors`: colisão, ciclo, alvo desconhecido, tipo genérico aplicado ao
  alias, alias local e alias não-interface em bound.
- `tests/test_parser.py`: AST e recusa de alias genérico; `tests/test_ast_printer.py`:
  `(type UserId Int)`.
- `tests/test_modules.py::test_importa_type_alias`: import de alias/módulo.
- `make check`, `make bench` e `make docs-sync`.
