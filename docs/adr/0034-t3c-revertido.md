# ADR-0034 — Revisão: parâmetro de `fn` continua explícito (T3c rejeitado)

- **Status:** accepted; substitui a parte **T3c** do [ADR-0033](0033-inferencia-t3c-t4.md)
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0020](0020-assinaturas-explicitas.md),
  [ADR-0022](0022-lambdas.md), [ADR-0027](0027-generics-t3b.md),
  [ADR-0033](0033-inferencia-t3c-t4.md), [`../../TODO.md`](../../TODO.md) §2,
  [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** [`src/semantics/checker.py`](../../src/semantics/checker.py),
  [`tests/test_checker.py`](../../tests/test_checker.py)

## Contexto

O T3c foi implementado junto do T4: parâmetro sem anotação em função de topo virava um
`TyVar` implícito, e a função passava a ser um esquema (`fn igual` ≡ `forall T, U. ...`).
A revisão levantou três problemas:

1. **Contrato de API.** O [ADR-0020](0020-assinaturas-explicitas.md) decidiu que a
   assinatura de `fn` é explícita porque é superfície: quem lê a declaração vê o contrato.
   Com o T3c, a **ausência** de anotação passa a significar quantificação universal, sem
   marcador. O tipo da função não está mais na declaração.
2. **Omissão ambígua (ação à distância).** O efeito da omissão depende do corpo:
   `fn primeiro(x, y) -> Int { return y }` generaliza `x`; `fn dobro(x) -> Int { return x * 2 }`
   falha em `x * 2`. O erro fala em "operandos", não em "parâmetro de tipo".
3. **Footgun de primeira classe.** `fn igual(x, y) -> Bool` **não é valor** (o esquema não
   pode ser passado/impresso), enquanto `fn igual(x: Int, y: Int) -> Bool` é. Omitir
   anotação tira a função de posições de valor — o oposto do que a omissão sugere.

A inferência em si não é o problema: locais já inferem (ADR-0010) e o T3b infere
argumentos de tipo na chamada. O problema é **quantificar implicitamente a assinatura de
API**.

## Decisão

1. **T3c é revertido.** `fn` volta a exigir anotação em **todos** os parâmetros, como no
   ADR-0020. O caminho para polimorfismo explícito continua sendo o T3b:
   `fn igual[T, U]` com `x: T` e `y: U`.
2. **T4 é mantido.** `val f = fn(x) => x` continua inferindo parâmetros e generalizando o
   esquema. A justificativa é a distinção: **contrato de `fn` = explícito; tipo de
   expressão = inferido**. Lambda é expressão (o ADR-0022 já inferia parâmetro por
   contexto), `val` é imutável e geralmente local.
3. **T3c-v2 (HM-lite) fica registrado no TODO**, não implementado agora: inferir o tipo do
   parâmetro **pelo uso no corpo** (unificação), em vez de tratá-lo como universal por
   omissão. `x * 2` ligaria `x` a `Int`; `x == y` generalizaria porque `==` não restringe.
   É a correção real do problema, mas exige unificação no corpo e mensagens novas.

## Consequências

- `fn igual(x, y) -> Bool` volta a ser erro (`Parameter 'x' needs a type annotation.`).
- Quem quiser o comportamento genérico escreve `fn igual[T, U]` (T3b) ou anota um tipo
  concreto; quem quiser o atalho usa `val id = fn(x) => x` (T4).
- Os testes de T3c foram removidos; o teste de método com parâmetro sem anotação continua
  (agora é o mesmo erro de qualquer `fn`).
- A documentação (spec, TODO, TIPOS, CHANGELOG) registra o T3c como **rejeitado**, não como
  pendente.

## Alternativas

- **Manter T3c e documentar como exceção ao ADR-0020:** rejeitado — manteria o footgun e a
  omissão ambígua; a exceção custaria a clareza do contrato.
- **Implementar HM-lite agora:** adiado — precisa de unificação no corpo (operadores
  numéricos ligando `TyVar` a `Int`/`Float`, truthiness, `len`) e revisão de mensagens;
  é maior que o próprio T3c e merece decisão/testes próprios.
- **Reverter T4 também:** rejeitado — lambda é expressão e o esquema é local; o custo
  (esquema não é valor) é o mesmo que o T3b já aceita para funções genéricas explícitas.
