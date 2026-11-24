# ADR-0141 — Checker: soundness de fluxo, merge ciente de saltos e escopo da precisão

- **Status:** accepted (fatia de soundness, gate do corpus e split `TypeOps`/`DeclTable` implementados em 2026-11-24)
- **Data:** 2026-11-24
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0018](0018-narrowing.md), [ADR-0025](0025-is-e-narrowing.md),
  [ADR-0032](0032-narrowing-campos-indices.md),
  [ADR-0045](0045-narrowing-representacao.md),
  [ADR-0086](0086-narrowing-captura-e-merge.md),
  [ADR-0107](0107-adiados-e-nao-objetivos.md),
  [ADR-0139](0139-break-continue.md), [ADR-0140](0140-match-literais.md),
  [`../../TIPOS.md`](../../TIPOS.md) §2, [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** [`loxia_core/semantics/flow.py`](../../loxia_core/semantics/flow.py)
  (chave, merge, `LoopContext`, política), `loxia_core/semantics/type_ops.py`
  (atribuição, unificação, substituição), `loxia_core/semantics/decl_table.py`
  (classes/enums/interfaces e hierarquia), `loxia_core/semantics/checker.py`,
  [`tests/test_checker_flow.py`](../../tests/test_checker_flow.py),
  [`tests/test_checker_sweep.py`](../../tests/test_checker_sweep.py),
  `tests/cases/break_narrowing.lx`, `tests/cases/break_finally.lx`,
  `tests/cases/match_arm_flow.lx`, `tests/cases/errors/break_post_loop.lx`,
  `tests/cases/errors/match_arm_leak.lx`, `tests/corpus_manifest.py`,
  `tests/test_ast_schema.py`

## Contexto

A #160 foi escrita para decidir se valia pagar **precisão** (aliasing, sumários de efeito,
CFG) no checker. Desde então a linguagem ganhou dois construtos de controle de fluxo e o
checker não foi atualizado junto:

- `break`/`continue` ([ADR-0139](0139-break-continue.md)): `visit_break_stmt` e
  `visit_continue_stmt` não fazem nada. `visit_while_stmt` aplica a condição falsa na saída
  do laço **incondicionalmente**, mas `break` sai sem tornar a condição falsa.
- `match` literal ([ADR-0140](0140-match-literais.md)): `_match_enum`/`_match_literal`
  checam cada braço com o estado de fluxo corrente, sem salvar/restaurar/juntar. O último
  braço vaza o seu refino para o resto do programa.

Os dois produzem o mesmo resultado, verificado em 2026-11-24:

```lox
var x: String? = nil
while (x == nil) {
  break
}
print(len(x))       # check: 0 · interpretador: 70 (R1000) · binário: 139 (SIGSEGV)
```

```lox
var x: String? = nil
val k = 1
val r = match k {
  0 => (x = "s")
  _ => "t"
}
print(len(x))       # check: 0 · interpretador: 70 · binário: 139
```

Como o backend consome os tipos publicados pelo checker ([I4](../spec/garantias.md)), um
refino inventado faz o lowering emitir uma chamada de `len` sobre um `String` que é `nil`.
Isso viola **I1** (interpretador × nativo) e a promessa de erro limpo: um programa que
passa no `--check` não pode morrer por sinal.

### Dados que sustentam a decisão

| Medida (2026-11-24) | Resultado |
| --- | --- |
| Falsos positivos em programa válido no corpus golden (319 casos) | 0 |
| `std/` + `examples/` (39 arquivos) | check-clean (`std/bytes.lx` só falha isolado, por mangling) |
| Casos golden que esperam erro de runtime e o check adianta | 38 (todos programas intencionalmente inválidos) |
| Casos diferenciais do backend | 229, **nenhum** cobre narrowing + erro |
| Custo do check (1.500 funções) | ~4% (0,54 s vs 0,58 s) |
| Tamanho do checker | 5.472 linhas, ~199 métodos, ~470 linhas de fluxo, 41 usos diretos de `self._narrowings` |
| Testes de narrowing | 28, todos de precisão; nenhum de soundness |

O protocolo de fluxo existe e funciona em `if`/`elif`/`else`, `while`, `for-in` e `try`
(salvar, checar, juntar), mas é **implícito**: nada obriga um construto novo a cumpri-lo.

## Decisão

1. **A precisão fica em A (status quo).** Aliasing (B), sumários de efeito (C) e
   CFG/points-to (E) permanecem fora, com os gatilhos do
   [ADR-0107](0107-adiados-e-nao-objetivos.md). Precisão não é requisito de correção:
   falso positivo é dívida de usabilidade; furo de soundness é bug.
2. **Soundness é invariante do checker (S1).** Um refino só vale se for dominado por um
   teste em **todos** os caminhos que chegam ao uso. Na dúvida, o refino é derrubado. O
   checker nunca inventa um refino que o caminho não provou.
