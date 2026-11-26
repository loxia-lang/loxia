# ADR-0148 — Ponto de entrada `main -> Result` e a borda de exit 70

- **Status:** accepted
- **Data:** 2026-11-26
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0135](0135-politica-de-erro.md) (§5, borda do processo),
  [ADR-0041](0041-enums-match.md) (`Result` embutido), [ADR-0042](0042-excecoes.md)
  (exceções), [ADR-0075](0075-diagnosticos-estruturados.md) (diagnósticos),
  [ADR-0014](0014-identidade-e-invariantes.md) (invariantes), [ADR-0031](0031-backend-nativo.md)
  (backend), [ADR-0066](0066-orcamento-e-gate-sintatico.md) (gate de sintaxe; não se aplica),
  issue [#142](https://github.com/loxia-lang/loxia/issues/142)
- **Implementação:** `loxia_core/semantics/checker.py` (`_detect_entry`),
  `loxia_core/execution/interpreter.py` (`interpret(entry=...)`/`_finish_entry`),
  `loxia_core/backend/lower.py` (`_call_entry`), `runtime/core.c`
  (`lox_unhandled_result`), `loxia/engine.py` (entry no run/check/build),
  `loxia_core/diagnostics` (`E3026`, `E3027`, `R1016`), `tests/cases/entry_main_*.lx`,
  `tests/test_entry_point.py`

## Contexto

O [ADR-0135](0135-politica-de-erro.md) §5 decidiu a **borda do processo**: um `Err` não
tratado no topo imprime `error: <msg>` em stderr e sai **70**. A regra ficou declarada como
**alvo** porque a linguagem executa statements e não tem `main`: um `Err` descartado é só um
valor e o processo sai 0. O [#142](https://github.com/loxia-lang/loxia/issues/142) pede o
ponto de entrada e a borda observável.

O desenho precisa conviver com o idioma que já existe. Programas de usuário frequentemente
declaram uma função `main` e a chamam no fim; é o caso do harness de TOML do próprio
repositório:

```lox
fn main() -> Nil { ... }
main()
```

Se **todo** `fn main` fosse chamado automaticamente, esse programa rodaria duas vezes. Por
isso o entry é **opt-in pela assinatura**: só um `main` que devolve `Result` abre o contrato.
Um `main` que devolve `Nil` (ou qualquer outro tipo) continua uma função comum, e o idioma
explícito segue válido.

## Decisão

1. **O entry é o `main` do arquivo de entrada.** É a função de topo chamada `main` do
   arquivo que está sendo executado/compilado (`loxia run`/`loxia build`), e só dele:
   módulos importados e o REPL nunca têm entry. Duas declarações de topo com esse nome são
   **`E3027`** (a regra vale para qualquer função de topo: a borda não pode ser ambígua e o
   checker/tree-walk não podem divergir na assinatura vigente). Um `main` único que não
   devolve `Result` não é entry; ele segue função comum.

2. **A assinatura é o opt-in.** O entry precisa ser:

   - sem parâmetros (nem defaults nem variádico);
   - sem parâmetros de tipo (não genérico);
   - com retorno **`Result[T, String]`** — `T` é livre (o payload de `Ok` é ignorado) e o
     erro é **sempre `String`**;
   - anotado explicitamente; um `main` sem anotação é uma função comum.

   Um `main` que devolve `Result` mas não cumpre a assinatura (parâmetros, genérico ou
   `E ≠ String`) é **erro de check** `E3026` (exit 65), não um no-op silencioso. Alias de
   tipo vale: a detecção usa o tipo já resolvido pelo checker.

3. **Ordem:** os statements de topo executam na ordem normal (declarações, efeitos,
   imports já carregados) e **depois** o `main` é chamado uma vez. Se um statement de topo
   falhar, o `main` não roda.

4. **Borda:** o valor devolvido pelo `main` decide o desfecho.

   - `Ok(...)` → **exit 0**, sem imprimir o payload.
   - `Err(msg)` → `error[R1016]: <msg>` em **stderr** e **exit 70**.
   - `msg` é a própria `String` devolvida (sem `repr`, sem aspas, sem stringificação
     implícita de outros tipos — I2).
   - A mensagem não tem posição de fonte: vem do valor, não de um token. O formato segue o
     precedente do runtime, `error[R1000]: Out of memory.`.

5. **Só o retorno do `main` conta.** Um `Err` descartado em outro lugar (statement de topo,
   variável não usada, retorno de outra função) continua sendo um valor comum. A borda não
   é uma exceção: `try` dentro do `main` não a captura, e uma exceção que escapa do `main`
   continua o caminho normal de `R1010`/exit 70 (com posição e stack trace).

6. **Sem sintaxe nova.** `main` não é palavra-chave; a regra é a assinatura, o nome e o
   arquivo. O gate do [ADR-0066](0066-orcamento-e-gate-sintatico.md) não se aplica.

7. **Fora de escopo:** `main(args)` (use `std.cli`/`args()`), `Ok(código)` como exit code
   (use `os.exit(código)`), exigir `main` em todo programa (scripts seguem statements-only),
   chamar `main` em módulos/REPL e o operador de propagação `expr?` (ADR-0135 §6).

## Regras observáveis

- O entry só existe no arquivo de entrada; importar um módulo com `main` não o executa.
- `fn main() -> Nil` é função comum; `main()` explícito continua funcionando.
- `--check` valida a assinatura antes de executar; `build` compila o entry.
- Um `main` que devolve `Result` e é chamado explicitamente roda **duas vezes** (uma pelo
  usuário, uma pela borda); a documentação diz para não chamá-lo.
- `--json`/`--json-lines` recebem a borda como diagnóstico `R1016` sem span.
- `loxia test` executa cada arquivo como programa (`run`), então um `main -> Result` num
  arquivo de teste também é entry; arquivos de teste não devem usar `main` como helper.

## Invariantes

- **I1:** interpretador e backend produzem os mesmos três canais. O caso diferencial
  `entry_main_err.lx` (L6) compara stdout, stderr e exit code; o backend chama
  `lox_unhandled_result`, que escreve exatamente `error[R1016]: <msg>\n`.
- **I2:** o tipo do erro é declarado (`String`); não há stringificação implícita de um `E`
  arbitrário.
- **I3:** a mensagem é texto do usuário; não há caminho, PID, timestamp nem endereço. O
  backend faz `fflush(stdout)` antes do stderr, como o restante do runtime.
- **I4:** o checker decide o entry e publica a assinatura; o backend consome o nó e o
  `FnSig`, sem inventar regra de tipo. `--check` limpo compila o caso.

## Consequências

### Positivas

- A promessa do ADR-0135 §5 passa a ser verificável, com código estável (`R1016`) e teste
  nos dois motores.
- O entry é explícito na assinatura; não muda programas sem `main -> Result` e preserva o
  idioma `fn main() -> Nil` + `main()`.
- `Ok`/`Err` continuam sendo o canal de falha esperada; defeito (`R1010`) e fluxo do
  usuário (`raise`) não se misturam.

### Negativas / custos

- Um programa que já tinha `fn main() -> Result[...]` e o chamava explicitamente passa a
  rodá-lo duas vezes. É pré-1.0 e o contrato é novo; a nota vai no changelog.
- Um `main` quase-Result (parâmetros, genérico, `E ≠ String`) passa a ser erro de check
  (exit 65), onde antes era uma função comum. A regra geral de `E3027` também passa a
  rejeitar **qualquer** função de topo duplicada; antes o tree-walk a executava e o
  backend morria em `E4002`, uma lacuna de I4 que este ADR fecha.
- Duas formas de programa convivem (statements-only e entry); a documentação precisa dizer
  quando usar cada uma.

### Neutras

- `String` como `E` é uma restrição deliberada: quem quer detalhe estruturado usa o próprio
  tipo como `Err` **fora** do entry e o traduz para `String` na borda.
- `error[R1016]` sem posição é o segundo caso do runtime sem span (o primeiro é o OOM).

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Todo `fn main` é o entry (estilo C) | Chamaria o harness de TOML duas vezes (ele já chama `main()`), e transformaria qualquer helper chamado `main` em código executado implicitamente. |
| Só statements de topo; sem entry | Mantém a mentira do ADR-0135 §5 e não dá como devolver falha ao shell. |
| `main` recebendo `List[String]` | Superfície nova e um segundo caminho de argumentos além de `args()`; fica para outro ADR se doer. |
| `Ok(código)` define o exit code | Redundante com `os.exit(código)` e mistura sucesso com status de processo. |
| Qualquer `E`, mensagem via `stringify` | Precisa formatar qualquer valor no stderr e cria divergência Python/C em instâncias/exceções; fere o "assinatura declara o canal". |
| Flag `--entry` no CLI | Não entrega o contrato por padrão e adiciona superfície a `run`/`check`/`build`. |

## Como verificar

- `tests/cases/entry_main_{ok,err,order,try,alias,nil}.lx` — golden e corpus `l6`
  (diferencial dos três canais).
- `tests/cases/errors/entry_main_{params,error_type,generic}.lx` — `E3026`, exit 65;
  `entry_main_duplicate.lx` e `duplicate_function.lx` — `E3027` (função de topo
  duplicada, incluindo `main`).
- `tests/test_entry_point.py` — módulo/REPL não têm entry e `--check` valida a assinatura.
- `tests/test_determinism.py` — a mensagem não introduz nada volátil.
- `--check` limpo compila (I4); `make check` verde.
