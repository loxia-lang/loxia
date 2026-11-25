# ADR-0080 — Interfaces nominais: implementação v1

- **Status:** accepted (implementado: tree-walk/checker + backend B2)
- **Data:** 2026-11-15
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0038](0038-traits-nominais.md) (modelo, substituído na nomenclatura),
  [ADR-0007](0007-ranges-e-iteracao.md) (`Iterable` de usuário),
  [ADR-0014](0014-identidade-e-invariantes.md) (portão), [ADR-0026](0026-freeze-1.0.md) (pós-1.0),
  [ADR-0027](0027-generics-t3b.md) / [ADR-0040](0040-generics-classes-desenho.md) (generics),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md) (orçamento),
  [ADR-0067](0067-desambiguacao-sintatica.md) (`;` opcional),
  [ADR-0031](0031-backend-nativo.md) / [ADR-0048](0048-abi-classes-l5.md) (backend),
  [`../../TIPOS.md`](../../TIPOS.md) §1.1, [`../../TODO.md`](../../TODO.md) §8/§9
- **Implementação:** `loxia_core/frontend/{token_type,keywords,stmt,parser,ast_printer}.py`,
  `loxia_core/frontend/ty.py`, `loxia_core/loader/loader.py`, `loxia_core/semantics/{resolver,checker}.py`,
  `loxia_core/execution/{lox_interface,lox_class,lox_instance,interpreter}.py`,
  `loxia_core/backend/*`, `tests/cases/interface_*.lx`, `tests/test_checker.py`,
  `tests/test_backend.py`, `tests/corpus_manifest.py`

## Contexto

O [ADR-0038](0038-traits-nominais.md) fechou o **modelo** (nominal, `implements`, métodos
default, sem constraints na v1), mas deixou seis pontos em aberto e adiou a implementação.
Agora o `for-in` de usuário ([ADR-0007](0007-ranges-e-iteracao.md)) e as constraints de
generics dependem dele; sem isso, o item 8 do `TODO.md` fica travado e a stdlib continua
presa ao comparador de três vias ([ADR-0076](0076-std-lists-sort.md)).

Ao revisar a nomenclatura antes de implementar, a decisão foi chamar o conceito de
**interface**, não de "trait": a v1 é uma interface **nominal com métodos default** (modelo
Java/Kotlin/C#), não um trait de Rust (sem associated types, bounds, `impl T for C`,
despacho estático ou coherence), não um trait de Scala/PHP (estado/reuso de código) e
**não** um `Protocol` do Python (estrutural). `implements` também combina com "interface",
não com "trait". O ADR-0038 fica `superseded by ADR-0080` **apenas na nomenclatura**; o
modelo nominal e os métodos default continuam válidos.

> **Implementação (2026-11-15):** fases T1–T9 entregues — sintaxe, tipos,
> conformidade/defaults no tree-walk e no checker, loader, golden/checker/AST e backend
> **Atualização (2026-11-25):** `is`/`as` com interface foram implementados no
> [ADR-0146](0146-is-as-interface.md), usando a tabela de interfaces do descritor; a
> restrição da v1 abaixo fica histórica.

> B2 (`interface_id` + tabela `itab` no descritor de classe). `is`/`as` com interface
> seguem fora.

Este ADR não reabre o modelo: fecha as decisões de **implementação** que faltavam e define
as fases.

## Decisão

### 1. Sintaxe

```lox
interface Forma {
  area() -> Float                 // abstrato: sem corpo, `;` opcional (ADR-0067)
  fn nome() -> String {           // `fn` opcional como em método (ADR-0067)
    return "forma"
  }
  fn descricao() -> String {
    return "${this.nome()} com área ${this.area()}"
  }
}

class Circulo implements Forma {
  val raio: Float
  fn init(raio: Float) { this.raio = raio }
  fn area() -> Float { return 3.14159 * this.raio * this.raio }
}

class Triangulo(Figura) implements Forma, Desenhavel { ... }
```

- `interface` é **palavra-chave nova** e a declaração é **top-level** (como enum).
- O corpo da interface aceita **só métodos**: `fn` opcional, parâmetros e retorno anotados
  (ADR-0020). Método **abstrato** é o que não tem `{`; o fim usa a regra de `;` opcional
  já existente (fim de linha, `}` ou EOF). Método **default** tem bloco `{ ... }`.
  A decisão abstrato × default é feita pelo token `{`, **sem** depender de newline.
- `implements` é **contextual**: só é especial depois do cabeçalho de classe; continua
  identificador em qualquer outro lugar (não entra em `KEYWORDS`).
