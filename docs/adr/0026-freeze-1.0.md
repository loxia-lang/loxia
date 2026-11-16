# ADR-0026 — Freeze da 1.0: erros, determinismo, UTF-8 e escopo

> **Atualizado por** [ADR-0078](0078-nome-loxia-extensao-lx.md): o nome e a extensão foram
> decididos (Loxia/`.lx`); “PyLox”/`.lox` são históricos. O corpo abaixo é o registro
> histórico da decisão da época.

- **Status:** accepted (item 4 substituído pelo [ADR-0085](0085-print-como-funcao.md))
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0014](0014-identidade-e-invariantes.md),
  [ADR-0016](0016-api-stdlib-hibrida.md), [ADR-0025](0025-is-e-narrowing.md),
  [`../../TODO.md`](../../TODO.md) §11, [`../spec/semantica.md`](../spec/semantica.md),
  [`../spec/garantias.md`](../spec/garantias.md)
- **Implementação:** [`loxia_core/execution/prelude.py`](../../loxia_core/execution/prelude.py),
  [`loxia_core/execution/interpreter.py`](../../loxia_core/execution/interpreter.py), [`loxia_core/semantics/checker.py`](../../loxia_core/semantics/checker.py),
  [`tests/test_official_suite.py`](../../tests/test_official_suite.py),
  [`tests/test_checker.py`](../../tests/test_checker.py),
  [`tests/test_interpreter.py`](../../tests/test_interpreter.py)

> **Atualização (ADR-0041/0042):** `enums`/`match`/`Result` e `try`/`except`/
> `finally`/`raise` entraram **depois** do freeze, no tree-walk; o escopo da 1.0
> continua o do freeze.
>
> **Atualização (ADR-0038, 2026-11-12):** traits foram decididos como nominais,
> `implements` e com métodos default, mas continuam **pós-MVP**; `D-17` fechado.
>
> **Atualização (ADR-0027, 2026-11-12):** T3b entra como exceção explícita ao freeze:
> funções genéricas com inferência, sem constraints, monomorfização no backend. Classes/
> métodos genéricos, type application explícita, traits e funções genéricas como valor
> continuam fora. Ver [ADR-0027](0027-generics-t3b.md).
>
> **Atualização (ADR-0028/0029/0030, 2026-11-12):** `--debug` adiciona checagem de overflow
> sem mudar o release; D-8 entra como exceção (`as`, parse e `math.*` determinístico);
> tuplas têm sintaxe decidida, mas ficam pós-1.0. Ver
> [ADR-0028](0028-overflow-debug.md), [ADR-0029](0029-conversoes-math.md) e
> [ADR-0030](0030-tuplas.md).

## Contexto

Depois de assinaturas, lambdas, soundness, mutação monomórfica e `is T`, a linguagem já
tinha superfície suficiente para o MVP — e superfície demais para congelar sem decidir.
O backend LLVM precisa de uma semântica estável; toda feature nova depois do freeze vira
dívida de codegen. O [`TODO.md` §11](../../TODO.md) listava doze decisões; cinco bloqueavam
a 1.0: erros, `clock`, UTF-8, `print` e escopo.

As escolhas abaixo foram feitas explicitamente antes do freeze, com as alternativas
registradas para não serem reabertas por acidente.

## Decisão

### 1. Erro de runtime é fatal

- Erro de compilação (léxico, sintaxe, resolver ou `--check`) → exit **65**.
- Erro de runtime → exit **70**; o programa para no ponto; o que já foi impresso permanece.
- A 1.0 **não tem** `try`/`throw`/`catch`, `Result[T, E]` nem recuperação de erro.
- Recuperação entra depois de generics + `match` (M5), provavelmente como `Result`.
- O backend LLVM pode chamar um `lox_panic(msg, line)`; sem unwinding, sem EH.

`ErrorReporter` continua sendo o mecanismo de diagnóstico; “fatal” é sobre execução, não
sobre qualidade da mensagem.

### 2. `clock` sai do prelúdio

`clock()` lia o relógio do sistema e, portanto, violava o I3 (“mesma entrada ⇒ mesmos
bytes”). A 1.0 fica com o prelúdio determinístico:

```lox
len   str   repr   range
```

- `clock` deixa de ser builtin reservado; pode ser usado como nome comum.
- A suíte oficial adapta `function/print.lox` trocando `clock` por `len` (ambos imprimem
  `<native fn>`); os golden cases de `clock` foram removidos.
- Tempo, se necessário, volta como módulo `time`/`clock` **explicitamente não
  determinístico**, fora do corpus I3 — nunca no prelúdio implícito.

### 3. UTF-8: strings sim, identificadores ASCII

- Fonte e literais de string são UTF-8.
- `len(s)` conta **code points**, não bytes; indexação de string não existe na 1.0.
- Identificadores continuam `[A-Za-z_][A-Za-z0-9_]*`; sem normalização Unicode (NFC/NFD)
  e sem `ação` como nome de variável na 1.0.
