# IDEIAS — parking lot (só o que ainda está aberto)

Só ficam aqui **coisas que ainda precisam ser feitas ou decididas**. Decisões fechadas
viram ADR + [`docs/decisoes.md`](docs/decisoes.md); o que já foi implementado sai daqui.

> **Escopo:** nada aqui é 1.0; o freeze está no
> [ADR-0026](docs/adr/0026-freeze-1.0.md). Para o mapa 1.0 × depois, veja
> [`ESCOPO.md`](ESCOPO.md).

## Pendências com direção já decidida

- **Generics além do T3b:** métodos genéricos, herança de `Box[Int]`, `is/as` reificado,
  type application explícita, função genérica como valor, recursão polimórfica e variance
  declarada continuam adiados ([TODO.md](TODO.md) §10).
- **Math:** `log`, `exp`, `sin`, `cos`, `tan`, `pow` e constantes (`math.pi`) dependem da
  libm; ficam fora do I3 até existir uma biblioteca determinística.
- **Bindgen:** reavaliar a tabela de primitivas em TOML só se o kernel passar de ~30
  primitivas ou surgir um segundo gerador.
- **Host:** `std/lsp` (framing), `fs.open` (streaming) e `net` (com consumidor) — I-11.

## I-4 — Contratos (`requires` / `ensures` / `invariant`)

**Status:** `em avaliação`.
**Decidir até:** depois do codegen estabilizar e antes de estabilizar a stdlib.

### A pergunta

Design by Contract na linguagem? Onde ficam as cláusulas, são opcionais, e qual o custo?

### Terminologia

O que foi descrito como "invariantes antes do corpo da função" é, na literatura, uma
**pré-condição**:

| Conceito | Onde | Verifica |
| --- | --- | --- |
| **Pré-condição** (`requires`) | antes do corpo | o que o chamador deve garantir |
| **Pós-condição** (`ensures`) | depois do corpo | o que a função garante, dado que a pré valeu |
| **Invariante de classe** (`invariant`) | na classe | vale na entrada e saída de todo método público |
| **Invariante de laço** | no `while`/`for` | antes/depois de cada iteração (P3, mais difícil) |

### Sintaxe proposta (Eiffel/Dafny-like, entre assinatura e corpo)

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
- No `ensures`, `result` é o valor de retorno e `old(expr)` é o valor na entrada
  (snapshot **raso**: `old(lista)` não congela o conteúdo).
- `invariant` de classe é checado na entrada e na saída de métodos públicos (não em
  privados, para não pagar duas vezes).
- Expressões de contrato são **puras**: sem I/O, atribuição ou `raise`; o checker impõe
  (ou restringe a comparações, aritmética, `len` e funções marcadas `pure`).
- Herança (cap. 13): pré-condições podem ser **enfraquecidas**, pós-condições
  **fortalecidas** (Liskov); invariantes são herdados.

### Opcional em três eixos

| Eixo | Opções | Recomendação |
| --- | --- | --- |
| **Declarar** | com/sem cláusulas | opcional por função (zero contrato = zero custo) |
| **Checar** | `off` / `check` / `warn` | `check` no interpretador/dev; `off` no nativo release, ligável com `--contracts=check` |
| **Onde** | runtime / estático | runtime por padrão; o checker pode provar casos triviais e evitar a checagem |

- `--contracts=off`: cláusulas são **parseadas e tipadas**, mas não executadas. "Off" é
  otimização, não permissão para código quebrado.
- `--contracts=warn`: só para migração; nunca default (segue com estado inválido).
- Violação é **falha fatal** (como `assert`), não `throw` recuperável: `try` em volta
  mascararia um bug. No REPL, reporta e mantém a sessão.
- Custo: `old(...)` pode alocar snapshot; contrato com `sorted(xs)` é O(n log n) — a
  complexidade deve ser documentada e `off` precisa existir.

### Contratos como testes

Pré e pós-condições são **oráculos de teste de graça**: um gerador property-based pode
produzir entradas que satisfazem `requires` e verificar `ensures`. É o argumento mais
forte a favor de DbC e combina com o fuzzing previsto no `TODO.md` §7.

### Impacto técnico

- **Parser:** três cláusulas novas, só entre assinatura e corpo; sem ambiguidade.
- **Resolver:** contratos veem parâmetros e, em `ensures`, `result`/`old` (snapshot na
  entrada).
