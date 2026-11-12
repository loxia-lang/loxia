# IDEIAS — parking lot (só o que ainda está aberto)

Só ficam aqui **coisas que ainda precisam ser feitas ou decididas**. Decisões fechadas
viram ADR + [`docs/decisoes.md`](docs/decisoes.md); o que já foi implementado sai daqui.

> **Escopo:** nada aqui é 1.0; o freeze está no
> [ADR-0026](docs/adr/0026-freeze-1.0.md). Para o mapa 1.0 × depois, veja
> [`ESCOPO.md`](ESCOPO.md).

## Pendências com direção já decidida

- **Tuplas:** sintaxe escolhida (`(a,b)`, `(A,B)`, `t[0]`, `val (a,b) = t`), implementação
  pós-1.0/backend ([ADR-0030](docs/adr/0030-tuplas.md)).
- **Generics além do T3b:** classes/métodos genéricos, constraints/traits, type application
  explícita, função genérica como valor, recursão polimórfica e variance declarada.
- **Math:** `log`, `exp`, `sin`, `cos`, `tan`, `pow` e constantes (`math.pi`) dependem da
  libm; ficam fora do I3 até existir uma biblioteca determinística.
- **Módulos/stdlib:** `std.*`, `io`, `string`, `collections` e `time` explicitamente não
  determinístico.
- **Diagnósticos:** spans/caret/stack trace e JSON determinístico (ver I-4).
- **Variádicos:** `...args`/`*args` continua em avaliação (I-5).
- **Iteráveis:** `..=`, `Iterable` de usuário e utilitários (`contains`, `sum`,
  `enumerate`, `zip`) dependem de traits/tuplas (I-6).

## I-4 — Linguagem "agent-friendly": contratos + erros estruturados determinísticos

**Status:** `em avaliação`
**Decidir até:** contratos depois do backend/1.0 e antes de estabilizar a stdlib; formato
JSON junto com o redesign de diagnósticos (`TODO.md` §3.1).

### A pergunta

1. Design by Contract: `requires` / `ensures` / `invariant` na linguagem? Onde ficam?
2. Contratos são opcionais? Em que sentido (declarar, checar, custo)?
3. Erros em JSON estruturado para agentes, com resolução **determinística**, mantendo um
   stack trace humano tradicional.

### Parte A — Contratos (DbC)

#### Terminologia (importante)

O que foi descrito como "invariantes antes do bloco de código de uma função" é, na
literatura, uma **pré-condição**. Os três conceitos:

| Conceito | Onde | Verifica |
| --- | --- | --- |
| **Pré-condição** (`requires`) | antes do corpo | o que o chamador deve garantir |
| **Pós-condição** (`ensures`) | depois do corpo | o que a função garante, dado que a pré valeu |
| **Invariante de classe** (`invariant`) | na classe | vale na entrada e saída de todo método público |
| **Invariante de laço** | no `while`/`for` | vale antes/depois de cada iteração (mais difícil; P3) |

Usar "invariante" para "checagem no topo da função" confunde com invariante de classe e
de laço. Recomendo os três nomes distintos desde o início.

#### Sintaxe proposta (Eiffel/Dafny-like, entre assinatura e corpo)

```lox
fn dividir(a: Int, b: Int) -> Int
  requires b != 0
  requires a >= 0
  ensures result * b <= a
{
  a / b
}

class Conta {
  var saldo: Int
  invariant saldo >= 0

  fn sacar(valor: Int)
    requires valor > 0
    requires valor <= saldo
    ensures saldo == old(saldo) - valor
  {
    saldo = saldo - valor
  }
}
```

Regras:
- `requires`/`ensures`/`invariant` são **cláusulas opcionais** entre a assinatura e `{`.
- No `ensures`, `result` é o valor de retorno e `old(expr)` é o valor da expressão na
  entrada (snapshot **raso**; documentar que `old(lista)` não congela o conteúdo).
- `invariant` de classe é checado na entrada e na saída de métodos públicos (não em
  métodos privados, para não pagar duas vezes).
- Expressões de contrato são **puras**: sem I/O, sem atribuição, sem `throw`. O checker
  deve impor isso (ou restringir a um subconjunto: comparações, aritmética, `len`,
  chamadas a funções marcadas `pure`).
- Herança (cap. 13): pré-condições podem ser **enfraquecidas**, pós-condições
  **fortalecidas** (Liskov); invariantes são herdados e checados junto.

#### Opcional? Sim, em três eixos — mas com default esperto

