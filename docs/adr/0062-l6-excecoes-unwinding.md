# ADR-0062 — L6j: exceções, ABI de unwinding e cleanup

- **Status:** accepted
- **Data:** 2026-11-13
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0042](0042-excecoes.md), [ADR-0048](0048-abi-classes-l5.md),
  [ADR-0061](0061-l6-enums-match.md), [`../../TODO.md`](../../TODO.md) §0/§6

## Contexto

Exceções não são um tipo novo: são um **subsistema de controle**. O tree-walk usa
`raise`/`except`/`finally` e captura erros de runtime como `LoxRuntimeError`; o backend
hoje usa `lox_panic` (exit 70) e não tem unwind. Implementar isso como mais um `if` no
lowering cria limpeza frágil em `return`, chamadas aninhadas e `finally`.

O alvo é o MVP single-file, com arena sem destrutores. Não há C++ EH nem GC.

## Decisão proposta

### ABI de runtime

```c
typedef struct LoxException {
  void *type;          /* descritor da classe Exception/LoxRuntimeError */
  LoxValue payload;    /* instância ou mensagem */
  int32_t line;
} LoxException;

typedef struct LoxTryFrame {
  jmp_buf env;
  struct LoxTryFrame *previous;
  LoxException exception;
} LoxTryFrame;
```

- `lox_try_begin(frame)` (C, chama `setjmp`) devolve `0` no caminho normal e `1` quando
  um `longjmp` chega; `lox_try_end(frame)` desempilha.
- `lox_throw(type, payload, line)` preenche o frame ativo e faz `longjmp`.
- O frame vive na arena ou em `alloca` do chamador; a ABI expõe só `i8*`.
- A declaração LLVM de `lox_try_begin` precisa de `returns_twice` (ou equivalente) para
  o otimizador não assumir retorno único.

### Cleanup e `finally`

- Uma pilha de cleanup por frame de execução: `{fnptr, env}` para cada `finally` ativo.
- `return` dentro de `try` executa os cleanups ativos antes de retornar.
- `raise` executa os cleanups até o `try` alvo; `lox_unwind_to(frame)` centraliza isso.
- `finally` é emitido como função interna `void (i8* env)` com captura explícita (mesma
  ideia das closures), para poder ser chamado tanto no caminho normal quanto no unwind.
- `finally` que lança substitui a exceção em propagação (semântica do tree-walk); a
  política precisa de teste dedicado.

### Integração com erros de runtime

- `lox_panic` atual vira o **fallback não capturado**: se não há frame ativo, imprime
  exatamente como hoje e faz `exit 70`.
- Dentro de `try`, divisão por zero, índice inválido etc. viram `LoxException` de
  `LoxRuntimeError` capturável, preservando linha e mensagem.
- `raise;` reusa a exceção corrente; fora de `except` é erro de compilação do checker.

### Ordem de implementação

1. Spike de ABI: `try { ... } except ... { ... }` sem `finally`, com `raise` de classe.
2. `finally`/cleanup em `return` e em unwind.
3. Erros de runtime capturáveis (`LoxRuntimeError`).
4. Caso `exceptions.lox`; depois testes negativos de rethrow/cleanup.
5. Só então considerar spans/stack trace (ADR-0046 deixou fora).

## Alternativas

| Alternativa | Por que não (agora) |
| --- | --- |
| `invoke` + `landingpad`/DWARF EH | `llvmlite` não expõe a personalidade/runtime com facilidade; plataforma e otimização ficam frágeis. |
| Retorno de status/erro em toda função | Muda a ABI de todas as funções, quebra FFI e obriga checagem em cada chamada; não reproduz `finally`. |
| `setjmp` + cleanup só estático (sem pilha) | Não funciona quando o `raise` atravessa funções chamadas; o cleanup precisa ser dinâmico. |
| Não implementar exceções no backend | Mantém um `PENDING` permanente e impede L6 completo. |

## Riscos

- `setjmp`/`longjmp` com frames gerados por LLVM e `-O2`; validar com o mesmo teste em
  `-O0`/`-O2` e com `returns_twice`.
- Cleanup que lança, `finally` com `return` e `raise` dentro de `except` são os pontos
  semânticos mais delicados; cada um precisa de caso golden.
- A ABI de `try` é interna, mas `LoxException`/`LoxTryFrame` viram contrato de runtime;
  documentar em `docs/spec/erros.md` antes de codar.
