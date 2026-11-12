# Decisões já tomadas

Registro executivo das decisões **fechadas** que antes ficavam misturadas com as abertas
no `TODO.md` §11. A fonte de verdade continua sendo o ADR (ou o documento indicado); este
arquivo existe para consulta rápida e para o `TODO.md` ficar só com o que ainda precisa de
decisão.

> **Regra:** decisão nova → ADR (quando relevante) + linha aqui. Discussão ainda aberta →
> [`../IDEIAS.md`](../IDEIAS.md)/[`../TODO.md`](../TODO.md) §11; não entra neste arquivo.

## Linguagem e semântica

| Decisão | Resumo | Fonte |
| --- | --- | --- |
| `val`/`var` | `val` imutável e com inicializador; `var` mutável e pode ficar sem valor (`nil`); parâmetros são `val` por padrão e `var x` libera a mutação. | [ADR-0005](adr/0005-val-var-imutabilidade.md) |
| `Int` vs `Float` | Tipos separados: `Int` é i64 e `Float` é f64; promoção só `Int → Float`; `/` sempre `Float`; wrapping de i64. | [ADR-0006](adr/0006-int-float-separados.md), [`../TIPOS.md`](../TIPOS.md) §3 |
| Nullability | Non-null por padrão; `T?` é açúcar para `T \| Nil` e aceita `nil` (`D-15`). | [`../TIPOS.md`](../TIPOS.md) §6, [ADR-0010](adr/0010-tipagem-estatica.md) |
| Ranges e `for-in` | `a..b` half-open, só `Int`, lazy e reutilizável; `range(a, b, step)` com passo; `for x in` sobre `Range`/`String`/`List`; variável `val` por iteração. | [ADR-0007](adr/0007-ranges-e-iteracao.md) |
| Listas | Um tipo `List[T]`, homogêneo e **invariante**; mutável in-place (`val` congela o binding); literal `[1, 2]`, `xs[i]`/`xs[i] = v`, `push`/`pop` e `len(xs)`; igualdade estrutural; mutar durante iteração é erro. | [ADR-0015](adr/0015-listas-tipadas.md) |
| Mapas | `Map[K, V]`, homogêneo e invariante; literal `{chave: valor}` (chaves são expressões; `{` no início do statement é bloco); `m[k]` erra se ausente e `m.get(k)` devolve `V?`; chaves `String`/`Int`/`Bool`; `get`/`has`/`remove`/`keys`/`values`; iteração de chaves em ordem de inserção; igualdade estrutural sem ordem. Sem `get(k, default)` — use `??`. | [ADR-0017](adr/0017-mapas-hash.md) |
| Narrowing | `T?` refina em `if`/`elif`/`else`, `x == nil`/`x != nil`, truthiness e early return; `is T`, `while` e `and`/`or` também estreitam; `val` e `var`, com invalidação em atribuição; faltam campos/índices e merge completo. | [ADR-0018](adr/0018-narrowing.md), [ADR-0025](adr/0025-is-e-narrowing.md) |
| Interpolação | `"${expr}"`, qualquer expressão, conversão por `stringify`; `\${` para literal; scanner empacota tokens da expressão. | [ADR-0019](adr/0019-interpolacao.md) |
| Defaults e campos | Defaults posicionais constantes com aridade `[mín, máx]`; campos `val`/`var` declarados no corpo, sem campo dinâmico. | [ADR-0009](adr/0009-defaults-e-campos.md) |
| Herança | `class B(A)` com parênteses (sem `extends`/`:`/`<`); `init` no corpo; `this` implícito; `super.init(...)` explícito. | [ADR-0008](adr/0008-heranca-class-parens.md) |
| Tipagem gradual | Checker opt-in (`--check`), funções anotadas, inferência local, `T?`/uniões, narrowing e truthiness; sem inferência de parâmetro sem anotação. | [ADR-0010](adr/0010-tipagem-estatica.md) |
| Assinaturas explícitas | Parâmetros/retorno obrigatórios; assinaturas de topo pré-declaradas para corpos (recursão mútua), mas o topo segue a ordem dos statements; inferir parâmetro ficou adiado. | [ADR-0020](adr/0020-assinaturas-explicitas.md) |
| Tipos de função | `fn(Int) -> Int` em anotações; parâmetros contravariantes, retorno covariante; classe como construtor (`fn(String) -> Animal`); lambdas em ADR-0022; funções genéricas em ADR-0027. | [ADR-0021](adr/0021-tipos-de-funcao.md) |
| Lambdas | `fn(x) => expr` e `fn(x) { ... }`; tipagem contextual pelo tipo esperado; retorno inferido; mistura não-nil exige anotação; `this`/`super` lexicais; sem defaults/trailing closure. | [ADR-0022](adr/0022-lambdas.md) |
| Soundness do checker | Retorno em todos os caminhos para funções/métodos; `return;` não-nil é erro; todo campo sem inicializador precisa ser atribuído em todos os caminhos do `init`; override compatível (contravariante/covariante), checado depois de todas as classes. | [ADR-0023](adr/0023-soundness-do-checker.md) |
| Mutação monomórfica | Variável tem um tipo só; `var x = nil` sem anotação é erro; use `T?`/`Any`; campo mutável com `nil` idem; `val x = nil` é permitido; sem união/flow-sensitive implícita. | [ADR-0024](adr/0024-mutacao-monomorfica.md) |
| `is T` e narrowing | `x is T` devolve Bool; testa primitivos, classes/subclasses, `List[T]`/`Map[K,V]` e uniões; estreita variáveis em `if`/`else`, `while`, `and`/`or`; sem campos/índices; tipos de função recusados. | [ADR-0025](adr/0025-is-e-narrowing.md) |
| Freeze da 1.0 | Erro de runtime é fatal (exit 70), sem `try`/`Result`; `clock` sai do prelúdio; strings UTF-8 com `len` em code points (indexação de string fora da 1.0) e identificadores ASCII; `print` continua statement; escopo congelado (single-file, sem módulos/`if`-expr/`match`/traits/`Any` no backend); generics é a exceção do ADR-0027. | [ADR-0026](adr/0026-freeze-1.0.md) |
| Generics T3b | Funções genéricas `fn id[T] (...)`, corpo checado uma vez sem constraints; inferência na chamada (sem `id[Int]`); só funções; monomorfização no backend; recursão polimórfica recusada; função genérica não é valor. | [ADR-0027](adr/0027-generics-t3b.md) |
| Overflow no debug | `--debug` checa `+ - * ** -`, `INT_MIN // -1` e `% -1`; overflow é erro fatal (exit 70); release continua wrapping; shifts não checam. | [ADR-0028](adr/0028-overflow-debug.md) |
| Conversões e `math` | `as` explícito (`Int`/`Float`/`Any`/classe/lista/mapa); `Float as Int` trunca e falha em NaN/Inf/range; `Int.parse`/`Float.parse` devolvem `T?`; `math.*` determinístico com abs/min/max/clamp/floor/ceil/round/trunc/sqrt; transcendentais fora do I3. | [ADR-0029](adr/0029-conversoes-math.md) |
| Tuplas | Sintaxe `(a, b)`/`(A, B)`, acesso `t[0]`, destructuring `val (a, b) = t`, 2+ elementos, imutáveis; implementação **pós-1.0/backend**. | [ADR-0030](adr/0030-tuplas.md) |
| `fn`/`elif`/`;` | `fn` substitui `fun`; `elif` é açúcar para `else if`; `;` opcional no fim da linha, EOF ou antes de `}`; operador só continua na mesma linha; `return` sozinho devolve `nil`. | [ADR-0011](adr/0011-fn-elif-ponto-e-virgula.md) |
| Comentários, `//`, `**` e bits | `#` e `/* */` aninhado; `//` truncado só `Int`; `**` com precedência matemática e `Int ** Int -> Int`; `& \| ^ ~ << >> >>>` em i64; shift inválido é erro. | [ADR-0012](adr/0012-comentarios-divisao-potencia-bits.md) |
| Ternário, `??`, `?.` e escapes | `a if c else b` (Python-style); `??` só nil; `?.` com optional call e assignment proibido; escapes `\n \t \r \" \\ \0 \u{...}`. Sem `?:`, interpolação, `"""` ou raw ainda. | [ADR-0013](adr/0013-ternario-nil-aware-escapes.md) |
| API da stdlib | Modelo **híbrido**: builtins globais para operações genéricas/protocolos (`len`, `str`, `repr`), métodos para ações específicas (`xs.push/pop`), namespaces nativos para conversão (`Int.parse`/`Float.parse`, `math.*`) e funções livres para composição. Builtins globais são reservados (shadowing só local); sem métodos em primitivos; extensões/UFCS em P3 pós-LLVM. | [ADR-0016](adr/0016-api-stdlib-hibrida.md), [ADR-0029](adr/0029-conversoes-math.md) |

## Processo e escopo

| Decisão | Resumo | Fonte |
| --- | --- | --- |
| Pipeline `\|>`/`:>` | **Rejeitado por enquanto** em 2026-11-11; alternativas e gatilhos de reabertura ficam registrados. | [`../IDEIAS.md`](../IDEIAS.md) I-2 |
| Identidade e invariantes | A linguagem se define por **I1** equivalência executável, **I2** nada implícito e **I3** determinismo observável; features passam pelo portão de admissão. | [ADR-0014](adr/0014-identidade-e-invariantes.md), [`spec/garantias.md`](spec/garantias.md) |

## O que ainda não está aqui

Nome/extensão da linguagem, `if`/blocos como expressão, `print` como função, `match`,
futuro de classes/traits, exceções vs `Result`, **generics de classes/métodos e
constraints**, módulos, backend, contratos e unificação mutável continuam **em aberto** no
[`../TODO.md`](../TODO.md) §11. Tuplas têm sintaxe decidida, mas implementação pós-1.0.