| Eixo | Opções | Recomendação |
| --- | --- | --- |
| **Declarar** | com/sem cláusulas | opcional por função (zero contrato = zero custo) |
| **Checar** | `off` / `check` / `warn` | `check` no interpretador/dev; `off` no nativo release, ligável com `--contracts=check` |
| **Onde** | runtime / estático | runtime por padrão; o checker pode provar alguns casos triviais e evitar a checagem |

- `--contracts=off`: cláusulas são **parseadas e tipadas** (não podem ter erro de tipo),
  mas não executadas. Documentar que "off" é otimização, não permissão para código
  quebrado.
- `--contracts=warn`: só para migração — loga a violação e continua. Perigoso (segue com
  estado inválido); nunca default.
- Violação é **falha fatal** (como `assert`), não `throw` recuperável: contrato violado é
  bug, e `try/catch` em volta mascararia. No REPL, reporta e mantém a sessão viva.
- Custo: pós-condição com `old(...)` pode alocar snapshot; contrato com `sorted(xs)` é
  O(n log n) — documentar a complexidade e permitir `off`.

#### Contratos como testes (bônus valioso)

Pré e pós-condições são **oráculos de teste de graça**: um gerador (property-based testing,
futuro `hypothesis`) pode produzir entradas que satisfazem `requires` e verificar
`ensures`. Isso transforma contrato em teste sem escrever teste. É o argumento mais forte
a favor de DbC na linguagem, e combina com o fuzzing já previsto no `TODO.md` §7.

#### Impacto técnico

- **Parser**: três cláusulas novas, só entre assinatura e corpo; sem ambiguidade.
- **Resolver**: contratos enxergam parâmetros e (em `ensures`) `result`/`old`; `old` exige
  guardar snapshot na entrada.
- **Checker**: pureza, tipos, e `result` só em `ensures`.
- **Interpretador**: avaliar antes/depois; erro estruturado em vez de `LoxRuntimeError`
  genérico.
- **LLVM**: cada cláusula vira `icmp` + branch para o runtime de falha; `--contracts=off`
  remove tudo. Cuidado: **não** transformar contrato em `llvm.assume` sem checagem — se a
  pré-condição for violada, o comportamento é UB em vez de erro. Primeiro checar, depois
  (talvez) usar como hint.
- **Testes**: golden de contrato (violação com `kind`, `clause`, `bindings`), e teste de
  que `off` não altera o resultado.

### Parte B — Erros estruturados em JSON

#### Princípio

Um único **modelo de diagnóstico** interno; dois renderizadores: **humano** (caret +
cores + stack trace) e **JSON** (máquina). Nunca gerar a mensagem duas vezes.

#### Esquema proposto (v1)

```json
{
  "schema_version": "1.0",
  "command": "check",
  "success": false,
  "summary": { "errors": 1, "warnings": 0 },
  "diagnostics": [
    {
      "code": "E3001",
      "kind": "type_mismatch",
      "severity": "error",
      "phase": "typecheck",
      "message": "expected Float, found String",
      "span": {
        "file": "src/main.lox",
        "start": { "line": 3, "column": 9, "offset": 41 },
        "end":   { "line": 3, "column": 14, "offset": 46 }
      },
      "labels": [
        { "span": { "file": "src/main.lox", "start": { "line": 3, "column": 9 }, "end": { "line": 3, "column": 14 } },
          "message": "encontrado String" }
      ],
      "notes": ["o valor vem de `pessoa.nome` (linha 2)"],
      "help": "use `as Float` para converter explicitamente",
      "docs": "https://lox.dev/errors/E3001",
      "fixes": [
        {
          "applicability": "machine-applicable",
          "edits": [
            { "file": "src/main.lox",
              "span": { "start": { "offset": 41 }, "end": { "offset": 46 } },
              "replacement": "(pessoa.nome as Float)" }
          ]
        }
      ]
    }
  ]
}
```

Campos-chave:
- `code` **estável** (`E3xxx` tipo, `E1xxx` parser, `C1xxx` contrato, `R1xxx` runtime) e
  nunca reutilizado; `docs` aponta para o catálogo.
- `span` com **linha, coluna e offset em bytes** (offset é o que o editor/agente usa para
  editar sem ambiguidade; linha/coluna é o que o humano lê).
- `fixes[]` com `applicability` (`machine-applicable`, `maybe-incorrect`, `manual`) e
  `edits[]` com substituição por span — é o que permite o agente corrigir sem adivinhar.
- `kind` separa categorias sem quebrar `code`.