- Formas canônicas: `class C implements I { ... }` e `class C(A) implements I1, I2 { ... }`.
  Não há `class C(A, I)` (ambíguo, ADR-0038), nem `interface A : B`.
- Proibido na v1: campos/estado na interface, `init`, métodos `static`, interfaces
  genéricas, herança de interfaces, interface como valor e `is`/`as` com interface.

### 2. Tipos

- Novo `InterfaceTy(name)` em `loxia_core/frontend/ty.py`; `display` devolve o nome. Interface
  **não** é `ClassTy`: não tem construtor, campos nem herança.
- Interface é **tipo, não valor**. Usar `Forma` como expressão é erro dirigido
  (`Interface 'Forma' is a type, not a value.`), não `Undefined variable`.
- Atribuibilidade: `ClassTy(C)` → `InterfaceTy(I)` se `C` implementa `I` **direta ou
  transitivamente pela superclasse**. `InterfaceTy` → `ClassTy` nunca; `InterfaceTy` →
  `Any` sim; `InterfaceTy?`/uniões seguem as regras existentes. Interface em campo,
  parâmetro, retorno, `List[Forma]`, `Map[K, Forma]` (valor) é permitido; chave de `Map`
  continua `String`/`Int`/`Bool`.
- `is`/`as` com interface ficam **fora da v1**, como no ADR-0038: o checker recusa com
  diagnóstico dirigido (`Interface types aren't supported in 'is' yet.`), nos dois
  motores. O mapa classe→interfaces fica para quando o backend tiver a tabela (fase B2).

### 3. Verificação de `implements` (checker)

- A interface precisa estar **declarada antes** da classe que a implementa (mesma regra
  da superclasse hoje); interface desconhecida, duplicada na lista ou fora do topo é erro.
- Para cada método exigido: a classe precisa declarar um método **de assinatura exata**
  (parâmetros e retorno) **ou** herdar um default. Exato é deliberado: a ABI do `itab` é a
  da interface, então covariância/contravariância de representação (`Any` × `Int`,
  `Int` × `Float`) não é segura no backend. Divergência é `E...` com a assinatura esperada
  e a achada.
- Método de classe **sempre vence** o default; sem override, o default é herdado.
- Conflito: se duas interfaces **distintas** implementadas (incluindo as herdadas da
  superclasse) declaram o mesmo método e a classe **não** fornece uma implementação
  própria/herdada de classe, é erro — inclusive se os corpos default forem iguais.
  O programador resolve com override explícito. Não há `Forma::metodo` na v1.
- A classe pode implementar interface que a superclasse já implementa (idempotente).
- Um campo não pode ter o mesmo nome de um método exigido pela interface (como já acontece
  com método da superclasse).

### 4. Métodos default

- O corpo default é checado **uma vez**, na declaração da interface, com
  `this: InterfaceTy(I)`; só os métodos da própria interface são visíveis em `this` (sem
  campos, sem `super`, sem `init`). Chamadas a métodos abstratos são permitidas e
  despacham no runtime para a implementação da classe.
- `this` no default pode ser passado/retornado como a interface; o valor em runtime é a
  instância concreta.
- O default **não** pode acessar campo (`this.x` é erro dirigido) nem chamar `super`.
- Ordem de resolução em runtime: método próprio da classe → superclasse → defaults das
  interfaces na ordem de `implements`. Assim a herança de classe continua vencendo o
  default (modelo Java), e o resultado não depende de hash.

### 5. Runtime (tree-walk)

- Novo valor `LoxInterface(nome, defaults)`; `LoxClass` ganha `interfaces` e
  `implements_interface(nome)` (transitivo pela superclasse).
- `LoxClass.find_method` passa a cair nos defaults; o binding a `this` é o mesmo dos
  métodos normais. Representação de valor **não muda**: a instância continua sendo o
  valor; `stringify`/igualdade/`str` não mudam.
- `LoxInstance.get` não muda (já delega para `find_method`).
- Exceções embutidas (`Exception`/`RuntimeError`) não implementam interfaces.

### 6. Backend LLVM

Duas fases, ambas explícitas (sem lowering "mais ou menos"):

**B1 — lacuna declarada (histórico, substituída por B2).** Enquanto a ABI não existia,
`interface`, `implements` e anotação `InterfaceTy` falhavam com
`... is not supported by the backend yet.` (exit 65) e casos em `PENDING`. I4 era
preservado pela lacuna declarada ([ADR-0064](0064-orcamento-do-corpus.md)); os dois casos
foram promovidos a `LEVELS` em B2.

