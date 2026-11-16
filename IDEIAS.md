# IDEIAS — parking lot (só o que ainda está aberto)

Só ficam aqui **coisas que ainda precisam ser feitas ou decididas**. Decisões fechadas
viram ADR + [`docs/decisoes.md`](docs/decisoes.md); o que já foi implementado sai daqui.

> **Escopo:** nada aqui é 1.0; o freeze está no
> [ADR-0026](docs/adr/0026-freeze-1.0.md). Para o mapa 1.0 × depois, veja
> [`ESCOPO.md`](ESCOPO.md).

## Pendências com direção já decidida

- **Generics além do T3b:** classes genéricas MVP feitas; **métodos genéricos, herança de
  `Box[Int]` e `is/as` reificado adiados** ([TODO.md](TODO.md) §10). Continuam em avaliação
  constraints (interfaces nominais decididas, pós-MVP:
  [ADR-0038](docs/adr/0038-traits-nominais.md), [ADR-0080](docs/adr/0080-interfaces-nominais-implementacao.md)),
  type application explícita, função
  genérica como valor, recursão polimórfica e variance declarada.
- **Math:** `log`, `exp`, `sin`, `cos`, `tan`, `pow` e constantes (`math.pi`) dependem da
  libm; ficam fora do I3 até existir uma biblioteca determinística.
- **Módulos/stdlib:** `std.*`, `io`, `string`, `collections` e `time` explicitamente não
  determinístico.
- **Diagnósticos:** spans/caret/stack trace e JSON determinístico (ver I-4).
- **Variádicos:** `...args`/`*args` continua em avaliação (I-5).
- **Iteráveis:** `..=`, `Iterable` de usuário e utilitários (`contains`, `sum`,
  `enumerate`, `zip`) dependem de interfaces (pós-MVP) e tuplas (prontas) (I-6).

## I-4 — Linguagem "agent-friendly": contratos + erros estruturados determinísticos

**Status:** contratos `em avaliação`; **erros estruturados decididos e implementados**
([ADR-0075](docs/adr/0075-diagnosticos-estruturados.md)).
**Decidir até:** contratos depois do backend/1.0 e antes de estabilizar a stdlib.

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

### Parte B — Erros estruturados (decidido e implementado)

O desenho de erros saiu deste documento: virou o
[ADR-0075](docs/adr/0075-diagnosticos-estruturados.md), com modelo único
(`Diagnostic`), códigos estáveis por família, spans (linha/coluna/offset),
`--error-format=human|short|json`, ordenação/dedup/cap determinísticos e caminho relativo.
Catálogo em [`docs/spec/erros.md`](docs/spec/erros.md). O que ainda falta — paridade do
runtime nativo, stack trace, `notes` de proveniência, `fixes[]`, `explain`, `json-lines`,
warnings e LSP — está no [`TODO.md`](TODO.md) §3.

### Parte C — Checklist "agent-friendly"

O checklist operacional (JSON nos comandos, exit codes, cor, sem rede/telemetria,
`--timeout`, catálogo, formatter idempotente, builds reproduzíveis) foi absorvido pelo
[ADR-0075](docs/adr/0075-diagnosticos-estruturados.md) e pelo [`TODO.md`](TODO.md) §3.
Itens ainda em aberto: `--json-lines`, `lox explain`, `lox capabilities`, `--timeout` e
`llms.txt`.

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
- **Erros: um modelo, dois renderizadores** — decidido e implementado no
  [ADR-0075](docs/adr/0075-diagnosticos-estruturados.md) (JSON v1 com `code`/`span`,
  ordenação determinística e `--error-format`).
- **Protocolo de reparo** documentado (`check --json` → aplicar `fixes` → reexecutar →
  progresso), com `--fix --dry-run` e `explain`.
- **Ordem prática**: JSON/determinismo fechados (ADR-0075); contratos depois do cap. 10,
  quando há funções para anotar.

### Riscos e anti-metas

- Não tratar contrato como fronteira de segurança: com `off`, ele não existe.
- Não permitir efeito colateral em contrato (nem `print` de debug).
- Não emitir JSON com endereço/timestamp/ordem instável — quebra cache e confiança.
- Não criar um segundo modelo de erro para agente; o humano e o agente leem o mesmo.
- Não usar `llvm.assume` em contrato antes de ter checagem (UB silencioso).
- Não versionar schema sem `schema_version` e sem teste de compatibilidade.

### Gatilhos para revisitar

- ao revisitar a paridade do runtime nativo ou `fixes[]` (`TODO.md` §3);
- ao começar o codegen (contratos em LLVM);
- quando houver `lox check --json` (aí medir se o agente realmente resolve com `fixes`).

### Perguntas abertas

- [ ] `requires`/`ensures` ou `pre`/`post` (mais curto)? E `old`/`result`?
- [ ] Contrato no topo do corpo (`invariant x > 0`) em vez de cláusula? (não recomendo)
- [ ] `off` remove a checagem **e** a avaliação das expressões? (sim, senão não otimiza)
- [ ] Violação de contrato: exit 70 com `kind` ou exit 71 dedicado?
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

**Status:** implementado para `Range`, `String`, `List`, `Map`, tupla e iterador de
usuário (`iter()` + `next() -> T?`, [ADR-0082](docs/adr/0082-iterador-de-usuario.md)).
Resta:

- `..=` e ranges inclusivos.
- `enumerate` e outras funções de iteração na stdlib.
- `Option`/enum como sentinela para permitir `nil` como elemento (hoje `nil` encerra).

**No backend:** `for-in` cobre as fontes embutidas e iteradores de usuário; o `for`
C-style continua desaçucarando para blocos + `while`. Ver TODO §6.8.

## I-7 — Paralelismo (multithread) — em avaliação

**Status:** `a pensar` — sem data; depende de async ([ADR-0037](docs/adr/0037-async-direcao.md)),
de I/O e do M7.
**Decidir até:** depois que async e a stdlib de I/O existirem, e antes de prometer
performance multinúcleo.

> **Nota (2026-11-16):** concorrência de **I/O** (spawn, servidor) não exige thread:
> `poll` sobre handles resolve sem heap compartilhado e sem `async` (ver I-11). Thread
> continua sendo só para CPU, e a primeira forma a tentar segue data-parallel
> determinístico.

### A pergunta

Async (ADR-0037) é **concorrência single-thread**: uma tarefa por vez, determinística.
Paralelismo é usar N núcleos. Vale a pena? Em que forma? O que dá para prometer sem quebrar
I1/I3?

### Restrições

- **I1**: mesmo stdout/stderr/exit code no interpretado e no compilado.
- **I3**: mesma entrada ⇒ mesmos bytes; a ordem de execução não pode depender do SO.
- Boehm é thread-safe, mas GC + heaps compartilhados + threads exigem um modelo de memória
  escrito (atomics, o que é corrida, o que é UB).
- O runtime C do backend é single-thread hoje; pool de threads é runtime novo.
- A 1.0 não tem `try`; falha em worker precisa de regra (fatal global? `Result` por
  tarefa?) e isso depende de `Result`/`try`.