Violação de contrato usa o mesmo envelope:

```json
{
  "code": "C1002",
  "kind": "contract_violation",
  "phase": "runtime",
  "message": "precondition failed: b != 0",
  "function": "dividir",
  "clause": "requires",
  "span": { "file": "src/main.lox", "start": { "line": 2, "column": 12 }, "end": { "line": 2, "column": 18 } },
  "bindings": { "a": "10", "b": "0" },
  "trace": [ { "function": "main", "file": "src/main.lox", "line": 9 } ]
}
```

`bindings` mostra os valores das variáveis citadas na cláusula — o equivalente
estruturado do "mostre os argumentos no panic".

#### Determinismo (o que faz a resolução ser repetível)

1. **Ordenação fixa**: por `(file, start.offset, code)`; nunca pela ordem de um `dict`
   ou de um `set` (foi exatamente a classe de bug do `<object at 0x...>`).
2. **Sem dados voláteis**: nada de timestamps, PID, endereço de memória, caminho absoluto,
   locale ou ordem de `os.listdir`. Caminhos **relativos à raiz do projeto**.
3. **Formatação numérica canônica**: uma única `stringify` (ver
   [ADR-0006](docs/adr/0006-int-float-separados.md)) para
   mensagens e `bindings`; float sempre com representação round-trip.
4. **Dedup e cascata**: um erro raiz gera um diagnóstico primário; derivados viram
   `notes`/`related`, não erros novos. Limite `--max-errors`.
5. **Códigos e schema versionados**: `schema_version` no envelope; código nunca muda de
   significado. Mudança incompatível = nova major do schema.
6. **Saída separada**: em `run`, o stdout é do **programa**; diagnósticos vão para o
   **stderr** (JSON único ou NDJSON). Em `check`, o JSON vai para o stdout.
7. **Mesmo input → mesmo output**: teste de determinismo roda duas vezes e compara bytes
   (exceto nada — deve ser idêntico).

#### Protocolo de reparo determinístico (para agentes)

```
1. lox check --json            → diagnostics[]
2. selecionar fixes com applicability == "machine-applicable"
3. descartar edits sobrepostos (aplicar só os disjuntos; reportar os demais)
4. aplicar edições atomicamente (ou --fix --dry-run para só receber o diff)
5. reexecutar
6. progresso obrigatório: erros diminuíram OU conjunto de codes mudou
7. parar após N iterações (ex.: 10) ou quando success == true
8. se não houver fix: usar help/docs/code — nunca "adivinhar" edição
```

Comandos que tornam isso possível:
- `lox check --json` / `lox build --json` / `lox run --json` (diagnósticos);
- `lox check --fix --dry-run --json` (devolve `fixes[]` sem escrever);
- `lox explain E3001 --json` (entrada do catálogo, com exemplo e contraexemplo);
- `lox capabilities --json` (versão, schema, códigos suportados, exit codes).

#### Lado humano

- `--error-format=human|short|json|json-lines` (default `human` em TTY).
- O renderizador humano usa os mesmos `Diagnostic`s: caret, cores (`NO_COLOR`), notas e
  **stack trace** com frames (`at dividir (linha 2) ← main (linha 9)`).
- `--json` não pode degradar a experiência humana: o humano vê o mesmo erro bonito, só que
  em outro formato quando pedir.

### Parte C — Checklist "agent-friendly" (além de erros)

- [ ] `--json` em todos os comandos de inspeção (`check`, `ast`, `types`, `fmt --check`).
- [ ] **Nunca** prompt interativo; `--yes`/`--non-interactive` onde houver risco.
- [ ] Exit codes estáveis e documentados (65 sintaxe, 70 runtime, 66 arquivo; contrato
      pode virar 71 no futuro, mas `kind` já distingue).
- [ ] `--color=auto|always|never` e `NO_COLOR`; saída sem ANSI quando não-TTY.
- [ ] `--no-progress`; progresso só em stderr.
- [ ] Sem rede, sem telemetria, sem escrita fora do projeto.
- [ ] `--timeout` para execução (agente não pode travar em loop infinito).
- [ ] Catálogo de erros em JSON versionado no repo (`docs/erros/`), gerado dos códigos.
- [ ] Formatter idempotente e determinístico (`fmt` duas vezes = igual).
- [ ] Builds reproduzíveis (sem caminho absoluto no binário/objeto).
- [ ] `llms.txt`/`docs/agents.md`? (documentação pensada para agente, curta e factual)

### Argumentos a favor