**B2 — ABI de interface (implementada).** O desenho:

- cada interface recebe um **id determinístico** pela ordem de declaração no programa
  ligado (loader incluso); nada de hash;
- o descritor de classe ganha `interface_count` + ponteiro para uma tabela de pares
  `{interface_id, itab}`; `itab` é um array de ponteiros de função na ordem dos métodos da
  interface;
- método default é compilado **uma vez por interface** com a ABI de método
  `(env, this, params...)`; override da classe aponta a função da classe no `itab`;
  a closure default fica num global `g.iface.<nome>.<método>` para que classes locais
  (descritor criado dentro de função) possam referenciá-la sem SSA entre funções;
- valor de tipo interface continua sendo o ponteiro de instância (sem tag novo); chamada
  `d.m(args)` carrega o descritor da instância, varre a tabela de interfaces (linear,
  poucas por classe), pega o ponteiro no índice do método e chama;
- classes sem interfaces têm tabela vazia; o custo é 2 words no descritor + a tabela;
- classes genéricas e locais que implementam interfaces usam a mesma tabela (a genérica
  por instanciação monomorfizada; a local no descritor construído na função);
- `is`/`as` com interface continuam fora (podem reusar a tabela depois).

### 7. Orçamento sintático (ADR-0066)

| Métrica | Antes | Depois | Teto | Observação |
| --- | --- | --- | --- | --- |
| palavras-chave | 27 | **28** | 28 | `interface`; `implements` é contextual |
| formas de declaração | 5 | **6** | 6 | `interface` |
| níveis de precedência | 19 | 19 | 19 | nenhum operador novo |
| formas de statement | 11 | 11 | 12 | interface é declaração |
| construções sensíveis a newline | ~6 | ~6 | não crescer | abstrato × default é decidido por `{` |
| grafias por conceito | 1 | 1 | 1 | uma forma de declarar/implementar |

O teste `test_scoreboard_de_keywords_bate_com_keywords` exige atualizar o placar do
ADR-0066 no mesmo commit da palavra-chave. A saída de `print` como keyword (outro item do
§8) depois devolve uma casa, mas **não** é pré-requisito.

### 8. Stdlib

Nenhum módulo muda **nesta** entrega: sem constraints, uma interface sozinha não substitui
o comparador de `std.lists.sort` nem a `List[Any]` de `std.fmt.format`. O ganho é indireto:
interfaces são o pré-requisito de `T: Interface` (constraints) e do `Iterable` de usuário.
A adoção na stdlib vem depois, em três passos declarados: constraints (`sort`/`max` sem
comparador), iterador (`for-in` sobre classe) e variádicos
(`fmt.format(template, ...args)`).

## Consequências

### Positivas

- Fecha os seis pontos em aberto do ADR-0038 sem reabrir o modelo.
- O nome "interface" descreve exatamente a v1 e combina com `implements`; evita esperar
  associated types/`impl` blocks de Rust e o sentido de "trait" em PHP/Scala.
- Erro de conformidade perto da declaração (nominal + I2), não no ponto de uso.
- Destrava constraints e `for-in` de usuário; a stdlib pode evoluir sem comparador.
- Representação de valor não muda no tree-walk; backend tem plano verificável e fase de
  lacuna declarada.

### Negativas / custos

- `interface` vira palavra-chave: código que use `interface` como identificador quebra
  (não há ocorrência no corpus hoje). `implements` contextual fica sem destaque na grammar
  gerada.
- Conflito de defaults obriga override explícito; sem `Forma::m` não há como chamar um
  default específico.
- Sem herança de interfaces nem interfaces genéricas na v1; cada uma exige ADR próprio.
- Backend B2 mexe no descritor de classe (ABI) e afeta todo o codegen de classe — risco
  alto, por isso é uma entrega separada.
- B1 foi temporário: os dois casos de interface saíram de `PENDING` para `LEVELS` em B2.
- O checker ganha um segundo contexto de `this` (interface × classe): refactor cuidadoso
  para não afrouxar campo/`super`.
- A renomeação de "trait" para "interface" invalidou a nomenclatura do ADR-0038; a
  documentação histórica que diz "trait" só muda onde for viva (TODO/TIPOS/ESCOPO/README).

### Neutras

- Interfaces não são valores nem namespaces; `print Forma` continua erro.
- A ordem de métodos da interface é a ordem de declaração e define o `itab`; é
  determinística.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Manter "trait" | Sugere o pacote Rust que não entregamos (associated types, bounds, `impl`, coherence) e colide com PHP/Scala; `trait` + `implements` mistura vocabulários |
