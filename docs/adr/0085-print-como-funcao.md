# ADR-0085 — `print` como função builtin

- **Status:** accepted (implementado)
- **Data:** 2026-11-15
- **Substitui:** cláusula “`print` continua statement” do
  [ADR-0026](0026-freeze-1.0.md)
- **Relaciona:** [ADR-0016](0016-api-stdlib-hibrida.md) (builtins),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md) (orçamento),
  [ADR-0083](0083-variadicos.md) (variádicos), [ADR-0084](0084-type-alias.md)

## Contexto

O [ADR-0026](0026-freeze-1.0.md) congelou `print` como statement para a 1.0: uma linha,
sem parênteses, sem valor. Isso impedia composição (`print` não podia ser passado,
retornado ou usado como expressão), mantinha uma palavra-chave e uma forma de statement
só para I/O, e divergia do resto da linguagem, em que operações são funções builtin
(`len`, `str`, `repr`). Com variádicos (ADR-0083) e o checker estável, o custo de migrar
os fontes é mecânico e o ganho é tirar uma construção especial da gramática.

## Decisão

### 1. Sintaxe e semântica

```lox
print(1)
print("x")
print(print(1))       # imprime 1 e depois nil

fn eco(x: Any) -> Nil { return print(x) }
```

- `print` deixa de ser palavra-chave e **não existe mais `printStmt`**. A forma
  `print expr` não é aceita; `print` é um identificador builtin.
- Assinatura: `print(valor: Any) -> Nil`. Escreve `stringify(valor)` e uma newline;
  devolve `nil` (por isso `print(print(1))` imprime `1` e `nil`).
- **Um argumento só** na v1. Não é variádico: `print(a, b)` é erro de aridade. Separar
  com espaço ou múltiplos `print` é explícito; um `print(...args)` mudaria a saída de
  todos os casos e fica para outro ADR, se houver dor.
- `print` é builtin global reservado (`BUILTIN_NAMES`), como `len`/`str`; um escopo local
  pode sombreá-lo (ADR-0016). O checker o trata como `NativeFnTy` com assinatura
  `fn(Any) -> Nil`.
- Erros de tipo do argumento são os de `Any`: qualquer valor é aceito; listas, mapas,
  funções e instâncias usam a mesma representação de `stringify` do tree-walk/backend.

### 2. REPL

O REPL continua exibindo o valor de uma expressão pura, mas agora **envolve a expressão
numa chamada `print(expr)`**. `print(1)` digitado no REPL é executado uma vez e não é
envelopado de novo (evita imprimir `nil` extra). Statements continuam statements.

### 3. Backend

- A chamada é reconhecida em `CallLowering` como `print` e usa os mesmos
  `lox_print_int/float/bool/str/...` do antigo statement, incluindo optionais e `Any`.
- O retorno é `nil`; a chamada é uma expressão normal, então pode aparecer em `if`,
  argumento, `print(print(x))` etc.
- A ABI, o runtime C e os símbolos `lox_print_*` não mudam; só o nó de AST/statement
  deixa de existir.
- Como os outros builtins nativos, `print` não é um valor de primeira classe no backend
  (`val p = print` fica fora do lowering); chamadas diretas são o caso suportado.

### 4. Migração e orçamento

- Todos os `.lx` do corpus, da suíte oficial, de `exemplos/`, `std/` e `bench/` foram
  migrados mecanicamente de `print expr` para `print(expr)`; nenhuma expectativa de
  stdout/exit foi alterada.
- `print` sai de `KEYWORDS` e do grupo de controle da grammar; o placar do ADR-0066 passa
  de **28 para 27** palavras-chave e de **11 para 10** formas de statement. O teto de 28
  continua válido.
- O caso negativo de `;` entre `print`s passa a exercitar a mensagem de expressão
  (`Expect ';' after expression.`), não a antiga mensagem de valor.

## Consequências

- `print` pode ser aninhado, retornado por funções que devolvem `Nil` e usado como
  expressão de controle.
- A gramática perde uma palavra-chave e um statement; `print` não colide mais com um
  identificador comum em declarações.
- Programas antigos com `print expr` precisam de parênteses — mudança **breaking**,
  aceita e coberta pela migração do repositório.
- O nome `Print` do AST/visitor deixa de existir; o builtin Python chama-se `Print` em
  `loxia_core/execution/natives/print.py`.

## Alternativas

| Alternativa | Por que não |
| --- | --- |
| Manter `print` statement e criar `println` | Duas grafias para o mesmo conceito; não resolve composição |
| `print(...args)` variádico | Muda separadores/saída de todos os casos; não há dor demonstrada |
| `print` retornando o valor | Quebraria `print(print(1))` e a leitura de “I/O devolve nil” |
| Builtin como método (`io.print`) | `print` é operação universal; namespace `io` já cobre arquivos |
| Só remover o keyword e manter nó `Print` | O parser não teria como distinguir `print(1)` de chamada; nó morto |

## Como Verificar

- `tests/cases/print_function.lx` no `l6`: tipos, `nil`, aninhamento, `print` como
  retorno de função; tree-walk e backend.
- `tests/test_parser.py`: `print(1)` vira `Expression(Call)`; REPL não imprime duas vezes.
- `tests/test_cli.py`/`test_ast_printer.py`: dump `(expr (call print ...))` e erros de
  sintaxe com parênteses.
- `make grammar` (keyword removida), `make docs-sync` e suíte completa.