1. **Contrato é documentação executável**: a intenção fica no código e é verificada, não
   em comentário que apodrece.
2. **Erro cedo e local**: a violação aponta a cláusula e os valores, não um stack trace
   genérico três camadas depois.
3. **Testes de graça**: pré/pós viram oráculo para property-based testing e fuzzing.
4. **Agente confiável**: JSON com `code`/`span`/`fixes` reduz alucinação; o protocolo de
   reparo é auditável e repetível.
5. **Humano não perde nada**: mesmo diagnóstico, renderizado bonito; JSON é opcional.
6. **Determinismo ajuda todo mundo**: cache de CI, diff de diagnósticos, testes de
   regressão de mensagem.
7. **Barato de começar**: contratos são só cláusulas opcionais; JSON é um renderizador a
   mais sobre o reporter que já existe.

### Argumentos contra

1. **Custo de execução**: pós-condições com `old`/`len`/ordenação podem dominar o tempo;
   `off` no release é obrigatório, mas aí o contrato deixa de valer em produção.
2. **Falsa segurança**: contrato não é verificação formal; cobre o que foi escrito.
   DbC não substitui type checker nem testes.
3. **Complexidade de linguagem**: mais três cláusulas, `old`, `result`, pureza, herança —
   é bastante superfície para uma linguagem em construção.
4. **JSON é contrato eterno**: schema e códigos viram API pública; errar cedo custa caro.
5. **Risco de "agent-only"**: features que só agente usa tendem a apodrecer; por isso o
   humano tem que consumir o mesmo modelo.
6. **Determinismo dá trabalho**: caminhos, floats, ordem de diagnósticos e dedup exigem
   disciplina em todo lugar (não só no reporter).
7. **Contratos em LLVM**: fácil de implementar, fácil de errar (`assume` = UB).

### Recomendação provisória

- **Contratos: sim, opcionais por declaração**, com `requires`/`ensures`/`invariant`,
  checagem **ligada por padrão no interpretador** e **desligável no nativo**
  (`--contracts=off|check|warn`). Violação = erro fatal estruturado (`C1xxx`), não
  exceção capturável.
- **Erros: um modelo, dois renderizadores**, JSON v1 com `code`/`span`/`fixes`, ordenação
  determinística e `--error-format`. Implementar **junto** com o redesign do §3.1 (não
  depois), senão o formato nasce torto.
- **Protocolo de reparo** documentado (`check --json` → aplicar `fixes` → reexecutar →
  progresso), com `--fix --dry-run` e `explain`.
- **Ordem prática**: JSON/determinismo primeiro (serve ao humano e ao agente, e é
  pré-requisito do LSP); contratos depois do cap. 10, quando há funções para anotar.

### Riscos e anti-metas

- Não tratar contrato como fronteira de segurança: com `off`, ele não existe.
- Não permitir efeito colateral em contrato (nem `print` de debug).
- Não emitir JSON com endereço/timestamp/ordem instável — quebra cache e confiança.
- Não criar um segundo modelo de erro para agente; o humano e o agente leem o mesmo.
- Não usar `llvm.assume` em contrato antes de ter checagem (UB silencioso).
- Não versionar schema sem `schema_version` e sem teste de compatibilidade.

### Gatilhos para revisitar

- ao implementar o redesign de diagnósticos (`TODO.md` §3.1);
- ao começar o codegen (contratos em LLVM);
- quando houver `lox check --json` (aí medir se o agente realmente resolve com `fixes`).

### Perguntas abertas

- [ ] `requires`/`ensures` ou `pre`/`post` (mais curto)? E `old`/`result`?
- [ ] Contrato no topo do corpo (`invariant x > 0`) em vez de cláusula? (não recomendo)
- [ ] `off` remove a checagem **e** a avaliação das expressões? (sim, senão não otimiza)
- [ ] Violação de contrato: exit 70 com `kind` ou exit 71 dedicado?
- [ ] `fixes` automáticos: só para sintaxe/typo, ou também semânticos?
- [ ] JSON em stderr (run) vs stdout (check) — confirmar contrato de CLI.
- [ ] `schema_version` por major/minor? Onde fica o catálogo de códigos?
- [ ] Contratos entram no AST público (`--ast --json`)? (sim, para tooling)
- [ ] Invariante de laço entra em qual fase? (P3)

### Referências