- **Checker:** pureza, tipos e `result` só em `ensures`.
- **Interpretador:** avalia antes/depois; erro estruturado próprio.
- **LLVM:** cada cláusula vira `icmp` + branch para o runtime de falha; `--contracts=off`
  remove tudo. **Não** transformar contrato em `llvm.assume` antes de checar: pré violada
  viraria UB em vez de erro.
- **Testes:** golden de violação (com `kind`/`clause`/`bindings`) e de que `off` não muda
  o resultado.

### Argumentos

A favor:
1. **Documentação executável**: a intenção fica no código e é verificada, não em comentário
   que apodrece.
2. **Erro cedo e local**: a violação aponta a cláusula e os valores.
3. **Testes de graça**: pré/pós viram oráculo para property-based testing e fuzzing.
4. **Barato de começar**: são cláusulas opcionais; o custo é no checker, não em um runtime
   novo.

Contra:
1. **Custo de execução**: pós-condições com `old`/ordenação podem dominar o tempo; `off` no
   release é obrigatório, mas aí o contrato não vale em produção.
2. **Falsa segurança**: contrato não é verificação formal nem substitui tipos e testes.
3. **Complexidade de linguagem**: três cláusulas, `old`, `result`, pureza e herança é
   bastante superfície para uma linguagem em construção.
4. **Contratos em LLVM**: fácil de implementar, fácil de errar (`assume` = UB).

### Recomendação provisória

- **Contratos: sim, opcionais por declaração**, com `requires`/`ensures`/`invariant`,
  checagem ligada por padrão no interpretador e desligável no nativo
  (`--contracts=off|check|warn`). Violação = erro fatal estruturado (`C1xxx`), não exceção
  capturável.
- **Ordem prática:** contratos depois do cap. 10, quando há funções para anotar.

### Riscos e anti-metas

- Não tratar contrato como fronteira de segurança: com `off`, ele não existe.
- Não permitir efeito colateral em contrato.
- Não usar `llvm.assume` em contrato antes de ter checagem.
- Não versionar a sintaxe de contrato sem ADR próprio.

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
- Dafny: <https://dafny.org/>
- SPARK/Ada: <https://www.adacore.com/sparkpro>
- Python `icontract`: <https://github.com/Parquery/icontract> · `deal`:
  <https://deal.readthedocs.io/>
- Property-based testing: <https://hypothesis.readthedocs.io/>

---

## I-7 — Paralelismo (multithread) — em avaliação

**Status:** `a pensar` — sem data; depende de async ([ADR-0037](docs/adr/0037-async-direcao.md))
e de caso de uso/benchmark. Concorrência de I/O já é resolvida com `poll` (I-11).
**Decidir até:** depois que async existir e houver caso de uso + benchmark, antes de
prometer performance multinúcleo.

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
- Falha em worker precisa de regra (fatal global? `Result` por tarefa?) — `try`/`Result`
  já existem, falta o modelo de falha.

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

## I-9 — Módulos fora do projeto e pacotes externos

**Status:** `em avaliação` — falta resolver monorepo e pacote externo.
**Decidir até:** antes do primeiro release público — é o pré-requisito técnico do
[`TODO.md`](TODO.md) §14.4.

### A pergunta

Com a regra atual do [ADR-0073](docs/adr/0073-imports-modulos.md) — raiz = diretório do
arquivo de entrada, `..` e caminho absoluto são erro, `std.` é raiz reservada — como um
programa consome:

1. um **monorepo** (`../shared/util.lx`, fora da pasta do projeto);
2. um **pacote de terceiro** instalado ou vendorizado?

Sem quebrar I3 (determinismo) nem a segurança de "import nunca escapa da raiz".

### Fatos do código (2026-11-16)

- [`loxia_core/loader/loader.py`](loxia_core/loader/loader.py): módulo = arquivo, pasta =
  namespace, `_` privado; `STD_ROOT = bundle_dir("std")`; o loader **inlina** os módulos em
  compile-time (não há módulo em runtime).
- A resolução é a mesma para os dois motores (o backend recebe a AST achatada) — uma regra
  só, e o I1 não depende de runtime de módulos.
