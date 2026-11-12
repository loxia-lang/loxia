# Glossário

Termos usados na documentação. Ordem alfabética.

**ADR** — *Architecture Decision Record*: registro imutável de uma decisão de design, com
contexto, consequências e alternativas. Ver [`adr/`](adr/).

**Ambiente (Environment)** — estrutura de escopo em runtime: um dicionário de nomes e um
ponteiro para o ambiente externo. Ver [`tech/arquitetura.md`](tech/arquitetura.md).

**Arity** — número de argumentos que uma função/classe espera. Verificada em runtime no
tree-walk.

**AST** — *Abstract Syntax Tree*: árvore de nós que representa o programa depois do parser.
Neste projeto os nós têm identidade (`eq=False`).

**Binding (ligação)** — associação entre um nome e um valor em um escopo. Em métodos,
"bind" é criar um ambiente com `this` apontando para a instância.

**Closure (fechamento)** — função que carrega o ambiente onde foi declarada, permitindo
acessar variáveis locais mesmo depois que o escopo terminou.

**Desugar (desaçucarar)** — transformar açúcar sintático em construções mais simples. Ex.:
`for` vira `{ var; while }` no parser.

**Distância (depth)** — quantos ambientes subir para achar uma variável local; calculada
pelo resolver e usada por `environment.get_at(distance, nome)`.

**Escopo léxico** — a variável é resolvida pelo local onde o código foi **escrito**, não
pelo local de chamada. O resolver garante isso.

**Expressão** — trecho que produz valor (`1 + 2`, `f()`, `a.b`). **Statement** — instrução
que produz efeito (`print`, `var`, `if`, `while`, `return`, bloco).

**Golden case** — arquivo `.lox` de teste com a saída esperada em comentários
(`// expect: …`). Ver §5 do `AGENTS.md` (local) e a skill `lox-testing`.

**Global / local** — global vive no ambiente raiz e é resolvido em runtime; local tem
distância calculada estaticamente.

**Instância** — objeto criado por uma classe, com campos próprios e métodos ligados a
`this`.

**Invariância** — regra de subtipagem em que `List[Int]` **não** é `List[Float]`, mesmo
com `Int <: Float`. Necessária porque a lista é mutável: aceitar `List[Int]` onde se espera
`List[Float]` permitiria `push(1.5)` e quebraria o tipo. Ver
[ADR-0015](adr/0015-listas-tipadas.md).

**Lista (`List[T]`)** — sequência homogênea e mutável in-place; literal `[1, 2]`,
indexação `xs[i]`, `push`/`pop`, `len(xs)` e `for-in`. `val` congela o binding, não o
conteúdo. Ver [ADR-0015](adr/0015-listas-tipadas.md).

**Initializer (`init`)** — método especial chamado na criação da instância; sempre devolve
a instância.

**Oráculo** — implementação de referência usada para comparar o comportamento de outro
backend (LLVM). Ver [ADR-0002](adr/0002-tree-walk-como-oraculo.md).

**REPL** — *Read–Eval–Print Loop*: modo interativo do `main.py`, uma linha por vez, estado
persistente.

**Resolver** — passe estático que valida escopos (redeclaração, `this`/`super`, `return`) e
grava a distância de cada variável local.

**Spec (especificação)** — descrição do comportamento **atual** do interpretador, em
[`spec/`](spec/).

**Stringify** — função única de formatação de valores (`nil`, `true`, `3`, `<fn f>`, `Foo
instance`). Ver [`spec/semantica.md`](spec/semantica.md).

**Token** — menor unidade léxica (palavra-chave, identificador, literal, operador).

**Truthiness** — regra de "verdadeiro/falso" em condições: só `nil` e `false` são falsos.

**Visitor** — padrão em que cada nó chama `visitor.visit_<no>_<expr|stmt>`; permite
adicionar passes (resolver, interpretador, printer) sem espalhar `isinstance`.
