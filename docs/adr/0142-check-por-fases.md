# ADR-0142 — `--check` por fases: gradual no `test`/CI, bloqueio no `run` depois

- **Status:** accepted (fase 1; fases 2–3 com gatilho declarado)
- **Data:** 2026-11-24
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0010](0010-tipagem-estatica.md),
  [ADR-0020](0020-assinaturas-explicitas.md),
  [ADR-0059](0059-i4-check-limpo-compila.md),
  [ADR-0141](0141-soundness-de-fluxo-do-checker.md),
  [`../spec/garantias.md`](../spec/garantias.md),
  [`../spec/erros.md`](../spec/erros.md), #160
- **Implementação:** `loxia/engine.py`, `loxia/cli_args.py`, `loxia/cli_commands.py`,
  `loxia/test_runner.py`, `.github/workflows/ci.yml`, `docs/spec/`, `tests/`

## Contexto

Hoje o checker é **opt-in**: `run` e o REPL não checam (nem avisam), `--check` checa e não
executa, `--emit` exige o checker e o LSP o roda a cada edição. Um programa com
`fn f(x: Int)` chamado com `"texto"` executa sem diagnóstico; o mesmo programa é recusado
pelo `--check` e pelo `--emit`.

Sob o `--check`, anotação de parâmetro e retorno é **obrigatória** (E3004,
[ADR-0020](0020-assinaturas-explicitas.md)). Isso significa que "tornar o check obrigatório"
hoje equivale a "tornar as anotações obrigatórias": no check estrito os 120 casos da suíte
oficial falham, e suprimir E3004 derruba as falhas para 42 — das quais 36 são casos que
esperam erro de runtime. Tornar o check obrigatório, portanto, não é só ligar um passo:
exige separar **check** de **anotações obrigatórias**.

Medidas de 2026-11-24 (as mesmas do [ADR-0141](0141-soundness-de-fluxo-do-checker.md)):

| Medida | Resultado |
| --- | --- |
| Falsos positivos em programa válido (319 golden + 39 std/examples) | 0 |
| Custo do check | ~4% (1,5 mil funções) |
| Casos golden que mudariam de exit 70 → 65 | 22 (todos programas inválidos) |
| Casos da suíte oficial com erro de runtime esperado que virariam erro de compilação | 36 |
| Casos de erro de runtime do corpus recusados pelo check | 38 de 71 |
| LSP | já checa a cada edição |

O custo real do "obrigatório" não é performance nem falso positivo no corpus: é que, com o
check bloqueando, **um falso positivo de narrowing passa a impedir a execução**. O padrão

```lox
if (p.nome != nil) {
  p.registrar()       # chamada de usuário derruba todo refino de campo/índice
  print(len(p.nome))  # falso positivo (ADR-0032/0086)
}
```

hoje é um erro só no `--check`; com bloqueio, vira "não consigo rodar". Pior: o diagnóstico
é `INVALID_OPERANDS`, que não é `lowerable`, então adiar os rebaixáveis não o neutraliza.

## Decisão

O check vira obrigatório **em fases**, separando "checar" de "bloquear" e de "exigir
anotação".

### Fase 1 — entra agora, sem mudar `run`

1. **Modo gradual** (`--gradual`, em `check`/`run`/`test`): anotação ausente (E3004) vira
   **aviso** e o tipo do parâmetro/retorno/field é `Any`; o resto do check continua estrito.
   Isto não substitui o `--check` estrito, que continua o default do comando.
2. **`loxia test` checa** cada `*_test.lx` no modo gradual e falha em erro de tipo real;
   `--no-check` desliga por arquivo/execução. Teste é o lugar onde o check obrigatório tem
   risco zero: o código é estável, anotado e roda em CI.
3. **CI deste repositório** roda `loxia check` estrito em `std/` e `examples/` (já são
   check-clean) e `loxia test` gradual. O corpus golden continua sendo executado como hoje.
4. `run` e REPL **não mudam** nesta fase.

### Fase 2 — gatilho: ADR-0141 implementado e uma release com a fase 1 verde