- O wheel já entrega `loxia` + `std/` + runtime ([ADR-0088](docs/adr/0088-distribuicao-e-raizes-de-modulo.md));
  `tests/test_install.py` prova o layout instalado com `import std.json`.
- O corpus `t1`/`t2` do diferencial ainda roda a partir do repo, não do wheel.

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

**B agora** (`std` continua embutida e reservada; a opção A segue funcionando de graça,
porque sem manifest a raiz é o projeto). **C depois**, e só com lockfile + hash de conteúdo — sem
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

## I-10 — Gerenciador de pacotes (o "uv" da Loxia)

**Status:** `em avaliação` — fases 1–4 em roadmap.
**Decidir até:** fase 1 antes do primeiro `loxia add`; fase 3 só com demanda real.

### A pergunta

O gerenciador de pacotes pode viver no `loxia` que já roda/compila/testa, no espírito do
`uv`, sem um segundo nome (`loxpkg`)?

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
| **1. Manifest + lock** | `[dependencies]` no `loxia.toml`, `loxia.lock` (versão exata + `sha256`), `loxia lock`, `loxia fetch --offline`, cache local | M | CLI + ADR-0088 §3 |
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

## I-11 — Capacidades de host: framing de LSP, `fs.open` e rede

**Status:** `em avaliação` — resta P1 (`std/lsp`) e P3 (`fs.open`, `net`); o servidor
LSP continua em Python ([ADR-0090](docs/adr/0090-lsp-escopo-e-hospedagem.md)).
**Relacionados:** [ADR-0071](docs/adr/0071-primitivas-de-runtime.md),
[ADR-0072](docs/adr/0072-stdlib-batteries.md), [`TODO.md`](TODO.md) §9.1 e §13.9.

### O que falta

- **`std/lsp`** (P1, M): framing `Content-Length`, JSON-RPC 2.0 e `DocumentStore` em Lox
  puro sobre `io.readUtf8`/`io.flush`, `std.json` e `std.utf8`. Determinístico e testável
  por transcrição, sem servidor.
- **`fs.open`** (P3, M): streaming para arquivos grandes; handle opaco, `close()`
  explícito e idempotente, sem finalizer (Boehm não é determinístico).
- **`net`** (P3, L): só com consumidor real; v1 sem DNS/TLS, loopback com IP literal; TLS
  em ADR separado.
- **Bloqueio do LSP em Loxia:** não é kernel, é front-end self-hosted/chamável. O caminho B
  (delegar a `loxia check --error-format=json` via `process.run`) cobre diagnóstico sem
  duplicar regra; o caminho C (parser+checker em Loxia) é projeto de compilador.

### Regras que continuam valendo

- `ambient: true` em tudo que toca SO/rede; fora do corpus I1/I3.
- Erro de host novo é `Result[T, OsError]`; `T?` fica só nas APIs antigas.
- Handle opaco com `close()`; usar handle fechado é `RuntimeError`.
- `poll` antes de thread; `spawn` sem shell; nenhum callback C→Lox; sem FFI genérica.
- Kernel > ~30 primitivas é sinal de camada errada; tipo opaco de handle antes de crescer.

### Perguntas abertas

- [ ] `Bytes` entra antes ou depois de `net`? (LSP não precisa; HTTP binário precisa.)
- [ ] Migrar `T?` antigo para `Result`/`OsError` ou conviver com a assimetria?
- [ ] `fs.open`: modo texto/binário, offset e `read(n)`/`write` no mesmo handle?
- [ ] `net`: qual consumidor paga a conta? DNS/TLS ficam para quando?
- [ ] `std/lsp`: transcrição de teste em TAP ou fixture JSON?

### Gatilhos para revisitar

- `std/lsp`: quando o servidor Python incomodar (boot, distribuição) ou houver consumidor.
- `fs.open`: arquivo grande real no caminho do formatter/LSP.
- `net`: com consumidor real, teste em loopback com IP literal.
- kernel > ~30 primitivas: sinal de camada errada.

---

## I-13 — Testes: o que falta

- [ ] Detalhes do `--json` (schema exato, `tests[]` plano ou por arquivo).
- [ ] Cobertura e snapshot (features próprias; property-based já tem
      [ADR-0098](docs/adr/0098-property-based-testing.md)).
- [ ] Localização de falha no relatório: expor `e.trace`/linha do `expect` (feature de
      linguagem, não do runner).