### Opções

| Opção | Como | Determinismo | Custo |
| --- | --- | --- | --- |
| Threads + heap compartilhado (Go/Java) | `spawn` + locks/atomics/channels | não, salvo disciplina | modelo de memória, GC, runtime, data races |
| Workers/isolates (JS Workers, Erlang) | heaps separados + mensagens | se a ordem for por join/ordem de mensagens | serialização, duplicar heap/GC |
| Data-parallel determinístico | `parallel map`/`Task.all` sobre funções puras, resultados ordenados | sim, por construção | provar pureza/efeitos, pool, merge ordenado |

### O que eu não faria

- Expor `thread`/`lock` na linguagem: vira C com sintaxe pior e mata o I3.
- Prometer "async usa todos os núcleos": não usa ([ADR-0037](docs/adr/0037-async-direcao.md)).
- Copiar o scheduler do Go: é um projeto de runtime inteiro.

### Perguntas abertas

- [ ] Qual caso de uso justifica? Sem `io`, sem perfil de CPU e sem cliente, é otimização
      sem demanda.
- [ ] Data-parallel só sobre funções puras? Como o checker sabe? (efeitos; interfaces pós-MVP)
- [ ] Workers com heap separado: como serializar `List`/`Map`/classes sem violar o I2?
- [ ] `Task.all` vira o ponto de paralelismo implícito? (recomendo não: explícito, tipo
      `parallel map`)
- [ ] Falha em worker: fatal global ou `Result` por tarefa? (depende de `try`/`Result`)

### Critério para decidir

Só depois que (a) async existir, (b) houver I/O, (c) houver caso de uso concreto e um
benchmark mostrando ganho. A primeira forma a tentar é **data-parallel determinístico**;
threads compartilhadas só com modelo de memória escrito e um ADR próprio.

## I-8 — Ideias soltas (algum momento)

Coisas sem dor demonstrada e **sem direção comprometida**. Não são backlog: não têm data,
não bloqueiam nada e só viram ADR se aparecer um caso real. Diferente de I-4..I-7, aqui não
há uma pergunta em avaliação — há uma ideia guardada.

### Operator overloading — estacionado

**Status:** `a pensar`, sem ADR e sem previsão. Saiu do `TODO.md` §8 porque não é uma
pendência de implementação; se um dia voltar, volta como proposta com dor demonstrada.

**O que seria:** `a + b` como açúcar para um método do tipo do operando esquerdo (por
exemplo `a.add(b)`), resolvido pelo checker.

**Por que não agora:**

- não há `Vec`/`Matrix`/`Money` na stdlib nem caso real que fique ilegível sem operador;
- `add()`/`compare()` explícitos já resolvem, sem dispatch implícito;
- interfaces atuais não têm `Self` nem parâmetros de tipo; uma interface `Add` precisaria
  de `Self` ou de interfaces genéricas antes;
- `==`/`!=` são estruturais e usados por `Map`/enums; sobrecarregar igualdade quebraria a
  consistência com hash — o mais seguro seria excluir;
- o backend hoje baixa `+` para instrução LLVM; overloading vira chamada de método/vtable,
  com custo de checker, ABI e testes diferenciais;
- o [ADR-0014](docs/adr/0014-identidade-e-invariantes.md) recusa feature que só compra
  superfície antes de dor real.

**Se algum dia voltar, escopo mínimo:**

- somente interfaces + constraints (`T: Add`);
- `Self` na interface; sem ele, o retorno perde o tipo concreto;
- só `+ - * /` e unário `-`; sem `==`, `[]`, `()` ou bitwise;
- dispatch estático/monomorfizado; sem operador em valor de tipo interface;
- método explícito como alternativa sempre disponível.

**Alternativa atual:** métodos `add`, `sub`, `scale`, `compare` e funções de ordenação com
`T: Ord`; nada disso exige mudança na linguagem.

**Critério para reabrir:** um programa real de tamanho não trivial em que a ausência do
operador seja a principal fonte de ilegibilidade — e um ADR que pague `Self`/interfaces
genéricas separadamente do açúcar.

### Trailing closure — estacionado

**Status:** `a pensar`, sem data. Saiu do `TODO.md` §8.

**O que seria:** permitir a lambda final fora dos parênteses:

```lox
lists.map(xs) { fn(x) => x * 2 }
```

**Utilidade:** reduz o ruído de `fn(...)` nas APIs de callback da stdlib (`lists.map`,
`filter`, `fold`, `results.map` etc.). Não adiciona capacidade: funções já são valores.

**Por que não agora:**

- o ganho é cosmético; a forma explícita é legível e tipada;
- `{` já é bloco, literal de mapa, corpo de `match` e agora disputaria o papel de closure
  depois de uma chamada;
- `;` opcional e regra de newline (ADR-0011/0067) tornam a decisão local do parser
  delicada: `foo()` seguido de bloco na linha seguinte é ambíguo;
- não há DSL nem biblioteca que dependa disso para ser usável.

**Critério para reabrir:** um caso real em que a ausência da trailing closure seja a
principal fonte de ilegibilidade, com um desenho de parser que não reintroduza ambiguidade
com bloco/mapa e preserve uma única forma canônica.

### `match` estrutural em uniões — estacionado

**Status:** `a pensar`, sem data. Saiu do `TODO.md` §8.

**O que seria:** padrões por tipo/estrutura, não só variantes de enum:

```lox
match x {
  Int => ...
  String => ...
}
```

e, na versão completa, destructuring de campos:

```lox
match p {
  Point(x, y) => ...
  Circle(r) => ...
}
```

**Utilidade:** substituir cadeias de `if (x is Int) ... elif (x is String) ...` e,
na versão completa, destructuring com checagem de exaustividade.

**Por que não agora:**

- `is` + narrowing já resolve uniões de forma explícita (ADR-0025/0086);
- o `match` atual é exaustivo, mas só para **enums fechados** (ADR-0041);
- type-pattern match é viável e reusa os tags de `is`, mas ainda exige gramática de
  padrão e regra de exaustividade para uniões;
- match estrutural de campos exige metadados/reflexão em runtime, regras para classes
  abertas, herança, campos privados, `List`/`Map`/tuplas e custo O(n) em padrões de
  coleção;
- o [ADR-0066](docs/adr/0066-orcamento-e-gate-sintatico.md) recusa match estrutural
  sobre uniões justamente porque o erasure não fornece testemunhas de tipo.

**Se um dia voltar, escopo mínimo:** só type-pattern match em uniões fechadas, sem
destructuring de campos e sem padrões profundos de coleção.

**Critério para reabrir:** muitas uniões reais com cadeias longas de `is` e uma proposta
que separe claramente “type match” de “structural match”.

### Extension methods — estacionado

**Status:** `a pensar`, sem data. Saiu do `TODO.md` §8.

**O que seria:** métodos declarados fora da classe, resolvidos pelo tipo do receptor:

```lox
val nomes = pessoas.map(fn(p) => p.nome)   # em vez de lists.map(pessoas, ...)
```

**Utilidade:** ergonomia de receptor para tipos existentes, inclusive primitivos e
`List`/`Map`, sem tocar na declaração original.