3. **Corolário de I1 (S2).** `--check` limpo ⇒ o programa não morre por sinal no backend;
   os únicos desfechos são `0`, `65` e `70`. Um `139` é bug de contrato, não "caso de borda".
4. **Merge ciente de saltos (D0)** — o que a precisão precisa hoje, não CFG:

   - **Saltos são terminadores.** `break`, `continue`, `return` e `raise` não caem para a
     instrução seguinte. O código depois deles continua sendo checado (diagnósticos
     permanecem), mas não contribui para o estado de saída do bloco.
   - **`while`.** Entrada `E`, corpo `B` checado com `E + condição-verdadeira`. A saída
     normal (zero iterações e fallthrough) é `join(E, B)` e recebe a **condição falsa**; os
     estados de `break` não a recebem, porque o `break` sai com a condição verdadeira. A
     saída é `join(saída_normal_refinada, estados de break)`. `while true` sem `break` não
     tem saída normal; o checker não modela alcançabilidade, então o estado depois do laço
     é esse merge conservador.
   - **`for-in`.** Saída é `join(E, B, estados de break)`; não há condição-falsa.
   - **`match`.** Cada braço parte de `E`, com os bindings no seu próprio escopo; o estado
     depois do `match` é o join dos braços que produzem valor. O último braço nunca define
     sozinho o estado seguinte.
   - **Ternário e lógico.** `a if c else b` faz fork dos dois braços (com os refinos de `c` e
     `not c`) e a saída é o join. Em `and`/`or`/`??` o operando direito é condicional: a
     saída é `join(estado_antes_do_direito, estado_depois)`. Marcar esses nós como
     `TRANSPARENT` foi o bug que o gate de política não pegou; eles têm teste de
     comportamento próprio.
   - **`try`/`finally`.** O merge do corpo e dos handlers que caem continua. Quando há
     `finally`, as **invalidações** que ele executa (atribuição, chamada de usuário,
     captura) são replicadas nos estados de `break`/`continue` gravados durante o corpo e
     os handlers, porque o `finally` roda antes de o salto concluir. Só invalidações são
     replicadas; refinos do `finally` podem depender do caminho de entrada e não são
     reaplicados. **Limitação declarada:** um `finally` que *estabelece* o refino (ex.:
     `finally { x = "a" }`) não o propaga ao estado do salto, então o programa válido
     `while (x == nil) { try { break } finally { x = "a" } }` seguido de `len(x)` é
     recusado. Aceitar exigiria sumário de efeitos (adiado); é a direção conservadora, não
     um furo.
   - **`if`/`else` como statement.** Cada ramo parte do estado de entrada; a saída é o join
     dos ramos que caem, com os refinos da condição aplicados só ao caminho que passa por
     ela.
   - **`continue`.** O estado no `continue` volta para o topo do laço; para o merge pós-laço
     ele conta como fallthrough (conservador). A ausência de fixpoint é declarada, não
     silenciosa.
5. **Política de fluxo obrigatória.** `STMT_FLOW`/`EXPR_FLOW` classificam cada nó como
   `transparent`, `fork`, `loop`, `jump`, `terminator` ou `isolated`. Um teste
   (`tests/test_checker_flow.py`) percorre as subclasses e **falha** quando aparece um nó
   sem política; os nós de fork (`if`, `match`, ternário, lógico, `try`, laços) têm também
   testes de comportamento que falham se o visitante deixar o estado vazar. O default não é
   "transparente": esquecer é erro de CI, não bug em produção. É o mesmo mecanismo do
   [ADR-0117](0117-ast-manual-e-cobertura-de-visitantes.md) aplicado a fluxo.
6. **Gate "o checker não mente".** `tests/test_checker_sweep.py` percorre todo caso golden
   que espera erro de runtime: se o `--check` está limpo e o interpretador levanta `R1000`,
   `R1001`, `R1005` ou `R1006`, é furo — exceto os casos da allow-list explícita, cujo erro
   depende do **valor** e não do tipo (5 casos: lista de `Bytes` inválida, expoente negativo,
   domínio de `**`, passo de `range` zero e contagem de shift). Casos com `# requires:`
   (capacidade externa) ficam fora, porque o desfecho depende do host. A varredura roda no
   processo (sem CLI por caso) em <1 s. As formas válidas entram no corpus diferencial
   (I1 nos três canais).
7. **Nada muda em runtime ou backend.** Tipos são apagados; só a aceitação e os diagnósticos
   do `--check` mudam. I1/I4 continuam valendo — e passam a valer de verdade nos casos de
   narrowing.

### Regras de invalidação (inalteradas nesta decisão)

Continuam valendo as regras do [ADR-0086](0086-narrowing-captura-e-merge.md) e do
[ADR-0032](0032-narrowing-campos-indices.md): chamada que pode executar código de usuário
derruba refinos de campo/índice e de `var` capturado; atribuição atualiza o refino da raiz;
índice só refina quando literal. O que muda é **quem participa do merge**, não o que
invalida.