- Design by Contract (Eiffel): <https://www.eiffel.com/values/design-by-contract/>
- C++26 contracts: <https://en.cppreference.com/w/cpp/language/contracts>
- Rust contracts (RFC/discussão): <https://github.com/rust-lang/rfcs/pull/2850>
- Dafny (requires/ensures/invariant verificados): <https://dafny.org/>
- SPARK/Ada (contratos + análise estática): <https://www.adacore.com/sparkpro>
- Python `icontract`: <https://github.com/Parquery/icontract> · `deal`:
  <https://deal.readthedocs.io/>
- JSON Schema: <https://json-schema.org/>
- SARIF (formato de diagnóstico para CI): <https://sarifweb.azurewebsites.net/>
- Diagnósticos JSON do rustc:
  <https://rustc-dev-guide.rust-lang.org/diagnostics.html#json-output>
- LSP `Diagnostic`: <https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#diagnostic>
- Property-based testing: <https://hypothesis.readthedocs.io/>

---


## I-5 — Variádicos (`...args` / `*args`)

**Status:** `em avaliação` (não implementar agora)

Vale ter coleta de argumentos extras, no estilo Python?

```lox
// candidato 1: asteriscos
fn somar(*numeros) -> Int { /* numeros é List[Int] */ }
fn log(nivel: String, *partes) { /* ... */ }

// candidato 2: reticências (Lox2/Kotlin-ish, evita colidir com multiplicação)
fn somar(...numeros) -> Int { /* ... */ }
fn log(nivel: String, ...partes) { /* ... */ }
```

`**kwargs` só faz sentido se existir **argumento nomeado** na chamada
(`f(x = 1, y = 2)`), que é outra feature grande.

#### Como outras linguagens resolvem

| Linguagem | Extra posicionais | Extra nomeados |
| --- | --- | --- |
| Python | `*args` (tuple) | `**kwargs` (dict) |
| Kotlin | `vararg` | não (named args explícitos) |
| Go | `...T` | não |
| Java | `T...` | não |
| Rust | não tem varargs de usuário | não |
| JavaScript | `...args` (rest) | object/`arguments` |
| C | `...` (varargs não tipado) | — |

#### Viabilidade de `*args`

- **Runtime:** `LoxCallable.arity()` deixa de bastar. Seria preciso algo como
  `min_arity()` + `accepts(n)` ou uma `Signature`, e `call` recebendo a lista de extras.
  A mensagem de aridade vira "pelo menos N" (`Expected at least 2 arguments but got 1.`).
- **Parser/AST:** `Param` ganha um flag `variadic`; só um rest por função e sempre por
  último; a chamada **não** muda (os extras simplesmente são aceitos).
- **Semântica:** o binding do rest é `val` (a lista pode ser mutável, mas o nome não muda);
  defaults só antes do rest; `fn f(a = 1, ...xs)` é aceitável, `fn f(...xs, a)` não.
- **Tipos:** `...numeros: Int` vira `List[Int]`; a chamada aceita qualquer quantidade e o
  checker unifica todos os extras. No LLVM, empacotar os extras em array/lista alocada.
- **Custo:** médio. Útil para `print`/logging/FFI/decorators, mas muita coisa se resolve
  com uma lista explícita: `fn somar(ns: List[Int])` + `somar([1, 2, 3])`.
- **Veredito:** viável e provavelmente útil, mas falta um caso de uso concreto; `List` e o
  type checker já existem. Fica P2/P3.

#### Perguntas abertas

- [ ] `*args` (Python) ou `...args` (Lox2/Kotlin)? `...` evita ambiguidade com `*` e
      combina com spread.
- [ ] o rest pode ser `var` (reatribuir a lista)? (recomendo não)
- [ ] permitir rest em `init`/métodos? Se sim, a aridade da classe vira "pelo menos N".
- [ ] defaults depois do rest? (recomendo proibir)
- [ ] `print`/`log` nativos viram variádicos ou continuam aceitando uma lista?

## I-6 — Iteráveis: o que ainda falta no `for x in`

**Status:** `em avaliação` — `Range`, `String`, `List` e `Map` já funcionam
([ADR-0007](docs/adr/0007-ranges-e-iteracao.md)); resta:

- `..=` e ranges inclusivos.
- `Iterable` de usuário (depende de traits/`Option` para o fim do iterator).
- `contains`, `sum`, `enumerate`, `zip` (stdlib + tuplas).
- Iterar tuplas (depois do ADR-0030).

**No backend:** `for-in` ainda não existe (depende de `Range`, L6); o `for` C-style
desaçucara para blocos + `while` e compila desde o L2. Ver TODO §6.8.