**Por que não agora:**

- funções livres (`lists.map`, `strings.trim`, `maps.getOr`) já dão a capacidade;
- a stdlib tem identidade híbrida deliberada (ADR-0016): builtins globais, métodos
  específicos do tipo e funções de composição;
- exige resolução por tipo, regras de visibilidade/importação, colisão com métodos reais,
  prioridade entre extensões e backend com alvo estático/monomorfizado;
- cria duas APIs para a mesma operação (`lists.map(xs, f)` e `xs.map(f)`) e fragmenta o
  estilo.

**Alternativa:** adicionar um método embutido pontual (`xs.map`) se um caso específico
doer, ou manter a função livre.

**Critério para reabrir:** um caso concreto que não possa ser resolvido por função livre
nem por método embutido, e um desenho de resolução sem ambiguidade.

### Classes como valores / metaclasses — estacionado

**Status:** `a pensar`, sem data. Saiu do `TODO.md` §8.

**O que já existe:** a classe pode ser passada como **valor de construtor**
(`criar(Animal, "Rex")`), inclusive em um `Map` de fábricas. Isso cobre a maior parte de
“classe como valor” para injeção/fábricas, sem reflexão (ADR-0021).

**O que seria a versão completa:** um `Class[T]`/metaclasse com métodos estáticos, campos
de classe, `Animal.nome`, introspecção de campos/superclasse e instanciação dinâmica.
Metaclasses seriam a “classe da classe”, com hooks de criação.

**Por que não agora:**

- o caso útil (construtor/fábrica) já funciona;
- `Class[T]` exige tipo, representação no backend, identidade/igualdade, impressão,
  interação com herança e com genéricos apagados;
- metaclasses são um sistema de metaobjetos, não um ajuste: hooks de criação, resolução
  de métodos e semântica de classe;
- **decorators não são metaclasses.** `@deco` é açúcar para `f = deco(f)` (ou
  `C = deco(C)`), e Loxia já consegue o decorator manual para funções:

  ```lox
  fn logged(f: fn(Int) -> Int) -> fn(Int) -> Int {
    return fn(x) => {
      print("chamando")
      return f(x)
    }
  }
  val f2 = logged(f)
  ```

  `@` exigiria sintaxe, ordem de aplicação, múltiplos decorators e diagnóstico — e
  esconderia fluxo, contra o I2.

**Se um dia voltar:** no máximo um `Class[T]` mínimo para introspecção, sem metaclasses e
sem `@decorators`; decorators de função continuam sendo funções de ordem superior.

**Critério para reabrir:** dor real de fábrica/introspecção que construtores como valor não
resolvam, com ADR separado para `Class[T]`; metaclasses/decorators só com justificativa
muito forte.

---

## I-9 — Módulos fora do projeto, stdlib instalada e pacotes externos

**Status:** `em avaliação`
**Decidir até:** antes do primeiro release público — é o pré-requisito técnico do
[`TODO.md`](TODO.md) §14.4. Hoje o repo funciona e o pacote não.

### A pergunta

Com a regra atual do [ADR-0073](docs/adr/0073-imports-modulos.md) — raiz = diretório do
arquivo de entrada, `..` e caminho absoluto são erro, `std.` é raiz reservada — como um
programa consome:

1. a **stdlib instalada** (o wheel não tem `std/`);
2. um **monorepo** (`../shared/util.lx`, fora da pasta do projeto);
3. um **pacote de terceiro** instalado ou vendorizado?

Sem quebrar I3 (determinismo) nem a segurança de "import nunca escapa da raiz".

### Fatos do código (2026-11-15)

- [`loxia_core/loader/loader.py`](loxia_core/loader/loader.py): módulo = arquivo, pasta = namespace,
  `_` privado; `STD_ROOT = Path(__file__).resolve().parents[2] / "std"`; o loader **inlina**
  os módulos em compile-time (não há módulo em runtime).
- A resolução é a mesma para os dois motores (o backend recebe a AST achatada) — bom: uma
  regra só, e o I1 não depende de runtime de módulos.
- `pyproject.toml`: sem `[build-system]`, sem `[project.scripts]`, `std/` fora do pacote.
- A suíte cobre `import std.*` nos casos `t1`/`t2` do diferencial, mas **sempre a partir do
  repo**: nenhum teste roda o layout instalado.

### Restrições que a decisão não pode violar

- **I3:** ordem de resolução fixa, sem variável de ambiente, sem caminho absoluto no
  diagnóstico, sem `set`/`dict` decidindo precedência.
- **I1:** a resolução é a mesma nos dois motores; nada de "no nativo resolve outro arquivo".
- **ADR-0073:** sem `__init__.py`, sem `index.lox`, sem reexportação, sem glob em `import`.
- **ADR-0066 (gate sintático):** versão/hash não entram no `import` (`import acme@1.2` é
  sintaxe nova); a restrição de versão mora no manifest.
- **Sem rede no caminho de build** por padrão: `loxia run` não pode depender de internet.

### Opções

| Opção | Como funciona | Prós | Contras |
| --- | --- | --- | --- |
| **A. Vendor-only** | dependências copiadas para dentro do projeto; raiz única | zero resolução; determinístico; nada novo no loader | update manual; duplicação; monorepo impossível; não é "pacote" |
| **B. Raízes declaradas** | `loxia.toml` com `paths` + ordem fixa; `import` continua só com identificadores | monorepo e dependência vendorizada funcionam; determinístico; sem rede; aditivo (sem manifest = hoje) | um arquivo de config; erro de "raiz não encontrada" precisa ser bom; precedência vira API |
| **C. Manifest + lockfile + registry** | `loxia add`, lock com hash, fetch | ecossistema de verdade | rede, confiança, semver, supply chain; é outro produto; só faz sentido depois de B |
| **D. Diretório global de pacotes** | `~/.loxia/pkgs/<nome>/<versão>`, resolvido por manifest | instala uma vez, usa em vários projetos | estado fora do projeto quebra reprodutibilidade a menos que o lock fixe; difícil de depurar |
| **E. `std` como pacote comum** | publicar `std` no mesmo mecanismo | uniformidade | versão da std divergir do compilador quebra semântica/I1; rejeitar |

### Sub-decisões (independentes da opção)

1. **Identidade do pacote:** nome declarado (`[package] name`) ou nome do diretório? Nome
   declarado permite `vendor/acme/` sem exigir `acme/` na raiz; o diretório passa a ser só
   localização.
2. **Layout interno:** `loxia_core/` do pacote vira a raiz de namespace (`acme/loxia_core/foo.lx`)?
   Recomendo raiz = diretório do pacote, como hoje, e `loxia_core/` só convenção de repositório.
3. **Precedência e ambiguidade:** ordem fixa `projeto → declaradas → std`. Se dois roots
   têm `acme/foo.lx`, **erro** (nunca primeira-vence em silêncio) — a mensagem lista as
   raízes relativas.
4. **`..`:** proibido no statement `import` (mantém ADR-0073); permitido **apenas** como
   raiz declarada no manifest. A diferença é auditabilidade: raiz declarada é explícita e
   versionada; `../` no meio do código é invisível.
