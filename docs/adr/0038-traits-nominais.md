# ADR-0038 — Traits: nominais, com métodos default, pós-MVP

- **Status:** superseded by ADR-0080 (nomenclatura: "traits" passou a "interfaces") e ADR-0081 (constraints)
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0008](0008-heranca-class-parens.md) (herança simples),
  [ADR-0014](0014-identidade-e-invariantes.md) (I1–I3 e portão),
  [ADR-0026](0026-freeze-1.0.md) (freeze), [ADR-0027](0027-generics-t3b.md) (generics),
  [ADR-0031](0031-backend-nativo.md) (backend), [ADR-0080](0080-interfaces-nominais-implementacao.md)
  (implementação e nome),
  [`../../TIPOS.md`](../../TIPOS.md) §1/§2.1, [`../../TODO.md`](../../TODO.md) §9/§11

> **Nota de nomenclatura (2026-11-15):** o modelo decidido aqui continua válido — nominal,
  `implements`, métodos default. O conceito passou a se chamar **interface**
  ([ADR-0080](0080-interfaces-nominais-implementacao.md)): a v1 é uma interface nominal
  com defaults, não um trait de Rust/Scala/PHP nem um `Protocol` estrutural do Python.
> O texto abaixo é histórico e mantém a palavra "trait". As constraints (`T: Trait`) foram
> entregues na forma `T: Interface + Ord + Num` pelo
> [ADR-0081](0081-constraints-generics.md).

## Contexto

`D-17` estava aberto com recomendação nominal, enquanto o `TODO.md` dizia
"traits/protocolos estruturais" e o ADR-0026 colocava traits fora da 1.0. O `M5` incluía
T6 ("traits + exaustividade") e a regra de codegen pausa o L4 até o M5 fechar — ou seja,
uma feature pós-1.0 estava no caminho crítico do backend.

Não há caso de uso concreto hoje: polimorfismo já existe via superclasse; `List`/`Map`/
`Range` são built-ins; não há protocolo de stdlib. O valor maior de traits está nas
constraints de generics (algo como `fn max[T: Comparable]` com `a: T` e `b: T`), que puxam especialização/
dicionários na monomorfização e são um passo separado.

## Decisão

1. **Nominal.** A classe **declara** que implementa o trait; o checker verifica que os
   métodos existem e têm assinaturas compatíveis. Não há conformidade estrutural: uma
   classe com os métodos certos, mas sem `implements`, **não** é o trait. Isso alinha com
   I2 (nada implícito), dá erro perto da declaração e mapeia direto para vtable/type-id
   no backend.
2. **Sintaxe.** `trait Nome { ... }`; `class C(A) implements T1, T2 { ... }`; sem
   superclasse, `class C implements T`. `implements` é palavra **contextual** (só é
   especial depois do cabeçalho de classe), para não quebrar código que use `implements`
   como identificador. Rejeitada a forma `class C(A, T1, T2)`: o primeiro item seria
   superclasse e os demais traits, o que é ambíguo quando só há trait e obriga o runtime a
   decidir sem checker.
3. **Métodos default fazem parte da v1 futura.** O trait pode ter assinaturas e corpos; a
   classe herda o corpo e pode sobrescrever. Conflito entre dois traits com a mesma
   assinatura e corpos diferentes exige override explícito na classe (erro se não houver).
   Como chamar o default de um trait específico (`super`? `T::m()`?) fica em aberto para o
   ADR de implementação.
4. **Sem constraints de generics na v1.** Traits entram primeiro como **tipo** de
   parâmetro/retorno/campo; `fn f[T: T]` e traits genéricos ficam para uma segunda
   fase, junto da monomorfização especializada.
5. **Implementação pós-MVP, fora do M5.** O M5 passa a ser T6a (classes/métodos
   genéricos) + T6c (`match`/enums e exaustividade). Traits não são pré-requisito de
   L4/L6: monomorfização e layout de classe não dependem deles.
6. **Runtime type-erased.** O valor é a instância da classe; chamadas por tipo de trait
   despacham pela busca de método que já existe. O backend só precisa de vtable/type-id
   quando compilar chamadas via trait (L6); até lá, rejeita com 65. `is Trait`/`as Trait`
   ficam adiados (exigem mapa classe→traits no runtime).

## Em aberto para a implementação

- Resolução de conflito de defaults (override obrigatório? erro? ordem de declaração?).
- Sintaxe para chamar o default de um trait específico e se ele pode chamar `this` e
  outros métodos do trait.
- Traits genéricos e constraints (`T: Trait`), incluindo coerência/orphan rules.
- Herança de traits (`trait A : B`) e traits como superclasse (não na v1).
- `is`/`as` em trait e custo de manter o mapa classe→traits.
- Backend: vtable/type-id, custo no layout e interação com monomorfização.

## Consequências

- `D-17` fechado: nominal, `implements`, métodos default; sem código novo agora.
- `docs/roadmap.md`/`TIPOS.md` deixam de tratar traits como bloqueio do M5/L4.
- A sintaxe existente não muda; `implements` é contextual e só aparece em declaração de
  classe.
- O ADR-0026 continua valendo: traits não estão na 1.0.

## Alternativas rejeitadas

- **Estrutural:** implícito (contra I2), conformidade acidental
  (`fn len() -> Int` vira `Sized` sem querer), erro no ponto de uso em vez da declaração,
  e resolução por forma é pior para vtable/type-id no LLVM.
- **Implementar agora:** custo de parser/AST/checker/testes/docs sem dor concreta, e
  manteria o M5 (e o L4) bloqueado por uma feature pós-1.0.
- **Sem métodos default:** o usuário escolheu defaults; eles reduzem duplicação e são o
  motivo comum para usar trait em vez de superclasse.
- **`class C(A, T1, T2)`:** ambíguo entre superclasse e trait.
