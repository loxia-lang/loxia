# ADR-0044 — Identidade de classe em runtime (`is`/`as`/`except`)

> **Atualização (2026-11-26):** o rebinding de classe continua aceito apenas pelo escape
> `Base = OtherBase as Any` (exercitado pela suíte oficial), e objeto de classe **não** é
> valor de função ([ADR-0150](0150-objeto-de-classe-nao-e-valor-de-funcao.md)). Um `Any`
> que não guarda classe num slot de classe passou a ser erro de check
> ([#247](https://github.com/loxia-lang/loxia/issues/247)).

- **Status:** accepted (tree-walk implementado; backend L5 pendente)
- **Data:** 2026-11-13
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0025](0025-is-e-narrowing.md), [ADR-0042](0042-excecoes.md),
  [ADR-0043](0043-layout-l5-classes.md), [`../../TODO.md`](../../TODO.md) §6.6,
  [`../spec/semantica.md`](../spec/semantica.md)

## Contexto

O tree-walk comparava **nomes** em `is`/`as` (`is_instance_of(nome)`, `matches_type`) e em
`except` (`_matches_exception`). Isso funciona para classes de topo com nomes únicos, mas
quebra com **classes locais** (a suíte oficial declara `class` dentro de função/bloco) e com
**rebinding de classe** (`Base = OtherBase`). Classes são valores de primeira classe; a
identidade natural é o objeto de classe, não a string do nome.

## Decisão

1. **Identidade = objeto de classe.** `x is Foo` resolve `Foo` no ambiente léxico em tempo
   de execução e compara a classe da instância com ela e com sua cadeia de superclasses.
   `x as Foo` usa a mesma checagem. `except Tipo` compara o objeto de classe já avaliado
   pelo handler.
2. **Semelhança de subclasse.** `Derived is Base` é verdadeiro; a comparação sobe
   `classe -> super` por ponteiro. Classes locais com o mesmo nome são classes diferentes.
3. **Enums.** `is Cor` continua por nome: enums são de topo e únicos; o objeto de enum não
   é uma classe. `match` de enum não muda.
4. **IDs.** Cada classe ganha um `id` inteiro determinístico (ordem de declaração no topo;
   ordem de execução nas locais) para vtable, mangling e tags do L6. O id **não** é usado
   para responder `is`/`as`/`except`; a resposta é por objeto/ponteiro.
5. **Rebinding.** Como `is` resolve o binding atual, `Base = OtherBase` faz `x is Base`
   seguir `OtherBase`. É o comportamento dinâmico e documentado; o checker pode estreitar
   pelo tipo estático, então código que reatribui classe e usa narrowing deve ser tratado
   como caso dinâmico (limitação registrada).
6. **Sombra de tipo por variável.** Se o nome do tipo estiver sombreado por um valor que
   não é classe no ponto do `is`, o runtime usa a classe do binding léxico quando existe;
   sem classe, cai no comportamento por nome (compatibilidade). O caso patológico fica
   documentado.

## Implementação no tree-walk

- `LoxClass.is_subclass_of_class(klass)` e `LoxInstance.is_instance_of_class(klass)`
  comparam ponteiros; `is_instance_of(nome)` continua para compatibilidade.
- `matches_type(value, ty, class_lookup)` recebe um resolvedor para `ClassTy`; o
  interpretador passa `_class_for_type(nome)`, que procura o binding no ambiente atual e
  só aceita `LoxClass` (enums seguem por nome).
- `_matches_exception` usa o objeto de classe para `LoxInstance`; para
  `LoxExceptionValue` (builtins) compara o nome, pois o valor não carrega o objeto.
- `ClassObjectTy` (classe como valor) continua por nome de subclasse; não é `is` de
  instância.

## Alternativas rejeitadas

- **ID estático por declaração:** estável para codegen, mas exige propagar ids por
  AST/checker, resolver classes locais com escopo e define `is` como estático mesmo após
  rebinding. Fica para o L6 se a monomorfização precisar.
- **Nome (status quo):** simples, mas falso positivo para classes locais homônimas e preso
  ao nome no rebinding.
- **Só classes de topo:** quebraria a suíte oficial e uma feature já suportada.

## Como verificar

- Golden: classe local homônima não é a classe global (`local is A` falso), subclasse é a
  base (`Derived() is Base` verdadeiro), `as` com classe errada vira erro de runtime.
- `except` com subclasse de exceção do usuário.
- Teste diferencial no L5: `is`/`as`/`except` com a mesma saída do interpretador.