5. **Variável de ambiente:** rejeitar (`LOXIA_PATH` quebraria I3). Para desenvolvimento,
   flag `--module-path DIR` (repetível) — flag entra no contrato "mesmas flags ⇒ mesmos
   bytes".
6. **Versão da stdlib:** acompanha o compilador na v1 (sem semver independente). Pacote de
   terceiro só ganha versão quando C existir.
7. **Cache:** nenhum na v1; depois, cache por hash de conteúdo (nunca por mtime).
8. **Symlinks:** seguir só dentro da raiz; symlink que escapa = erro na resolução.

### Recomendação provisória

**B agora, com `std` embutida e reservada** (opção A continua funcionando de graça, porque
sem manifest a raiz é o projeto). **C depois**, e só com lockfile + hash de conteúdo — sem
isso, rede quebra a promessa de reprodutibilidade que o projeto inteiro vende. **E
rejeitada**: a stdlib é parte da linguagem, não uma dependência.

Desenho mínimo:

```toml
# loxia.toml (na raiz do projeto)
[package]
name = "meu-app"

[modules]
paths = ["vendor", "../shared"]   # relativo ao manifest; ordem = precedência
```

```lox
import acme.json          # resolve em <root>/acme/json.lx do pacote "acme"
import std.json           # raiz reservada, embutida no wheel
```

### Impacto técnico

- **Loader:** parse do manifest (`tomllib`, stdlib), lista de raízes, erro de ambiguidade,
  diagnóstico com caminho relativo; `STD_ROOT` via `importlib.resources`.
- **CLI:** `--module-path`; mensagens de "módulo não encontrado" listando as raízes
  procuradas (sem absoluto).
- **Checker/backend:** nada — a resolução é compile-time e a AST chega achatada.
- **Packaging:** `loxia/std/` como package data; teste de instalação real (TODO §14.4).
- **Docs:** `docs/spec/` ganha a seção de módulos; ADR novo quando a opção fechar.

### Perguntas abertas

- [ ] `loxia.toml` ou `loxia.json`? (toml já está no ecossistema e `tomllib` é stdlib.)
- [ ] `[package] name` é obrigatório ou o diretório basta quando não há manifest?
- [ ] Pacote pode ter dependências próprias (manifest de pacote) ou só o projeto raiz
      declara? (recomendo: só o projeto raiz na v1.)
- [ ] Raiz declarada que não existe: erro na hora ou só quando um `import` a usa?
- [ ] `std` pode ser reimplementado pelo usuário? (não: nome reservado.)
- [ ] Como o corpus `t1`/`t2` roda instalado, e não só no repo?

### Gatilhos para revisitar

- primeiro release público (o wheel precisa funcionar fora do repo);
- primeiro usuário pedindo para consumir um pacote;
- self-hosting do front-end: precisará organizar lexer/parser/checker em módulos e vai
  exercitar a resolução de verdade;
- se aparecer monorepo real (dor concreta de `../shared`).

---

## I-10 — CLI único e gerenciador de pacotes (o "uv" da Loxia)

**Status:** `em avaliação` — a fase 0 (CLI único) já está decidida no
[ADR-0088](docs/adr/0088-distribuicao-e-raizes-de-modulo.md); as fases 1–4 são roadmap.
**Decidir até:** fase 1 antes do primeiro `loxia add`; fase 3 só com demanda real.

### A pergunta

Dá para ter **um** comando (`loxia`) que roda, compila, testa **e** resolve/baixa os
pacotes — no espírito do `uv`, sem um segundo nome (`loxpkg`)?

### Resposta curta

Dá, e é **muito** mais simples que o `uv` — porque a Loxia não tem os problemas que o `uv`
foi criado para resolver.

| O `uv` resolve (Python) | A Loxia tem? |
| --- | --- |
| virtualenvs isolados por projeto | ❌ não precisa: a compilação é por conjunto de fontes, sem ambiente global |
| wheels/ABI tag/manylinux, `pip` legado | ❌ tudo é fonte `.lx`; não há binário de dependência |
| PEP 517, `setup.py`, build isolation, sdist | ❌ o "build" é compilar; não há script de build executado na instalação |
| grupos dev/optional, editable install | ⚠️ dev-deps talvez; editable não faz sentido (fonte é fonte) |
| versão do Python, matriz de interpretadores | ❌ uma implementação (por enquanto) |

O que **sobra** — e é o gerenciador de pacotes de verdade: resolver o grafo de dependências,
travar versões com hash, baixar/cachear, e um índice de onde baixar. Isso é umas 2–3 mil
linhas, não 300 mil.

### Fases

| Fase | Entrega | Esforço | Depende de |
| --- | --- | --- | --- |
| **0. CLI único** | `loxia run/check/build/fmt/test/repl/version`; flags antigas preservadas | S | ADR-0088 §1 |
| **1. Manifest + lock** | `[dependencies]` no `loxia.toml`, `loxia.lock` (versão exata + `sha256`), `loxia lock`, `loxia fetch --offline`, cache local | M | 0 + ADR-0088 §3 |
| **2. Path e git** | `dep = { path = "../lib" }`, `dep = { git = "...", rev = "..." }` | M | 1 |
| **3. Índice estático** | índice tipo *sparse index* (JSON por pacote) em GitHub Pages/S3, tarball por versão, `loxia add nome@1.2` | L | 2 |
| **4. Resolver em Loxia** | reescrever o resolver na própria linguagem (dogfooding, como Cargo em Rust) | XL | self-hosting + `sha256` como primitiva |

A fase 2 resolve o caso de monorepo sem registry nenhum — provavelmente é onde o projeto
vai viver por muito tempo. A fase 3 só se paga com **terceiros publicando**, e isso é
problema de comunidade, não de código.

### Requisitos não negociáveis

1. **Lock com hash.** `loxia.lock` fixa versão + `sha256` do conteúdo; `--frozen` usa só o
   lock e falha se o manifest divergir.
2. **Resolução determinística.** Mesma entrada (manifest + lock) ⇒ mesmas versões, mesma
   ordem de download, mesma árvore. Nada de "depende do que o resolver achou primeiro".
3. **`loxia run` nunca acessa a rede.** Fetch é comando explícito (`loxia fetch`), cache
   local, e o build roda offline.
4. **Sem env var.** Caminho de cache e de pacotes vêm de flag/config; resultado não pode
   depender do ambiente (I3).
5. **Erro de conflito explicável.** Quando não há solução, a mensagem mostra a árvore de
   dependências que levou ao conflito, não "resolution failed".

### O que **não** fazer

- **Registry antes de haver demanda.** Índice vazio não é ecossistema; e moderar nomes
  (squatting) é trabalho humano contínuo.
- **Semver completo com backtracking** antes de existir pacote real com conflito. V1:
  versões exatas no lock; ranges depois, com teste de resolução.
- **Scripts de build em pacote.** É a maior parte do risco de supply chain do npm/PyPI e
  não é necessário: pacote Loxia é fonte + manifest.
