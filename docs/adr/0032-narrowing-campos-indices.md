# ADR-0032 — Narrowing de campos e índices (T5)

- **Status:** accepted
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0018](0018-narrowing.md), [ADR-0025](0025-is-e-narrowing.md),
  [ADR-0024](0024-mutacao-monomorfica.md), [`../../TODO.md`](../../TODO.md) §2,
  [`../../TIPOS.md`](../../TIPOS.md) §2.2, [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** [`src/semantics/checker.py`](../../src/semantics/checker.py),
  [`tests/test_checker.py`](../../tests/test_checker.py)

## Contexto

O narrowing da v1 (ADR-0018/0025) refina **variáveis**: a chave é o nome mais o índice do
escopo de declaração. `obj.campo` e `lista[i]` ficam de fora, então um campo `String?`
obriga o usuário a copiar para uma variável local ou a usar `!` (que não existe) mesmo
depois de `if (p.nome != nil)`.

T5 pedia três coisas: refinar campos/índices, invalidar quando o valor muda e melhorar o
merge de fluxo. Sem invalidação, o refino seria **inseguro** — o caso clássico é
`if (p.nome != nil) { p.nome = nil; len(p.nome) }`.

## Decisão

1. **Chave de refinamento = raiz + caminho.** A raiz é o nome da variável declarada
   (com o índice do escopo, como na v1); o caminho é uma tupla de segmentos:
   - `("field", "nome")` para `p.nome`;
   - `("index", (tipo, valor))` para índice **literal** (`xs[0]`, `m["k"]`, `m[true]`).
     O tipo entra na chave para `true` não colidir com `1` (o `isinstance(True, int)` do
     Python).

   Caminhos encadeados são permitidos: `p.endereco.rua`, `xs[0].nome`.

2. **Só índice literal refina.** `xs[i]` (variável/dinâmico) não refina: o checker não
   rastreia o valor de `i`, e refinar seria arbitrário. A consulta existe para os três
   formatos que têm caminho: `Variable`, `Get` e `Index`.

3. **Consulta:** ao inferir `Get`/`Index`, o checker procura o caminho refinado **antes**
   de calcular o tipo normal; se achar, o nó recebe o tipo estreitado (e o `types` do
   backend também).

4. **Invalidação por mutação:**
   - `p = ...` (atribuir à raiz) remove **todos** os caminhos daquela raiz;
   - `p.nome = ...` e `xs[0] = ...` removem aquele caminho e os mais fundos com o mesmo
     prefixo;
   - `val`/`var` novos (sombreamento) removem os refinamentos da raiz no escopo atual.

5. **Fluxo:** `while (cond)` aplica o refino **oposto** depois do laço (na saída normal a
   condição é falsa), então `while (x != nil) { x = nil }` deixa `x` como `nil` no resto do
   bloco. `if` continua como antes: `return` em um ramo aplica o refino do outro; sem
   `return`, os refinos valem só dentro de cada ramo (o join os descarta).

6. **Merge completo em CFG fica fora.** O ADR-0018 já julgou CFG desproporcional ao
   estágio; o que entra aqui é o join pós-laço, que é local e barato. Um `if`/`else`
   sintetizado em CFG continua no `TODO.md`.

## Limitações (honestas)

- **Sem aliasing:** uma chamada que muta `p.nome` (método, closure capturando `var`, outra
  referência à mesma instância) **não** invalida o refino. É a mesma limitação que a v1 já
  tinha para `var` capturado; a diferença é que agora ela também vale para campos.
- Mutação de coleção (`xs.push`, `m.remove`) não invalida índices/refinos da raiz; o refino
  é por caminho, não por "versão" do contêiner.
- Refino não atravessa atribuição a `var`: atribuir invalida, mesmo atribuindo o mesmo tipo.
- Índice precisa ser literal; sem `xs[-1]`/`xs[i+1]` (o primeiro nem existe na linguagem).

## Consequências

- `if (p.nome != nil) { print len(p.nome) }` passa no `--check` sem variável auxiliar,
  o mesmo para `List[T?]` e `Map[K, V?]`.
- O comportamento de invalidação é previsível e testado (`test_narrowing_field_*`).
- O checker segue **não** sendo um sistema de efeitos: quem muta por referência deve
  re-testar ou usar `val`.

## Alternativas rejeitadas

- **CFG/SSA completo no checker:** desproporcional; o ADR-0018 já registrou.
- **Refinar qualquer expressão** (chamadas, `a + b`): exigiria modelar efeitos.
- **Chave pela identidade do nó de AST:** não atravessa ocorrências — o `Get` do `if` e o
  do corpo são nós diferentes.
- **Invalidar tudo a cada chamada:** seguro, mas mataria o refino em qualquer programa com
  função; o ganho não paga.