| `Protocol` (Python) | Estrutural/duck typing; implícito, contra I2 e contra a decisão nominal do ADR-0038 |
| Estrutural (sem `implements`) | Implícito (contra I2), conformidade acidental, erro no uso, pior para o backend |
| `class C(A, I1, I2)` | Ambíguo entre superclasse e interface; o runtime decidiria sem checker |
| Defaults resolvidos por ordem de declaração | Silencioso e dependente de detalhe; override explícito é decidível |
| `Forma::metodo` na v1 | Sintaxe nova sem dor demonstrada; o override cobre |
| Vtable global com slots fixos por interface | Offsets instáveis entre classes; exigiria reservar slots em todas |
| Busca por nome no runtime (hash/string) | Mais lenta, ABI maior e ordem de hash arrisca I3 |
| Interfaces = classes / herança múltipla | Muda o modelo de objetos e o layout L5; recusado no ADR-0038 |
| Implementar tudo (semântica + backend) num commit | Diff gigante no descritor de classe; a fase B1 mantém I4 verificável |

## Plano de implementação

| Fase | Entrega | Arquivos principais |
| --- | --- | --- |
| T1 | ADR + spec + grammar + orçamento | `docs/adr/0080`, `docs/spec/{sintaxe,semantica}.md`, `make grammar` |
| T2 | AST/parser/printer: `interface`, `implements`, abstrato × default | `stmt.py`, `parser.py`, `ast_printer.py`, `token_type.py`, `keywords.py` |
| T3 | Resolver: `this` no default, duplicatas, `super` proibido | `resolver.py` |
| T4 | Checker: `InterfaceTy`, `InterfaceInfo`, conformidade, conflito, chamadas, `is/as` recusado | `ty.py`, `checker.py`, `codes.py` |
| T5 | Interpreter: `LoxInterface`, defaults, ordem de resolução | `lox_interface.py`, `lox_class.py`, `interpreter.py` |
| T6 | Loader: clonar `Interface`, renomear `InterfaceTy`/`implements` em módulos | `loader.py` |
| T7 | Testes: golden, checker, AST, determinismo, docs | `tests/cases/interface_*.lx`, `tests/test_checker.py` |
| T8 | Backend B1: recusa explícita + `PENDING` + I4 | `backend/*`, `tests/corpus_manifest.py` |
| T9 | Backend B2: id de interface, tabela, `itab`, dispatch | `lower_class_*`, `lower_model.py`, `lower_calls.py`, `runtime.c` |

Critério de pronto: `make check` verde (B1 e B2 entregues), casos golden e de erro,
`--check` limpo nos casos válidos, backend recusando **só** com a mensagem declarada,
`docs/roadmap.md`/`TIPOS.md` atualizados e `docs/decisoes.md` com a linha.

## Como verificar

Casos mínimos (golden):

- interface com método abstrato implementado por classe; default herdado; override de
  default;
- default chamando método abstrato (`this`) e `${...}`;
- classe com superclasse **e** interface; subclasse herda `implements`;
- interface como parâmetro, retorno, campo, `List[Forma]`; `Forma?` com `nil`;
- default usando `this` como valor da interface; interface em módulo importado.

Casos de erro:

- classe não implementa método exigido; assinatura incompatível; interface desconhecida;
- interface duplicada em `implements`; conflito de dois defaults sem override;
- interface fora do topo; campo no corpo da interface; `init` na interface; `super`/campo
  no default;
- interface como valor; `is`/`as` com interface; interface genérica.

Backend: os casos de interface foram promovidos de `PENDING` para `LEVELS` (l6) no mesmo
commit da ABI B2; o diferencial cobre stdout, stderr e exit code nos três canais.

Revisitar: se as constraints exigirem interfaces genéricas ou `Forma::m`, novo ADR; se B2
mostrar que a tabela de interfaces custa mais que o previsto, reavaliar com benchmark antes
de prometer I1 para interfaces.

## Referências

- [ADR-0038](0038-traits-nominais.md), [ADR-0007](0007-ranges-e-iteracao.md),
  [ADR-0014](0014-identidade-e-invariantes.md), [ADR-0066](0066-orcamento-e-gate-sintatico.md),
  [ADR-0067](0067-desambiguacao-sintatica.md), [ADR-0048](0048-abi-classes-l5.md),
  [ADR-0050](0050-monomorfizacao-t7.md)
- [`../../IDEIAS.md`](../../IDEIAS.md) I-6, [`../../TIPOS.md`](../../TIPOS.md) §1.1,
  [`../../TODO.md`](../../TODO.md) §8/§9
