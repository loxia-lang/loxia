# ADR-0002 — Tree-walk é a especificação executável (oráculo)

- **Status:** accepted
- **Data:** 2026-11-11
- **Relacionados:** [`../../TODO.md`](../../TODO.md) §5, §6; [`../tech/arquitetura.md`](../tech/arquitetura.md)

## Contexto

O projeto nasceu do jlox (tree-walk) e o objetivo de médio prazo é gerar código nativo com
LLVM. Havia três caminhos possíveis: continuar no tree-walk, migrar para uma VM de bytecode
(como o clox) ou transpilar para C antes do LLVM. Reescrever cedo arriscaria perder a
referência de comportamento justamente quando a linguagem vai mudar (sintaxe/tipos).

## Decisão

Manter o **interpretador tree-walk em Python** como:

1. implementação de referência da linguagem;
2. **oráculo** para testes diferenciais contra o backend LLVM no futuro (mesmo programa,
   mesmo stdout/exit code);
3. ambiente de experimentação de semântica, sem se preocupar com performance.

Não implementar VM de bytecode própria. O próximo backend é LLVM (via `llvmlite`), e a
performance fica para lá.

## Consequências

### Positivas

- Mudanças de linguagem são baratas e testáveis de imediato.
- Dois backends podem ser comparados automaticamente (diferencial), aumentando a confiança
  no codegen.
- Menos superfície: um interpretador simples em vez de compilador + VM + GC.

### Negativas / custos

- Performance limitada (ordens de magnitude abaixo de nativo); benchmarks medem regressão,
  não velocidade absoluta.
- O tree-walk não exercita problemas de codegen (ABI, GC, representação) — esses serão
  resolvidos no backend.
- Risco de o tree-walk acumular semântica difícil de mapear para LLVM (mitigado pelo
  resolver/type checker).

### Neutras

- O código do tree-walk não vira produto final; é infraestrutura de desenvolvimento.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| VM de bytecode (clox) | desvio grande, performance ainda insuficiente, não é o alvo |
| Transpilar para C | atalho que perde tipos e vira dívida; não ensina LLVM |
| Só LLVM, sem interpretador | sem oráculo; depuração de semântica no codegen é muito pior |

## Como verificar

- A suíte pytest cobre a linguagem no tree-walk.
- Quando o backend existir: um caso `.lox` roda nos dois e compara saída/exit code.
- Critério de reversão: se o codegen LLVM ficar pronto antes da linguagem estabilizar,
  reavaliar (não provável).