5. **`run` resolve e checa** no modo gradual, **antes** de executar, e bloqueia erro de tipo;
   `lowerable` continua adiado ao runtime (o interpretador levanta a mensagem/exit 70 que já
   emite, preservando o corpus). O REPL checa em modo gradual e **só avisa** (não bloqueia
   um snippet interativo).
6. **Escape:** `--no-check` por uma release, documentado como migração.
7. **Migração declarada:** os 22 casos golden que esperam erro de runtime passam a `expect
   error`; os 36 casos da suíte oficial com erro de runtime esperado passam a erro de
   compilação e a divergência é registrada em `docs/spec/erros.md` e no release notes
   (breaking). A suíte oficial continua valendo como oráculo de comportamento **válido**.

### Fase 3 — depois de uma release com a fase 2

8. Remove `--no-check`; `run` sempre checa. O modo gradual continua sendo o default do
   `run`; o `check` continua estrito.

### Regra de reversão

Se um falso positivo de narrowing bloquear um programa válido em uso real, a resposta é
abrir uma fatia de precisão (alias B ou efeito C-lite) — **nunca** afrouxar o check, e
nunca reintroduzir o `--no-check`.

## Consequências

### Positivas

- `loxia test` e CI passam a pegar erro de tipo antes do runtime, sem exigir anotação em
  todo código (modo gradual).
- Quando a fase 2 chega, `run` e `build` concordam mais: menos "roda interpretado, falha
  compilado". I1 ganha premissa verdadeira (ver [ADR-0141](0141-soundness-de-fluxo-do-checker.md)).
- O LSP e o CLI deixam de divergir sobre o que é erro.
- A fase 1 não quebra `run`, então dá para medir falso positivo e atrito antes de bloquear.

### Negativas / custos

- Mais um modo para documentar e testar (`--gradual`), com risco de confusão com o
  `--check` estrito.
- Na fase 2, 22 + 36 expectativas mudam de exit code; é breaking change e precisa de
  release notes e de uma decisão editorial sobre a suíte oficial.
- `run` fica ~4% mais lento e passa a recusar programas que hoje executam.
- Obriga a manter a taxa de falso positivo baixa; a pressão por B/C-lite aumenta (o que é
  bom, mas é trabalho novo).

### Neutras

- `--check` estrito não muda em nenhuma fase.
- `--emit` já exigia o checker; nada muda no backend.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Bloquear no `run` já (fase 2 imediata) | Bloqueia falso positivo de narrowing sem escape e quebra a suíte oficial antes de o contrato de fluxo existir |
| Bloquear só erro estrutural e avisar mismatch de tipo | Cria duas semânticas de "erro" para o mesmo programa; a fronteira entre estrutural e tipo é instável |
| Política por projeto (`loxia.toml`) e `run` opt-in | Não entrega "obrigatório"; a decisão fica diluída e o default continua permissivo |
| Enforcement em runtime (tags de tipo) | Quebra tipos apagados, custa performance e muda I2/I1 |
| Manter opt-in | Mantém a assimetria atual entre interpretado e compilado, que já produziu um crash |

## Como verificar

- `loxia test` falha em um `*_test.lx` com erro de tipo e passa em teste sem anotação
  (aviso), com e sem `--no-check`.
- `loxia check --gradual` aceita programa sem anotações e continua recusando erro real.
- Fase 2: os 22 casos golden e os 36 oficiais reclassificados; `make check` verde; corpus
  diferencial com I1 nos três canais.
- `tests/test_docs_consistency.py` e `docs/spec/erros.md` refletem os modos.
- **Revisitar:** taxa de falso positivo em uso real, custo de boot e reclamações de
  migração na fase 2.

## Referências

- #160, #112, [ADR-0141](0141-soundness-de-fluxo-do-checker.md)
- [`../spec/garantias.md`](../spec/garantias.md) (I4), [`../spec/erros.md`](../spec/erros.md)
- [ADR-0020](0020-assinaturas-explicitas.md) (anotações obrigatórias sob check),
  [ADR-0059](0059-i4-check-limpo-compila.md)