## Consequências

### Positivas

- Fim dos furos de fluxo (`break`, `match`, ternário, lógico e `try/finally`); o `--check`
  deixa de aceitar programas que crasham o binário.
- O check pode virar obrigatório ([ADR-0142](0142-check-por-fases.md)) sem mentir sobre o
  que garante.
- Construto de fluxo novo passa a custar uma linha de política e um teste, não uma
  auditoria de 5 mil linhas.
- A precisão deixa de ser tratada como requisito de correção — o que libera adiar B/C sem
  culpa.

### Negativas / custos

- Programas hoje aceitos passam a ser recusados quando a saída do construto de fluxo era
  inventada: os padrões de `break`, `match`, ternário, lógico e `try/finally` do contexto e
  dos testes de soundness. É a correção esperada, mas é mudança observável no `--check`.
  Programas válidos com `break` sob teste impossível continuam aceitos, porque a saída
  normal recebe a condição falsa antes do merge com os saltos.
- D0 mexe em ~150–250 linhas de fluxo e nos testes dos construtos afetados.
- A política de fluxo é cerimônia nova em todo nó de AST novo (mitigada pelo teste).
- O gate de soundness adiciona uma varredura rápida (<1 s) à suíte, com allow-list explícita.

### Neutras

- Alias, efeitos e CFG continuam adiados; não há mudança de sintaxe nem de runtime.
- O merge continua sem fixpoint de laço; isso é limitação declarada, não bug.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| B — alias-only (`val q = p`) | Nenhum programa real pediu; cada alias novo é uma fonte nova de invalidação e de furo, justamente o que a decisão quer eliminar |
| C — sumários de efeito | Com herança/interfaces abertas, o summary só é sound se o override for checado ou a classe for fechada; é feature de linguagem, não plumbing de checker |
| D — CFG-lite com blocos/arestas/fixpoint | Não há programa concreto que exija; reescreve o fluxo e arrisca determinismo de diagnósticos (I3); não evitaria os dois bugs sem a política |
| CFG full / points-to | Desproporcional (ADR-0032/0086); o custo é reescrita e o ganho não é nomeável hoje |
| Só corrigir os dois bugs, sem contrato | O próximo construto de fluxo repete o problema; foi exatamente o que aconteceu com `match` e `break` |
| Correção no backend (nil-check defensivo em `len`) | Defesa em profundidade é bem-vinda, mas a fonte do tipo errado é o checker; duplicar regra viola I4 |

## Como verificar

- As regressões de soundness em `tests/test_checker_flow.py`: `break` pós-laço, vazamento do
  último braço de `match`, vazamento do ternário e do lado direito de `and`, e `break` dentro
  de `try/finally` que atribui. O `--check` recusa todos (E3007). Com o check no `run`
  ([ADR-0142](0142-check-por-fases.md)) ligado, os dois programas do contexto também viraram
  casos golden de erro (`errors/break_post_loop.lx`, `errors/match_arm_leak.lx`).
- As formas **válidas** de `break`/`match` com narrowing entram no corpus diferencial
  (`break_narrowing.lx` em l2, `break_finally.lx` em l2, `match_arm_flow.lx` em l6), onde I1
  compara interpretador e binário nos três canais.
- `tests/test_checker_flow.py` falha se um `Stmt`/`Expr` novo não tiver política, cobre a
  precisão preservada (join dos braços, saída do `while`, laço aninhado, `break` guardado,
  código morto) e fixa a política esperada dos nós de fork (incluindo ternário e lógico).
- Corpus golden continua com 0 programa válido recusado.
- `make check` verde.
- `tests/test_checker_sweep.py` roda a varredura "check limpo ⇒ sem
  `R1000`/`R1001`/`R1005`/`R1006`" sobre todos os casos que esperam erro de runtime, com a
  allow-list de 5 casos dependentes de valor e sem os casos com `# requires:` (host). Ela
  falha se aparecer um furo novo **ou** se a allow-list ficar obsoleta (um caso que deixou
  de ser check-clean ou mudou de código).

**Revisitar quando:** houver `break` com rótulo/`loop` explícito, `match` estrutural com
guards, contratos estáticos, ou um programa real que precise de invariantes de laço; ou se
o corpus de conformidade ([ADR-0115](0115-corpus-de-conformidade-adiado.md)) exigir a regra
de narrowing escrita para uma implementação externa.

## Referências

- #160 (decisão), #112 (dívida de checker), #164 (`break`/`continue`), #167 (`match` literal)
- [ADR-0014](0014-identidade-e-invariantes.md) (portão), [ADR-0059](0059-i4-check-limpo-compila.md) (I4)
- [`../spec/garantias.md`](../spec/garantias.md), [`../spec/semantica.md`](../spec/semantica.md)