- **Pacote binário.** Tudo compila do fonte; isso elimina ABI/manylinux/wheels de uma vez.
- **Mirrors, workspaces completos e namespaces de pacote** antes da fase 3.

### Impacto técnico

- **Loader/CLI:** o manifest ganha `[dependencies]`; a árvore de dependências vira um
  conjunto de raízes resolvidas (mesmo mecanismo do ADR-0088 §3).
- **Reprodutibilidade:** o lock é o que permite dizer "este build é o mesmo" — e a Loxia já
  vende determinismo; um gerenciador de pacotes sem lock contradiria o produto.
- **Self-hosting:** o resolver da fase 4 precisa de `sha256` e (talvez) descompressão como
  primitivas do kernel — hoje não há criptografia na linguagem. Isso é uma decisão de
  runtime, não de sintaxe.
- **Segurança:** hash obrigatório, sem execução de código no fetch/build; o pior caso vira
  "código-fonte hostil compila", não "instalação executa script".

### Perguntas abertas

- [ ] V1 usa versões exatas + lock, ou já aceita `^1.2` (ranges)?
- [ ] `loxia add` edita o manifest ou só calcula e imprime o diff? (recomendo editar, com
      `--dry-run`.)
- [ ] O lock é commitado? (sim, sempre — é o contrato de reprodutibilidade.)
- [ ] Dependência declarada por pacote (transitiva) ou só na raiz? (v1: só raiz, como no
      ADR-0088.)
- [ ] Vendor: pasta comum ou cidadão de primeira classe (manifest aponta para ela)?
- [ ] Onde fica o cache (`~/.cache/loxia` ou por projeto)? Como isolar em CI?

### Gatilhos para revisitar

- primeiro pacote de **terceiro** (não seu) que alguém quer usar;
- self-hosting do front-end (o resolver em Loxia vira exercício real);
- se `loxia.toml` já existir com `[modules]`, a fase 1 é aditiva — só adiciona
  `[dependencies]`.

---

## I-11 — Capacidades de host: stdio binário, processo, `poll` e rede

**Status:** `em avaliação` — **P0 e P2 implementados**:
`io.flush`/`io.readUtf8` ([ADR-0094](docs/adr/0094-kernel-io-flush-e-read-utf8.md)) e
`process.*` + `std.proc` + `poll` ([ADR-0095](docs/adr/0095-processos-streams-poll.md)).
`fs.open`/`net` continuam em avaliação; o servidor LSP continua em Python
([ADR-0090](docs/adr/0090-lsp-escopo-e-hospedagem.md)).
**Origem:** 2026-11-16 — "o LSP não deu em Loxia por falta de stdlib de processo/rede?".
**Relacionados:** [ADR-0071](docs/adr/0071-primitivas-de-runtime.md) (kernel, sem FFI
genérica), [ADR-0072](docs/adr/0072-stdlib-batteries.md) (`ambient`),
[ADR-0079](docs/adr/0079-stdlib-t2.md) (T2), [`TODO.md`](TODO.md) §9.1 (`R1`) e §13.9.

### A pergunta

O que exatamente falta de ferramental para processo/rede, em que forma entra (FFI genérica,
shim C, primitiva tipada) e qual caso de uso paga a conta?

### Resposta curta

LSP **não** precisa de rede: é stdio com framing `Content-Length`. O que falta é ler **N
bytes** e garantir **flush**; JSON-RPC, framing, dispatch e store de documentos são Lox
puro sobre `std.json`. O bloqueio real é outro: **nenhum programa Loxia consegue analisar
outro arquivo Loxia** — não há front-end self-hosted nem API de compilador exposta.

Então "faltou stdlib de processo/rede" era o sintoma; a causa é a ausência de uma
capacidade de compilador. Rede, para o LSP, é zero.

### Fatos do código (2026-11-16)

- kernel: 17 primitivas (`args`, `io.*`, `fs.exists/listDir`, `os.*`, `time.*`, `substr`,
  `join`, `charCodeAt`, `fromCodePoint`) em `loxia_core/execution/primitives.py` — tabela
  única com `c_symbol`, corpo Python e `ambient`; **19 desde 2026-11-16** (`io.flush`,
  `io.readUtf8` — [ADR-0094](docs/adr/0094-kernel-io-flush-e-read-utf8.md));
- `std/`: T1 + T2 prontos (`json`, `io`, `fs`, `paths`, `convert` com base64/hex **sobre
  texto**, sem `Bytes`);
- runtime C: 6 unidades por domínio (`core`, `objects`, `strings`, `containers`,
  `numeric`, `kernel`) + `lox_runtime.h`, separadas em 2026-11-16; antes era um
  `runtime.c` de 2.524 linhas, das quais ~200 kernel. `runtime/kernel_gen.h` é gerado da
  tabela de primitivas e o `kernel.c` o inclui (ABI não diverge em silêncio);
- `io.write` no binário não fazia flush; no oráculo fazia — `R1` do
  [`TODO.md`](TODO.md) §9.1, **corrigido** no ADR-0094 (o I1 não pegava porque só compara
  os bytes do fim do processo);
- LSP local = stdio ([ADR-0090](docs/adr/0090-lsp-escopo-e-hospedagem.md)).

### O que um LSP em Loxia exigiria

1. `io.readUtf8(n) -> String?` — `Content-Length` conta **bytes** UTF-8; `readLine` e
   `readAll` não servem — **✅ implementado** ([ADR-0094](docs/adr/0094-kernel-io-flush-e-read-utf8.md));
2. `io.flush() -> Nil` — o binário bufferiza — **✅ implementado** (e `io.write` já
   flusha sozinho);
3. `byteLen(s)` e largura UTF-16 — **Lox puro** (`std/utf8`); são duas unidades diferentes
   no mesmo arquivo, e é a fonte clássica de bug de posição;
4. framing + JSON-RPC + dispatch — **Lox puro** (`std/lsp` + `std.json`).

**Não precisa de:** socket, thread, `stat`/mtime, file watching. O cliente empurra o texto
(`didChange`, full sync) e módulo alterado se resolve relendo e comparando o conteúdo.

### Quem analisa o documento (o bloqueio real)

| Caminho | Precisa | Custo | Risco |
| --- | --- | --- | --- |
| **A. servidor em Python** | nada | S | nenhum; é a decisão atual |
| **B. Loxia delegando ao CLI** | `proc.spawn` + `poll` | M | ~40–100 ms de boot por mudança; debounce resolve |
| **C. Loxia com front-end próprio** | portar parser+checker | XL | **duas verdades** de diagnóstico (`check` × servidor); I4 |

B é o único caminho de dogfooding que não duplica regra: `proc.spawn("loxia", ["check",
"--error-format=json", ...])` + `std.json` no stdout já dá diagnóstico, span e trace; a
tradução span→range (code point → UTF-16) é a única lógica nova. C só depois do
self-hosting do front-end — e aí o trabalho é de compilador, não de stdlib.

### Catálogo por camada

