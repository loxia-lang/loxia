# ADR-0086 — Narrowing avançado: captura de `var` e merge de fluxo

- **Status:** accepted (implementado)
- **Data:** 2026-11-15
- **Relaciona:** [ADR-0018](0018-narrowing.md), [ADR-0025](0025-is-e-narrowing.md),
  [ADR-0032](0032-narrowing-campos-indices.md),
  [ADR-0045](0045-narrowing-representacao.md), [`../../TODO.md`](../../TODO.md) §8,
  [`../../TIPOS.md`](../../TIPOS.md)

## Contexto

O narrowing já cobria `T?`, `is T`, truthiness, `and`/`or`, `while`, early return e
campos/índices literais. O item “uniões + narrowing” do TODO continuava 🟡 por duas
lacunas:

1. **soundness:** um `var` capturado por closure podia ser mutado durante uma chamada sem
   invalidar o refino do chamador;
2. **precisão:** os refinos eram locais ao ramo; um `if`/`else` em que os dois caminhos
   eliminam `Int` não deixava `x: String` para o resto do bloco.

A primeira é um falso negativo (`--check` aceita programa que falha em runtime); a segunda
é um falso positivo (obriga reescrever código correto).

## Decisão

### 1. `var` capturado (P2)

- O resolver marca a declaração de uma variável mutável quando ela é atribuída dentro de
  uma função/lambda que a captura. Locais usam o **token de declaração**; globais usam o
  nome (o resolver não resolve globais para profundidade).
- O checker recebe esses conjuntos e, **depois de uma chamada que pode executar código do
  usuário**, remove os refinos de variável capturada.
- Chamadas nativas puras (`print`, `len`, `str`, `repr`, `chars`, `range`, métodos de
  `List`/`Map`, módulos nativos) não invalidam: elas não executam closures do usuário.
  Chamadas de função/método/construtor/valor de função invalidam.
- `for-in` sobre classe/interface (iterador de usuário) também invalida; sobre
  Range/String/List/Map/tupla não há código do usuário.
- O corpo de toda função/lambda é checado com um **estado de fluxo vazio**: refinos do
  chamador não valem dentro de uma função que pode executar depois. Ao sair, o estado do
  chamador é restaurado.
- A regra é conservadora: uma chamada de usuário invalida mesmo que não alcance a closure.
  Não há points-to/efeitos.

### 2. Estado de fluxo e merge (P3)

- Os refinos vivem em um **mapa único**: `(índice_da_declaração, nome, caminho) -> tipo`.
  O índice distingue shadowing sem pilha de escopos.
- `if`/`elif`/`else`:
  - cada ramo é checado a partir do estado de entrada;
  - ramo que sempre retorna não contribui para a continuação;
  - sem `else`, o ramo implícito é a entrada com os refinos da condição falsa;
  - os ramos que caem no fim são combinados por **interseção de chaves** e **união dos
    tipos**; se um ramo não tem uma chave, ela é descartada;
  - com um ramo que retorna, vale o estado do outro.
- `while`: o corpo é checado com a condição verdadeira; na saída junta-se a entrada com a
  saída do corpo (o laço pode executar zero vezes) e aplica-se a condição falsa.
- `for-in`: mesma junção de zero iterações; a variável do laço não vaza.
- `try`: corpo e handlers que caem no fim são unidos; handler que sempre retorna não
  contribui. `finally` é checado sobre o estado unido.
- Atribuição a variável atualiza o refino para o tipo atribuído (depois de invalidar os
  refinos antigos); isso é seguro e necessário para o merge.
- O merge é **estruturado**; não há CFG explícito, SSA, fixpoint de laços, aliasing de
  referências nem efeitos de chamada.

### 3. Representação

Nada muda no runtime/backend. `storage_types` continua o tipo declarado e o lowering não
usa o tipo de fluxo para escolher representação ([ADR-0045](0045-narrowing-representacao.md)).

## Consequências

- O caso abaixo passa a ser recusado no `--check` (antes passava e falhava em runtime):

  ```lox
  var x: String? = "a"
  val clear = fn() { x = nil }
  if (x != nil) {
    clear()
    print(len(x))
  }
  ```

- O merge elimina falsos positivos:

  ```lox
  fn f(x: Int | String, c: Bool) -> String {
    if (c) { if (x is Int) { return "i" } }
    else   { if (x is Int) { return "j" } }
    return x
  }
  ```

- Chamadas de usuário após um refino continuam perdendo precisão; chamadas nativas puras
  não.
- Campos/índices seguem com invalidação conservadora em qualquer chamada (ADR-0045).
- Aliasing completo, closures mutando variáveis de formas não rastreadas por atribuição e
  efeitos de métodos continuam fora; a limitação é declarada, não prometida.

## Alternativas

| Alternativa | Por que não |
| --- | --- |
| Nunca estreitar `var` capturado | Perderia o uso antes da chamada, que é seguro |
| Invalidar em toda chamada, inclusive `print`/`len` | Falsos positivos em código comum |
| CFG/SSA completo | Custo desproporcional e não há dor demonstrada além do merge estruturado |
| Points-to/aliasing completo | Semanas a meses, perde precisão; fica fora |
| Não atualizar o refino na atribuição | Impede o merge de ramos que atribuem o mesmo tipo |

## Como Verificar

- `tests/test_checker.py`: `test_narrowing_captured_*`,
  `test_narrowing_user_iterator_invalidates_captured_var`,
  `test_narrowing_merges_both_branches`, `test_narrowing_merges_one_returning_branch`,
  `test_narrowing_merge_keeps_*`, `test_narrowing_merge_of_field_paths`,
  `test_narrowing_for_in_does_not_leak_body_refinement`,
  `test_narrowing_try_ignores_returning_handler` e
  `test_narrowing_try_joins_falling_through_handler`.
- `make check` e `make bench`.
