# ADR-0147 — Valores de função: assinatura em runtime e `is`/`as fn`

- **Status:** accepted
- **Data:** 2026-11-25
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0046](0046-closures-celulas-l4.md) (closure `{fnptr, env, display}`),
  [ADR-0048](0048-abi-classes-l5.md) (ABI), [ADR-0029](0029-conversoes-math.md) (`as`),
  [ADR-0055](0055-l6-any-casts.md) (`Any` boxeado), [ADR-0144](0144-any-dinamico-exige-estreitamento.md)
  / [ADR-0146](0146-is-as-interface.md) (narrowing), [ADR-0025](0025-is-e-narrowing.md) (`is`),
  [ADR-0141](0141-soundness-de-fluxo-do-checker.md) (fluxo), [ADR-0107](0107-adiados-e-nao-objetivos.md)
  (não-objetivos), issue [#213](https://github.com/loxia-lang/loxia/issues/213)
- **Implementação:** `runtime/lox_runtime.h` (`LoxClosure`, `LoxFnSig`),
  `runtime/objects.c` (`lox_fn_assignable`, `lox_type_assignable`, parse de função),
  `loxia_core/backend/lower_model.py` (`_CLOSURE`/`FnSig`), `lower_functions.py`,
  `lower_class_codegen.py` (bound methods/interface thunks), `lower_calls.py`,
  `loxia_core/semantics/checker.py` (`FnTy` por declaração, `visit_as_expr`/`visit_is_expr`),
  `loxia_core/execution/lox_function.py` (assinatura), `interpreter.py`,
  `tests/cases/fn_*.lx`, `tests/test_checker.py`, `tests/test_backend.py`

## Contexto

Um valor de função pode ser guardado em `Any` (tag `FUNCTION`, payload = `LoxClosure*`), em
campo, lista, mapa ou global. O backend o **imprime** e o **passa adiante**, mas não o
**chama** dinamicamente: `as fn(T) -> U` é recusado pelo checker (`E3013`) e `is fn(...)`
também (`E3007`). O `E3025` manda estreitar com `is`/`as`, mas para função o caminho não
existe. É a parte de funções do [#213](https://github.com/loxia-lang/loxia/issues/213).

O `LoxClosure` atual é `{void *fn; void *env; const char *display;}` (ADR-0046). A aridade
e a assinatura existem no **site de criação/chamada** (`FnSig`: params, retorno, `min_params`,
variádico) e são apagadas do valor. Guardar só `min/max` no closure fecharia o caso de
contagem errada, mas **não** o de mesma aridade com tipos errados:

```lox
fn f(x: String) -> String { return x + "!" }
val a: Any = f
val g = a as fn(Int) -> Int
print(g(1))
```

O tree-walk faz `1 + "!"` e erra em runtime; o binário passa `1` como ponteiro de `String` e
lê lixo/segfault. Para I1/I4, o cast tem que ser uma **checagem**, não uma promessa do
usuário. Ao mesmo tempo, os tipos do programa são apagados (ADR-0025/0055): não há tipo
reificado em cada valor para checar parâmetros/retorno em runtime.

## Decisão

1. **O closure carrega a assinatura.** `LoxClosure` ganha, no fim do struct (append;
   ADR-0046/0048), `int64_t min_arity`, `int64_t max_arity` e `void *signature` — um
   ponteiro para um `LoxFnSig` **estático** (tabela por tipo de função, sem GC). O
   `LoxFnSig` tem `{min_arity, max_arity, variadic, n_params, LoxTypeDesc **params,
   LoxTypeDesc *ret}`. Todo site que cria closure (função, lambda, método, bound method,
   default de interface, thunk de interface) preenche esses campos a partir do `FnTy` do
   checker/`FnSig` do backend.

2. **Assinaturas usam as árvores de tipo do matcher.** Os `LoxTypeDesc` existentes
   (`C<id>`, `J<id>`, `L<...>`, `M<...>`, `T<...>`, `U<...>`, escalares, `A`/`N`) ganham um
   nó de **função** (`K<...>`, com a própria `LoxFnSig`), para tipos de função **aninhados**
   em parâmetros/retorno. `lox_type_assignable(expected, actual)` compara tipos (não
   valores), espelhando `TypeOps.assignable`: `Any` no topo, classe → superclasse,
   classe → interface implementada, uniões/containers/opcionais, e função → função
   recursivamente.

3. **`is fn(D) -> R` / `as fn(D) -> R`:**
   - `is` é verdadeiro sse o valor é um closure (`FUNCTION`) cuja assinatura **real** é
     atribuível à assinatura alvo (`assignable_fn`: parâmetros contravariantes, retorno
     covariante; aridade/`min_params`/variádico incluídos) **e as representações de máquina
     são iguais** em cada parâmetro/retorno (regra de ABI abaixo);
   - `as` devolve o próprio closure (com a assinatura **real**, não a alvo) ou falha em
     runtime (`R1011: Can't cast value to fn(...)`) nos dois motores;
   - quando o tipo estático da origem já é um `FnTy` (ou `Never`), o checker decide
     estaticamente com `assignable_fn` **e** a mesma checagem de ABI (parâmetro/retorno):
     compatível → sem checagem em runtime; incompatível → `E3013` na hora do cast. De
     `Any`/união/`TyVar` a checagem é em runtime. A atribuição comum (sem `as`) segue a
     regra estática do backend, que conhece o callee e coage na chamada;
   - `as`/`is` **não** aceitam nativo (valor nativo no backend já é `E4001`) nem objeto de
     classe (tag `CLASS`; construção dinâmica é o [#219](https://github.com/loxia-lang/loxia/issues/219));
   - o alvo `fn` é validado recursivamente (`_validate_is_type`/`_validate_as_target`);
     `fn` com `TyVar` (função genérica) **não é valor** e o cast dinâmico é recusado com
     mensagem declarada.

3b. **ABI-compatible subtyping (regra do cast).** Em uma **atribuição** comum o backend
conhece o callee real e coage (`Int → Any` na chamada), então a variância pode ser mais
liberal; no **cast** (`as`, estático ou dinâmico) o código gerado para o alvo usa a
representação **do alvo**, e a assinatura real só existe no `LoxFnSig` do closure. Aceitar
`fn(Any) -> Int` como `fn(Int) -> Int` passaria `i64` para um parâmetro de 2 palavras
(`Any`) — UB. Portanto o `is`/`as` exige, por parâmetro e pelo retorno:

- `lox_type_assignable(alvo, real)` — a mesma subtipagem do checker; **e**
- `lox_rep_equal(alvo, real)` — mesma representação de máquina (`Any` 2 palavras; escalar
  `i64`/`f64`/`i1`; opcional escalar `{i1, payload}`; referências/classes/interfaces/
  containers/funções: ponteiro; união de múltiplos não-nil: `Any`).

Assim `fn(I) -> Int` como `fn(C) -> Int` (ponteiro) é aceito; `fn(Any) -> Int` como
`fn(Int) -> Int` é recusado com `R1011` nos dois motores. O tree-walk espelha a mesma regra
(`same_rep` sobre os `Ty`), então a asserção é checada, não confiada. Um adapter de chamada
(que boxaria/desboxaria argumentos e retorno para permitir a variância completa) fica como
alternativa futura, não neste PR.

4. **Narrowing.** `if (f is fn(D) -> R)` refina o caminho para o `FnTy`; a chamada
   `f(args)` usa a assinatura alvo, já garantida pela checagem. `f as fn(D) -> R` idem.

5. **O tree-walk é o oráculo.** O checker registra o `FnTy` de cada `Function`/`Lambda`/
   método (`function_types`), o engine passa esse mapa ao interpreter, e o `LoxFunction`
   carrega a assinatura; `bind`/defaults copiam. `matches_type(FnTy)` usa
   `TypeOps.assignable_fn` com a assinatura real; `as` devolve o callable ou levanta
   `R1011`. O backend espelha a mesma regra em C (`lox_fn_assignable`).

6. **Escopo.** Funções, lambdas, métodos, bound methods e defaults de interface; tipos de
   função opcionais (`fn(...)?`, issue [#225](https://github.com/loxia-lang/loxia/issues/225));
   tipos de função aninhados. Fora: valores nativos, objetos de classe (#219), funções
   genéricas como valor e reificação de tipos.

7. **ABI/desempenho.** O append mantém os três primeiros campos (o código que lê
   `fn`/`env`/`display` continua válido). Chamadas **estáticas** não mudam: a checagem é no
   cast/`is`, não por chamada. O `LoxFnSig` é estático (sem GC, sem alocação por closure);
   o custo é +24 bytes por closure e uma tabela de assinaturas por tipo usado.

## Consequências

### Positivas

- Fecha o buraco de I1/I4 para funções em `Any`: ou o cast/`is` falha nos dois motores, ou
  a chamada é segura. `E3025` passa a ter caminho para função.
- `Any`/campo/lista de callbacks (jsonrpc, `expect`, tabelas de handlers) passam a funcionar
  de verdade, sem cast não checado.
- Sem sintaxe nova e sem tag nova em `LoxValue`; o `LoxFnSig` é estático e determinístico.

### Negativas / custos

- ABI do closure +24 bytes (ADR-0046/0048) e atualização de **todos** os sites de criação.
- `lox_type_assignable` tipo-a-tipo em C (classe/interface/união/container/função) e a
  tabela de assinaturas; mais código de runtime do que o `min/max` sozinho.
- O checker precisa publicar `FnTy` por declaração e o interpreter carregar; um mapa a
  mais no engine.
- Funções genéricas como valor continuam fora (não há como representar `TyVar` em runtime);
  nativo/classe-objeto ficam para PRs próprios.

### Neutras

- `E3007`/`E3013` deixam de ser a resposta para `fn`; continuam para os alvos ainda fora.
- O `LoxFnSig` entra no cache de tipos como os demais descritores; o texto do tipo só
  aparece em `--emit=ll`/diagnóstico interno.
- `print`/`str` de função seguem `<fn nome>`; nada de endereço (I3).

## Alternativas

- **Só aridade** (`min/max` no closure): barato, mas mesma aridade/tipos errados continua
  UB/divergente; teria que ser documentado como asserção não checada — recusado pela
  identidade de I1.
- **Checagem por chamada** (wrapper que valida args/retorno a cada chamada dinâmica):
  custo por chamada e caminho de chamada mais complexo; ainda precisaria da assinatura real
  para ser som. B é melhor: paga uma vez no cast.
- **Subtipagem completa com adapter de ABI** (trampolim que boxa/desboxa/coage args e
  retorno conforme a assinatura real): aceita `fn(Any) -> Int` como `fn(Int) -> Int`, ao custo
  de um call dinâmico genérico no runtime; fica para um ADR/PR futuro. Neste PR, a regra é
  ABI-compatible (3b).
- **Igualdade exata de assinatura**: C bem menor, mas recusa casos seguros
  (`fn(Any) -> Int` usado como `fn(Int) -> Int`) e obriga o usuário a reescrever a
  assinatura; a subtipagem do checker já é a regra estática.
- **Reificar tipos em todo valor**: som máximo, mas ABI/GC/perf em todo o runtime e muda o
  modelo apagado (ADR-0025/0055); overkill.
- **Não permitir cast dinâmico**: mantém #213 aberto e função em `Any` inutilizável.

## Como verificar

- `tests/cases/fn_any.lx` (l6, diferencial): função em `Any`, `is`/`as` com assinatura
  exata, chamada; aridade errada → `is` false/R1011; tipo de parâmetro/retorno errado →
  false/R1011 nos dois motores.
- ABI: `fn(I) -> Int` em `Any` como `fn(C) -> Int` (ponteiro) → aceito e chamável;
  `fn(Any) -> Int` em `Any` como `fn(Int) -> Int` → `R1011` nos dois motores; o mesmo par
  **estático** continua aceito (callee conhecido, backend coage) e chamável.
- Contravariância/covariância: `fn(Any) -> Int` como `fn(Int) -> Int`; `fn(Int) -> Any`
  como `fn(Int) -> Int` (deve falhar); classe/interface nos parâmetros/retorno.
- Aninhados: `fn(fn(Int) -> Int) -> Int` e retorno de função; opcionais
  `fn(Int) -> Int?`; `var f: fn(Int) -> Int?`.
- Variádicos/defaults (`min_params`) e bound methods/defaults de interface.
- `if (f is fn(...)) { f(...) }`; campo/lista/mapa de funções; `--check`/`--emit`;
  `R1011` com assinatura no texto; determinismo.
- `tests/test_checker.py` para os casts estáticos impossíveis e o narrowing; `make check`.

## Emendas

- [ADR-0046](0046-closures-celulas-l4.md): o closure ganha aridade e ponteiro de assinatura;
  o layout antigo é prefixo.
- [ADR-0029](0029-conversoes-math.md)/[ADR-0055](0055-l6-any-casts.md): `as`/`is` cobrem
  `fn`; a checagem é de assinatura, não de tag.
- [ADR-0146](0146-is-as-interface.md): funções passam a ser alvo de narrowing; interface e
  função compartilham a ideia de checagem runtime (tabela de interfaces × assinatura).