| Camada | Superfície | Esforço | Demanda hoje |
| --- | --- | --- | --- |
| kernel #18 | `io.flush()` | S | ✅ feito (ADR-0094) |
| kernel #19 | `io.readUtf8(n) -> String?` | S | ✅ feito (ADR-0094) |
| kernel #20–26 ✅ | `process.*` (handles `Int`) + `std.proc` (`Stream`/`Process`/`Output`, `spawn`, `run`) | feito (ADR-0095) | B, `lox fmt`, `lox test` |
| kernel #27 ✅ | `process.poll(handles, timeoutMs) -> List[Int]` | feito (ADR-0095) | `spawn` com dois pipes; I/O concorrente |
| kernel #28–31 | `net.tcpListen`/`tcpConnect`; `Socket.{read, write, close}`; `net.unix*` | M | nenhum (LSP não usa) |
| kernel #32 | `fs.open(path, mode) -> File` (streaming) | M | arquivos grandes (§10 do TODO) |
| std | `utf8`: `byteLen`, `utf16Width`, decode estrito | S | LSP/qualquer protocolo |
| std | `lsp`: framing, JSON-RPC, `DocumentStore` | M | dogfooding |
| std | `process`: `run(argv) -> Result[Output, OsError]` | S | açúcar sobre `proc` |
| std | `http`: request/response sobre `net` | L | sem consumidor |
| **fora** | TLS, DNS, HTTP/2, threads, async/await, libuv, FFI genérica | — | não |

### Desenho (regras que valem mais que a lista)

- **`ambient: true` em tudo.** Fora do corpus I1/I3, como `fs.exists`/`time.now`.
  `io.write`/`io.flush` continuam determinísticos e entram no corpus.
- **Erro de host é `Result[T, OsError]`, não `T?`.** `nil` apaga `errno`; o ADR-0079 já
  admitiu que "arquivo ilegível ≠ inexistente" é dor. `OsError` é enum com `NotFound`,
  `Permission`, `IsDir`, `Busy`, `Timeout`, `Other(Int)`; `T?` fica só nas APIs antigas
  (assimetria documentada na spec).
- **Handle opaco, `close()` explícito, sem finalizer.** Boehm não é determinístico (mesma
  decisão do `fs.open` no TODO §10); `try/finally` é o cleanup. Usar handle fechado é
  `RuntimeError`; `close()` idempotente.
- **`poll` antes de thread.** É a concorrência que este runtime paga: sem heap
  compartilhado, sem data race, sem sintaxe de `async`. `spawn` com dois pipes **exige**
  `poll`, senão `stderr` enche e deadlocka.
- **Nenhum callback C→Lox que possa lançar.** `accept(handler)`/`listen(fn)` fazem unwind
  de exceção Lox através de frame C — UB na prática; a API é *pull*.
- **`proc.spawn` sem shell.** `argv` é lista; `cwd`/`env` explícitos; nunca interpolar
  string em shell.
- **`net` v1 sem DNS e sem TLS.** DNS é o primeiro passo para não-determinismo de rede (e
  teste em loopback não precisa dele); TLS é árvore de dependência (cert store, relógio,
  SNI) e não passa no portão do ADR-0014 hoje.
- **Sem FFI genérica.** O sistema de tipos não expressa ponteiro/struct/varargs/callback;
  I1 morre (o oráculo teria que usar `ctypes`, proibido no ADR-0071); ownership indefinido;
  Boehm não vê `malloc`. O shim C **é** o caminho — como primitiva tipada da tabela
  (ADR-0071), não como `dlopen` para o usuário. Ver I-12.

### Por que não agora

- O LSP em Python (ADR-0090) é a decisão certa de produto e não bloqueia nada.
- `proc`/`net` sem consumidor é superfície paga pelo codegen (portão do ADR-0014).
- `io.flush` + `io.readUtf8` são exceção: o primeiro **corrige bug**, o segundo é barato e
  fecha a lacuna de qualquer protocolo por stdio — não dependem de rede.

### Recomendação provisória

1. P0 ✅ (`io.flush`, `io.readUtf8`, regressão em modo streaming —
   [ADR-0094](docs/adr/0094-kernel-io-flush-e-read-utf8.md)); `std/utf8` em Lox continua
   pendente.
2. P1: `std/lsp` de framing (sem servidor) — é determinístico e testável por transcrição.
3. P2 ✅: `proc` + `poll` ([ADR-0095](docs/adr/0095-processos-streams-poll.md)); falta o consumidor real (`lox fmt`/test runner).
4. P3: `fs.open`; `net` só com consumidor real.

### Perguntas abertas

- [ ] `Bytes` entra antes ou depois de `net`? (LSP não precisa; HTTP binário precisa.)
- [ ] Migrar `T?` antigo para `Result`/`OsError` ou conviver com a assimetria?
- [ ] `poll` por handle ou por `Reader`/`Writer`? (Hoje não há método nativo em tipo
      embutido; handle concreto + adapter em Lox evita `NativeClassTy` completo.)
- [ ] `posix_spawn` (portável, sem fork) ou `fork`+`exec`? `posix_spawn` evita fork com GC.
- [ ] Buffering: flush por escrita (igual ao oráculo; custo em laço com `print`) ou
      `io.flush` explícito com oráculo bufferizado?
- [ ] Limite de handles por processo: tabela fixa ou dinâmica?

### Gatilhos para revisitar

- `io.flush`/`readUtf8`: já justificados (`R1`, `prompt`, JSONL).
- `proc`: quando o primeiro fluxo real precisar rodar algo (formatter, test runner, B).
- `net`: com consumidor real, teste em loopback, IP literal; DNS/TLS em ADR separado.
- kernel > ~30 primitivas: sinal de camada errada.

---

## I-12 — Tabela de binding declarativa (bindgen interno)

**Status:** `implementado na versão barata` (2026-11-16) — `runtime/gen_kernel.py` gera
`runtime/kernel_gen.h` da tabela `Primitive` e o `kernel.c` o inclui; `make primitives`
regenera e `tests/test_primitives_gen.py` falha se o gerado ficar velho. O arquivo de
dados em TOML continua **não adotado** (o gatilho segue: >30 primitivas ou um segundo
gerador).
**Relacionados:** [ADR-0071](docs/adr/0071-primitivas-de-runtime.md) (a tabela `Primitive`
já é a fonte única), [ADR-0066](docs/adr/0066-orcamento-e-gate-sintatico.md) (nada de
sintaxe), `make grammar` + `tests/test_editor_grammar.py` (precedente de artefato gerado).

### A pergunta

Adicionar uma primitiva hoje é editar a mesma assinatura em quatro lugares (tabela Python,
protótipo C, teste, spec). Dá para gerar três deles de um arquivo só? Isso é FFI
disfarçada?

### O que é

Um arquivo de dados que declara cada primitiva, e um gerador que emite o resto:

```toml
[[primitive]]
lox = "io.readUtf8"
c = "lox_io_read_utf8"
params = ["Int"]
result = "String?"
ambient = true
platform = "any"
spec = "io.md#readutf8"
```

Gerado por `make primitives`:
1. `loxia_core/execution/primitives_gen.py` — a tabela `Primitive` (o corpo Python continua
   escrito à mão em `primitives_bodies.py`);