- O runtime nativo guarda bytes UTF-8 e decodifica code points em `len`; o tree-walk usa
  `str` do Python (code points).
- UTF-8 completo em identificadores fica para depois; exige decisão de normalização,
  colunas/caret e mangling no LLVM.

### 4. `print` continua statement — **substituído pelo ADR-0085**

- Histórico: a 1.0 congelou `print expressão` como instrução; o
  [ADR-0085](0085-print-como-funcao.md) a trocou por `print(valor)` (`Any -> Nil`),
  removeu o statement e migrou corpus/suíte oficial/exemplos.
- Não há `println`.
- A justificativa original era manter a gramática e a suíte sem mudança; com a migração
  mecânica e o orçamento reduzido, o custo deixou de pagar a exceção.
- Texto original: “Se a composição fizer falta, `println(x)` entra depois como função,
  sem quebrar o statement.”
- `str`/`repr` continuam sendo as formas de obter string.

### 5. Escopo congelado

Ficam **fora da 1.0** (revisão depois do backend/M5):

- módulos/imports/namespaces; um arquivo `.lox` é um programa;
- `if`/bloco como expressão; ternário e `??` cobrem o caso comum;
- `match`/enums, traits/structs, exaustividade;
- exceções, `try`/`throw` e `Result`;
- named args, operator overloading, trailing closure, single-param lambda sugar;
- `as` casts e conversões implícitas;
- stdlib ampla (`math`, `io`, `string`, parse): só o prelúdio mínimo acima, métodos de
  `List`/`Map` e `print`;
- `Any` **no backend L0–L2**: a linguagem mantém `Any` como escape gradual, mas o
  compilador do MVP o rejeita com erro claro; boxed depois;
- nome/extensão definitivos: “PyLox”/`.lox` são nomes de trabalho até o release público.

`--check` continua opt-in no CLI; `loxia build` (quando existir) sempre roda o checker antes
de gerar código.

### 6. Generics é uma trilha separada

T3b (por exemplo, `fn id[T] (x: T) -> T`) não é decidido por este ADR. Se entrar antes do
freeze, a estratégia precisa ser escolhida junto:

- **monomorfização** — código concreto por instanciação; melhor layout/performance, mais
  codegen;
- **erasure/boxing** — representação uniforme; codegen menor, mais dinâmico;
- **híbrido** — monomorfiza primitivos e boxa `Any`/não restritos.

Sem essa decisão, generics não entra no backend.

## Consequências

### Positivas

- A semântica da 1.0 cabe no LLVM MVP: sem EH, sem tempo ambiente, sem módulos e sem
  `Any` obrigatório no backend.
- I3 fica limpo: o prelúdio não tem fonte de não determinismo.
- O escopo é pequeno e testável; a suíte oficial continua como rede.
- `clock` deixa de ser uma exceção escondida no contrato de determinismo.

### Negativas / custos

- Não há recuperação de erro na 1.0; programas precisam validar antes.
- Sem `clock`, não dá para medir tempo sem uma futura API não determinística.
- Identificadores em português (com acento) não funcionam ainda.
- Sem módulos, bibliotecas só existem no prelúdio ou em um arquivo.
- `Any` não compila no MVP; programas com `Any` ficam fora do subset compilado.
- Remover `clock` é uma mudança breaking para quem já usava o builtin (pré-1.0).

## Alternativas consideradas

| Alternativa | Por que não agora |
| --- | --- |
| Manter `clock` e abrir exceção no I3 | Enfraquece a garantia central e complica o corpus diferencial |
| `clock` determinístico via flag | Mais um modo para manter; `clock` não é essencial |
| `Result` na 1.0 | Exige generics, `match` e biblioteca; MVP grande demais |
| `try`/`throw` | LLVM EH/setjmp, GC e stack traces; risco alto |
| `print` como função | Quebra gramática, suíte e exemplos sem ganho de MVP |
| UTF-8 completo em identificadores | Normalização, colunas e mangling; adiável |
| Módulos/imports agora | Resolução, linking e testes; depois do backend |
| `if`/bloco expressão agora | Muda parser/AST/codegen; ternário cobre |
| `match`/traits agora | Dependem de tipos/exaustividade; depois do MVP |
| `Any` boxeado no backend | Representação dinâmica em todo lugar; o gate é mais barato |

## Como verificar

- `tests/test_checker.py::test_clock_is_a_regular_name_after_removal`;
- `tests/test_interpreter.py::test_clock_is_not_a_builtin`;
- `tests/test_official_suite.py` (adaptação `clock` → `len`);
- golden cases de `clock` removidos;
- `tests/test_determinism.py` continua verde;
- `make check` verde.

Critério para revisar: quando `Result`/`match`/generics entrarem; quando o backend
precisar de `Any`; quando UTF-8 em identificadores virar prioridade; quando módulos
forem necessários para bibliotecas.
