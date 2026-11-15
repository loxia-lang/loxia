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