2. `runtime/kernel_gen.h` — protótipos C com a assinatura exata que o lowering espera;
3. `tests/cases/kernel/<lox>.lx` esqueleto + entrada no manifesto;
4. checagem de que a âncora da spec existe.

`tests/test_primitives_gen.py` falha se o gerado estiver desatualizado — mesmo padrão do
`make grammar`: o artefato é gerado e editar à mão não passa.

### O que isso **não** é

- **não é FFI de usuário:** nenhum `extern fn`, nenhum `dlopen`, nenhum header lido em
  runtime; o conjunto é fechado e versionado com o compilador;
- **não gera semântica:** os corpos Python e C continuam manuais — é o pedaço que pode
  divergir, e o gerador não o protege (só teste diferencial protege);
- **não cobre tipo novo:** `Process`/`Socket`/`File` exigem checker + backend + spec; é aí
  que mora o custo real, e o gerador não ajuda.

### Por que pode valer

- o custo de hoje não é escrever a função, é **sincronizar quatro arquivos** e o teste que
  falta quando alguém esquece um;
- o protótipo C gerado pega drift de ABI em compilação, não em teste;
- `ambient`, `platform` e `deprecated` viram dados, não `if` espalhado.

### Por que pode não valer

- são ~20 primitivas; o gerador custa mais que 20 edições manuais até o kernel crescer
  (gatilho natural: ~30 ou o primeiro drift real);
- formato novo no núcleo (`tomllib` é stdlib no 3.13, mas ainda é mais um formato para o
  projeto ler);
- risco de "gerou, logo está pronto" — a primitiva só está pronta com spec + golden +
  diferencial.

### Alternativa mais barata — ✅ implementada (2026-11-16)

A tabela `Primitive` **já é dados**: gerar só o `kernel_gen.h` a partir dela, sem formato
novo e sem mover a tabela para TOML. Ganha-se o check de ABI; a tabela continua Python
(tipada, `mypy strict`, refactorável). O esqueleto de teste automático ficou de fora: os
casos novos continuam escritos à mão (o gerador não sabe a expectativa), e o que faltava
de verdade era o check de assinatura. Ver `runtime/gen_kernel.py`.

### Recomendação provisória

Não agora. Se `proc`+`poll` entrarem (I-11), fazer **antes** do `net`. Começar pela
alternativa barata; TOML só se a tabela virar fonte de mais de um gerador.

### Gatilhos para revisitar

- kernel passando de ~30 primitivas;
- primeiro drift de assinatura entre tabela e C que só apareceu em teste;
- se o gerador de protótipo C pegar um drift real, o resto se paga sozinho.

---

## I-13 — Testes: `std.test` (biblioteca) + `lox test` (runner) e mocks

**Status:** `implementado` ([ADR-0096](docs/adr/0096-testes-biblioteca-e-runner.md),
2026-11-16) — `std/test.lx` + `lox test`, com hooks e `--isolate=test`; os probes de
viabilidade ficam abaixo.
**Relacionados:** [ADR-0092](docs/adr/0092-estilo-e-formatter.md) (estilo),
[ADR-0093](docs/adr/0093-cli-agent-friendly-e-reparo.md) (CLI e JSON),
[ADR-0095](docs/adr/0095-processos-streams-poll.md) (`proc`/`poll` para o runner),
[`TODO.md`](TODO.md) §13.6 (`std.test`), `tests/runner.py` (corpus dourado — **não** é
isto), `R3` no TODO §9.1, [ADR-0096](docs/adr/0096-testes-biblioteca-e-runner.md).

### A pergunta

Como testar código Loxia? Uma biblioteca dentro da linguagem (`asserts`, `describe`/`it`,
matchers, mocks) e/ou um runner de fora (`lox test`)? O que a linguagem **não** permite e
como contornar sem inventar sintaxe?

### Fatos do código (probes de 2026-11-16, interpretador e binário)

| Capacidade | Resultado |
| --- | --- |
| `it(name, fn() { ... })` (closure como argumento, executada na hora) | ✅ idêntico nos dois motores |
| `class TestFailure(Exception) { init(msg) { this.message = msg } }` | ✅ capturável por `except Exception` |
| `class Expectation[T] { val value: T; fn toBe(other: T) }` + `expect[T]` | ✅ monomorfiza e roda nos dois motores (inclusive igualdade de listas) |
| método chamado `not` | ❌ `not` é keyword; usar `notToBe`/`negate()` |
| `<=`/`>` em `T` sem constraint | ❌ checker `E3007`; **classe não aceita constraint** (ADR-0040) |
| `expect(anyValue)` (`T = Any`) | ❌ não infere (`E3011`); `Any` como campo também não existe no backend |
| closure em **global** (`var before: fn() -> Nil = ...`) | ✅ nos dois motores (hooks de um nível são viáveis) |
| closure em **lista**, chamada depois | ❌ no binário: `R1001: Can only call functions and classes` (`R3`) |

Consequência: o desenho não pode depender de **registry de closures**. `it` executa o
corpo na hora; o runner descobre testes por **arquivo**, não por reflexão.

### Decisão de desenho (adotada): duas camadas

**1. `std.test` — biblioteca em Lox puro, determinística.**
Sem reflection, sem anotação, sem registro adiado. Módulo não aceita `var` top-level
(`E1001`), então o estado vive numa `Suite` explícita; `it` roda imediatamente e imprime TAP:

```lox
import std.test as t

val suite = t.Suite()

suite.describe("soma", fn() {
  suite.it("inteiros", fn() {
    t.expect(1 + 1).toBe(2)
  })
  suite.it("string", fn() {
    t.expect("a" + "b").toBe("ab")
  })
  suite.it("pula", fn() { suite.skip("sem rede") })
})
suite.done()   # imprime plano/resumo e encerra com 0/1
```

API mínima proposta:

- `class TestFailure(Exception)`, `class Skip(Exception)`;
- `Suite` com `describe(name, body)`, `it(name, body)`, `skip(reason)`, `report()` e
  `done()`; `fail(message)` é função livre;
- `expect[T](value) -> Expectation[T]` com `toBe`, `notToBe` (só igualdade universal; sem
  constraint dentro de classe);
- matchers numéricos como **funções livres** com `T: Ord` (`expectGt`, `expectGe`,
  `expectLt`, `expectLe`) — é o que o checker permite hoje (ADR-0081);
- `expectNil[T](value: T?)`, `expectNotNil[T](value: T?) -> T`;
- `expectList[T](items: List[T])` com `toContain`; `expectString(s)` com `contains`;
- `expectRaise(body: fn() -> Nil) -> String` (devolve a mensagem; o tipo da exceção não é
  reificável — sem `is T` dinâmico);
- `Recorder` (mocks, abaixo).

Por que imediato: (a) `R3` impede guardar closures em lista no binário; (b) ordem é a do
fonte (determinística por construção); (c) uma falha não interrompe as seguintes porque
`it` captura a exceção por teste. `suite.skip` usa um flag (`skipRequested`) porque
`except` de classe de módulo não casa no binário (`R4`).

