---
name: lox-stdlib
description: Critério de pronto para módulo da stdlib e regras para capacidade de host/kernel (ambiente, handle, Result, poll e orçamento).
whenToUse: Ao propor ou implementar módulo em std/, primitiva nova em runtime/ ou capacidade de host (fs.open, net, proc).
---

# Stdlib e kernel

A decisão de escopo está no [ADR-0072](../../../docs/adr/0072-stdlib-batteries.md)
(stdlib = Lox puro sobre o kernel) e no [ADR-0071](../../../docs/adr/0071-primitivas-de-runtime.md)
(kernel fixo de primitivas, sem FFI genérica). Esta skill é o checklist operacional.

## Antes de codar

1. **Dor real** — programa concreto em `examples/` ou caso que use o módulo; não copie
   API de outra linguagem por simetria.
2. **Camada certa** — se dá para escrever em Lox puro sobre `std/*`/kernel existente, é
   stdlib; só vai para o kernel o que é SO ou representação que Lox não alcança.
3. **Determinismo** — classifique cada função como determinística ou `ambient`; `ambient`
   fica fora do corpus I1/I3 e o teste usa entrada fixa.
4. **Sintaxe** — módulo novo **não** adiciona sintaxe. Se precisar, é o gate do
   [ADR-0066](../../../docs/adr/0066-orcamento-e-gate-sintatico.md), não stdlib.

## Critério de pronto por módulo

- [ ] programa real em `examples/` ou caso que o use (não simetria com outra linguagem);
- [ ] golden em `tests/cases/std_<modulo>.lx` + `--check` limpo;
- [ ] determinismo declarado (função `ambient` ≠ corpus I1);
- [ ] doc pública em `std/*.lx` e página gerada em `docs/stdlib/`;
- [ ] zero sintaxe nova — se precisar, é ADR-0066, não stdlib;
- [ ] `make check` verde; `make bench` se tocar caminho quente.

## Capacidade de host (kernel)

Cada capacidade nova pede **ADR próprio** e passa pelo orçamento do kernel. Regras que
não mudam:

- `ambient: true` em tudo que toca SO/rede; fora do corpus I1/I3.
- Erro de host novo é `Result[T, OsError]`; `T?` fica só nas APIs antigas.
- Handle opaco com `close()` explícito e idempotente; usar handle fechado é
  `RuntimeError`; **sem finalizer** (Boehm não é determinístico).
- `poll` **antes** de thread; `spawn` sem shell; nenhum callback C→Lox que possa lançar;
  sem FFI genérica (`extern fn` continua fora, [ADR-0071](../../../docs/adr/0071-primitivas-de-runtime.md)).
- `net` v1 só com IP literal, loopback quando possível, sem DNS nem TLS; TLS é ADR
  separado.
- Kernel acima de ~30 primitivas é sinal de camada errada; tipo opaco de handle antes de
  crescer.

As capacidades em avaliação ficam em **Discussions › Ideas** (threads de `net`, `fs.open`,
registry); `fs.open` tem issue de decisão
([#16](https://github.com/loxia-lang/loxia/issues/16)) e o orçamento corrente está no
[`docs/roadmap.md`](../../../docs/roadmap.md).
