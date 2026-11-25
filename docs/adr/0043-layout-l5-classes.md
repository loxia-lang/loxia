# ADR-0043 — Layout L5: classes, campos, vtable e `init`

> **Atualizado por** [ADR-0145](0145-campo-any-slot-largo.md): o slot de campo não é mais uniformemente `i64` — campo `Any` ocupa duas palavras, com offset absoluto por campo.

- **Status:** accepted (desenho; backend L5 pendente)
- **Data:** 2026-11-13
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0008](0008-heranca-class-parens.md), [ADR-0009](0009-defaults-e-campos.md),
  [ADR-0031](0031-backend-nativo.md), [ADR-0040](0040-generics-classes-desenho.md),
  [ADR-0044](0044-identidade-classe.md), [`../../TODO.md`](../../TODO.md) §6.6,
  [`../spec/semantica.md`](../spec/semantica.md)

## Contexto

O L4 (closures) está liberado e o L5 (objetos) é o próximo passo do backend. O tree-walk já
define a semântica de classes, campos, herança, `this` e `super`; o layout nativo precisa
reproduzi-la byte a byte (I1). Este ADR fixa o contrato de layout **antes** do codegen.

Fatos do tree-walk que o layout tem que respeitar:

- `LoxClass` funde os campos da superclasse na criação da classe; a ordem é sempre base →
  derivada, na ordem de declaração.
- Inicializadores de campo são **constantes** ([ADR-0009](0009-defaults-e-campos.md)):
  rodam na construção da instância, antes do `init`, e não veem `this`.
- `init` herdado é usado quando a subclasse não define um; `super.init(...)` chama o da
  base explicitamente.
- Campos duplicados na cadeia são erro de runtime; `val` só pode ser atribuído uma vez.
- Classes são valores de primeira classe e podem ser locais.

## Decisões

1. **Instância.** `{ ptr classe, campos... }`. O primeiro campo é o ponteiro para o
   descritor da classe (vtable/tipo). Os campos vêm **base primeiro**, na ordem de
   declaração; a derivada anexa os seus. O prefixo é compatível: o offset de um campo da
   base é o mesmo na derivada.
2. **Descritor de classe.** `{ ptr super, i32 id, ptr nome, ptr vtable, i32 n_campos }`
   (o nome serve para `print`/`repr`; o id para mangling/tags do L6). Classes de topo são
   descritores estáticos; classes locais ganham descritor em runtime, na ordem de execução,
   com id sequencial determinístico.
3. **Vtable.** Ordem de declaração dos métodos. A derivada copia a vtable da base, o
   override substitui o slot e métodos novos são anexados. `init` **não** entra na vtable:
   o construtor chama o `init` encontrado na cadeia; `super.m()` é chamada **direta** à
   implementação da base, passando o mesmo `this`.
4. **`this`.** Primeiro parâmetro implícito dos métodos e do `init`; acesso a campo é load
   no offset fixo. Não há `self`.
5. **Campos.** Sem campo dinâmico; declarar de novo na mesma classe ou em subclasse é erro,
   assim como campo com o mesmo nome de um método (o checker passa a policiar; o runtime
   já rejeita a duplicata). `val` é imutável depois do `init`; `var` é mutável.
6. **Inicialização.** Os inicializadores constantes rodam base → derivada, uma vez por
   instância. Campos sem inicializador precisam ser atribuídos no `init` (ou no
   `super.init`). O runtime mantém um **bitmap de inicialização** por campo (ou por campo
   obrigatório): cada atribuição marca o bit, `val` dupla é erro, e ao fim do `init` a
   checagem percorre os campos na ordem base → derivada, reportando o primeiro faltante.
   A prova estática no checker pode eliminar o bitmap depois; não no MVP.
7. **Construção.** Alocar instância, gravar o ponteiro da classe, rodar inicializadores,
   chamar `init`, verificar o bitmap, devolver a instância. A aridade vem do `init`
   encontrado na cadeia (inclusive herdado).
8. **Classes locais.** O L5 suporta classes locais (o tree-walk já suporta): o descritor é
   criado quando a declaração executa e o binding vive no ambiente léxico. O id é
   sequencial por execução; a ordem é determinística para a mesma entrada.
9. **Memória e determinismo.** Arena/alocação do backend; sem endereço, timestamp ou ordem
   de hash na saída (I3). Ordem de campos, vtables e ids é a de declaração.
10. **Escopo do L5.** Classes de topo e locais, herança simples, `this`, `super`, `init`.
    Ficam para depois: herança genérica/reificação (ADR-0040), traits, `Any` boxeado,
    exceções e enums no nativo (L6).

## Alternativas rejeitadas

- **Dicionário dinâmico de campos no nativo:** perde offsets fixos, prefixo compatível e
  previsibilidade; é o que o ADR-0009 já eliminou na linguagem.
- **Ordem de campos por hash/nome:** determinística só se ordenada, mas quebra o prefixo
  natural da herança e complica a compatibilidade binária.
- **Vtable só na classe derivada (sem prefixo):** `super` e chamadas virtuais herdadas
  exigiriam lookup por nome em runtime.
- **Sem bitmap, confiando no checker:** o checker atual não prova inicialização herdada;
  o runtime é a spec até o L6.

## Como verificar

- Testes de ordem de campo/inicialização e erro de campo faltante no tree-walk (já
  existentes; ampliar na implementação).
- No L5, teste diferencial: mesma saída do interpretador para campos herdados, `init`,
  `super`, `this`, classes locais e erro de campo não inicializado.