**2. `lox test` — runner na CLI (Python).**
Não precisa de reflection: descobre `tests/**/*_test.lx` (ou os caminhos passados), roda
cada arquivo em **subprocesso** e agrega a saída TAP.

- `loxia test [paths] [--filter SUB] [--only NAME] [--jobs N] [--timeout MS] [--json]
  [--fail-fast] [--native]`;
- subprocesso por arquivo: `os.exit`, stack overflow ou panic de um teste não matam a
  suíte; `--timeout` é por arquivo (sem thread não há timeout por teste);
- `--jobs` roda N arquivos em paralelo (threads no Python; o runner em Lox, se um dia
  existir, usa `std.proc` + `poll`);
- `--native` compila cada arquivo (`--emit=exe`) e roda o binário — o runner não duplica o
  diferencial do corpus, mas dá o mesmo caminho para o usuário;
- `--json`: envelope estável (`schema_version`, `tests[]` com `file`, `name`, `status`,
  `message`), **sem duração/timestamp** por padrão (I3);
- filtro: o runner passa `-- --filter=SUB` e a lib ignora `it` que não casa (contando só
  os executados).

Alternativas descartadas para descoberta:

| Alternativa | Por que não |
| --- | --- |
| `#[test]` / anotação | sintaxe nova; gate do ADR-0066 e sem ganho sobre convenção de arquivo |
| reflection em runtime | a linguagem não tem (e não deve ter) metadata |
| registry de closures (`List[fn]`) | `R3`: não chama no binário; e o interpretador viraria a única verdade |
| gerar driver a partir de `fn test_*` | viável (o front-end Python já parseia), mas é um segundo mecanismo antes de haver dor; fica como plano B se `--only`/isolamento por teste forem necessários |

### Mocks, spies e fakes (sem reflection)

Não há monkey-patching, nem substituição de método em instância, nem interceptação. O que
existe — e é suficiente — são três padrões:

1. **Injeção por função** (o mais barato): a produção recebe `fn(...) -> ...` em vez de
   chamar o global. Stub = closure; spy = closure que registra num `Recorder`.
   ```lox
   fn total(carrinho: List[Int], now: fn() -> Int) -> Int { ... }
   t.it("usa o relógio", fn() {
     val fixed = fn() -> Int { return 1_700_000_000 }
     t.expect(total([1, 2], fixed)).toBe(3)
   })
   ```
2. **Interface + fake** (quando há estado): `interface Mailer { fn send(to: String) -> Bool }`
   e um `class FakeMailer implements Mailer` que grava em `List[(String, String)]`. É o
   mock nominal que o ADR-0080 já suporta; `Recorder` cobre contagem/ordem sem classe
   específica.
3. **Fakes de capacidade** para `process`/`fs`/`time`: a produção recebe
   `fn(List[String]) -> Output?`/`fn(String) -> String?`/`fn() -> Int`; o teste devolve
   `Output(0, "...", "")`, um mapa em memória ou um relógio fixo. Zero dependência de
   `std.test` no código de produção.

Regras que o `std.test` deve documentar: nada de mock implícito (I2), nada de ordem de mock
depender de hash (I3), e mock de processo/arquivo só entra em teste `ambient` (fora do
corpus I1).

### Limites e decisões abertas

- **Hooks**: `beforeEach`/`afterEach` de **um nível** cabem (closure em global, probe ✅);
  aninhados exigem lista de closures (`R3`). MVP: sem hooks ou um nível.
- **Localização da falha**: `TestFailure` capturada não carrega stack trace (o `Trace` não
  é exposto à linguagem), então a mensagem aponta o teste, não a linha do `expect`. Melhor
  no futuro com `Trace` acessível ou spans.
- **`done()` sai do processo?** Recomendo `report() -> Int` (puro) + `done()` que faz
  `os.exit(report())`; o runner usa o exit code.
- **`--json` compartilha schema com `check`/`mcp`?** Sim, envelope v1 + `tests[]`.
- **Convenção de arquivo**: `*_test.lx` (Go) ou `*.test.lx` (JS)? Nenhuma colide com o
  loader (o runner roda o arquivo, não importa). Recomendo `*_test.lx`.
- **Corpus**: testes puros de `std.test` entram no corpus `t3` e no diferencial; testes que
  usam `proc`/`fs`/`time` são `ambient` e ficam fora.
- **`std.asserts` vs `std.test`**: `asserts` continua sendo contrato de produção (usa
  `RuntimeError`); `std.test` tem `TestFailure`/`Skip` próprios para o runner distinguir
  falha de bug de infraestrutura.

### MVP (ordem)

1. `std/test.lx` (`TestFailure`, `Skip`, `describe`, `it`, `fail`, `skip`, `expect`,
   `toBe`/`notToBe`, `expectNil`/`expectNotNil`, `expectGt`/`Ge`/`Lt`/`Le`,
   `expectList`/`toContain`, `expectString`/`contains`, `expectRaise`, `Recorder`,
   `report`/`done`) + golden `std_test.lx` no corpus `t3` (subconjunto determinístico).
2. `loxia test` (glob, subprocesso, TAP, `--filter`, `--timeout`, `--json`, `--jobs`,
   `--fail-fast`, `--native`) + testes em pytest com projeto temporário.
3. Docs: `docs/stdlib/test.md` gerado, spec, ADR quando fechado.
4. Depois: hooks (1 nível), `--only` + isolamento por teste, snapshots, property-based com
   `std.rand` semeado, cobertura; corrigir `R3` se hooks aninhados/registry virarem
   requisito.

### Decidido (2026-11-16, [ADR-0096](docs/adr/0096-testes-biblioteca-e-runner.md))

- Duas camadas: `std.test` (Lox) + `lox test` (CLI); `it` imediato, sem registry.
- Asserções híbridas: `expect(x).toBe(y)` + funções livres com `T: Ord`/coleções/`raise`.
- Runner em Python agora; runner em Lox depois, com `proc`+`poll`.
- Fakes no usuário; `std.test` só `Recorder`.
- Descoberta só `tests/**/*_test.lx`; um subprocesso por arquivo.
- `report() -> Int` + `done()` com `os.exit`.
- Localização (trace) fica para depois; MVP aponta arquivo + nome do teste.
- `beforeEach`/`afterEach` escopados ao `describe`, com ordem externa→interna e
  `afterEach` inversa; `--list` + `--only` dão isolamento por teste com `--jobs`.

### Ainda em aberto

- [ ] Detalhes do `--json` (schema exato, `tests[]` plano ou por arquivo).
- [ ] Cobertura/snapshot/property-based: cada um é feature própria, fora do MVP.
- [ ] Expor `e.trace`/linha do `expect` (feature de linguagem, não do runner).

### Gatilhos para revisitar

- primeira suíte de usuário real (não a do repo) querendo rodar testes;
- `lox fmt`/`lox test` no caminho de CI de alguém;
- `R3` corrigido (aí registry/hooks aninhados voltam à mesa);
- pedido de cobertura/snapshot/property-based — cada um é feature própria, não MVP.
