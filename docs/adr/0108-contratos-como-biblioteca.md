# ADR-0108 — Contratos como biblioteca (sintaxe adiada)

- **Status:** accepted (biblioteca implementada; piloto de adoção na stdlib em andamento)
- **Data:** 2026-11-18
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0014](0014-identidade-e-invariantes.md) (portão),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md) (gate sintático),
  [ADR-0107](0107-adiados-e-nao-objetivos.md) (adiados),
  [ADR-0096](0096-testes-biblioteca-e-runner.md) e
  [ADR-0098](0098-property-based-testing.md) (testes/propriedades),
  [ADR-0042](0042-excecoes.md) (exceções),
  [issue #14](https://github.com/loxia-lang/loxia/issues/14)
- **Implementação:** [`std/contracts.lx`](../../std/contracts.lx),
  `tests/cases/std_contracts.lx`, `tests/cases/std_contracts_property.lx`,
  `tests/cases/this_in_lambda.lx`, `tests/cases/nil_value.lx`,
  [`../stdlib/contracts.md`](../stdlib/contracts.md)

## Contexto

A issue [#14](https://github.com/loxia-lang/loxia/issues/14) propôs design by contract
como sintaxe: `requires`/`ensures` entre a assinatura e o corpo, `invariant` em classes,
`result`/`old` e um modo `--contracts=off|check|warn`. A proposta é a mais madura das
ideias abertas, mas não passa no portão do [ADR-0014](0014-identidade-e-invariantes.md)
nem no orçamento do [ADR-0066](0066-orcamento-e-gate-sintatico.md) sem decisões que ainda
não existem:

- `old(expr)` não tem semântica de snapshot definida (referência vs. valor, listas, ciclos,
  handles nativos);
- `invariant` é insustentável enquanto campos são públicos e mutáveis: o objeto pode ser
  quebrado de fora, e `init`/reentrância/herança não têm regra;
- Liskov exige combinação de contratos na herança (`require else`/`ensure then`), metadata
  na vtable e uma decisão sobre checagem estática (indecidível);
- “fatal, não capturável” é uma categoria nova de erro, com política de `finally` e unwind;
- `--contracts=off` só é honesto se contratos forem puros (não há sistema de efeitos), e
  `warn` continua depois de uma pré-condição falsa;
- o backend precisaria lowerar tudo com stderr byte a byte idêntico (I1), e sem backend os
  casos viram `PENDING` (hoje o corpus tem 0 `PENDING`).

Ao mesmo tempo, a dor real existe e é mais estreita do que a proposta: a stdlib já expressa
pré/pós-condições em prosa e faz checagens imperativas (`powMod`, `factorial`, `fmt.pad`,
`convert`), o comparador de `sort` é documentado mas não policiado, e `std.property` já
oferece geração/shrinking determinísticos. O que falta é uma forma **explícita e
reutilizável** de declarar e checar contratos, não necessariamente sintaxe.

A decisão também foi motivada por três achados do piloto no backend: `this` dentro de
lambda/função local em método passava no `--check` e falhava no lowering nativo
(`E4002 internal lowering error`); `check[T]` com `T = Nil` gerava um parâmetro `Nil`
sem representação; e closures dentro de `try` não capturavam locais. Os três foram
corrigidos como parte deste ADR; o primeiro é uma promessa do
[ADR-0022](0022-lambdas.md) e uma violação de I4.

## Decisão

**Contratos entram como biblioteca (`std.contracts`), não como sintaxe.** A sintaxe de
`requires`/`ensures`/`invariant` fica adiada com gatilhos; a biblioteca é o mecanismo
interino e o experimento que produz evidência para a decisão futura.

### 1. API

- `ContractError(Exception)`: violação de contrato; **não** é `RuntimeError`, para não ser
  engolida por `except RuntimeError`. É capturável explicitamente, e não capturada termina
  em `exit 70` com `R1010` e stack trace.
- `require(condition, message = "precondition failed")`,
  `ensure(condition, message = "postcondition failed")` e
  `checkInvariant(condition, message = "invariant violated")`: primitivas manuais.
- `check[T](name, pre, body, post) -> T`: avalia `pre` antes do corpo (se falso, o corpo
  não roda), chama `body`, avalia `post(result)` só no retorno normal e devolve o resultado.
- `checkMethod[T, R](name, self, pre, body, post) -> R`: como `check`, com o receptor
  explícito. Evita capturar `this` em closure e funciona nos dois motores.
- `checkVoid(name, pre, body, post) -> Nil` e `checkMethodVoid[T](...) -> Nil`: variantes
  para funções/métodos que devolvem `Nil`, sem parâmetro de resultado.
- `old` é uma variável local capturada antes da mutação; `result` é o parâmetro de `post`.
  Não há mágica de snapshot: listas/mapas/instâncias continuam por referência, e quem
  precisa de cópia copia explicitamente.
- Predicados devem ser puros e totais; a biblioteca não impõe isso.

### 2. Escopo

- Sem sintaxe, sem `invariant` automático, sem herança/Liskov, sem contrato de interface,
  sem verificação estática e sem modos `off|warn`.
- Contratos são **cooperativos**: só rodam onde o autor chama `require`/`check`/etc.
- Campos públicos continuam tornando invariantes uma convenção, não uma garantia.
- Para falha esperada continua valendo `Result`/`T?`; contrato é para bug de programação.

### 3. Nomes e compatibilidade

- `checkInvariant` (não `invariant`) para não colidir com uma futura palavra-chave.
- `require`/`ensure` são distintos de `requires`/`ensures`, então uma futura sintaxe pode
  coexistir; se ela for aceita, `ContractError` e a semântica pre→body→post são reusados.

### 4. Correções de backend que o piloto exigiu

- **`this` lexical em lambda/função local**: o passe de captura agora trata `This` como
  uso de um binding sintético do método; quando capturado, o receptor vive em célula e
  atravessa o `env`. Cobre lambda direto, lambda retornado e função local; caso
  `tests/cases/this_in_lambda.lx` no corpus diferencial.
- **`Nil` em parâmetro de tipo de função e em local**: `Nil` passa a ter um slot `i32`
  dummy no ABI (sem payload); chamadas passam `0` e locais `Nil` são suportados. Isso
  remove o `E4001` de `check[T]` com `T = Nil`. Parâmetro **nomeado** `Nil` continua
  recusado pelo checker (`E1005`, “use `Any`”): a correção é para tipos de função e
  locais, não uma nova feature de parâmetro.
- **Captura em `try`/`raise`**: o passe de captura agora percorre corpo, handlers e
  `finally`, então uma lambda dentro de `try` que captura um local (inclusive o binding
  do `except`) é boxed e chega ao `env`. Sem isso, `check` dentro de `try` falhava no
  lowering nativo com “Undefined variable”.

## Piloto de adoção (2026-11-20)

O primeiro piloto usa contratos **só como pós-condições internas**, sem trocar a validação
de entrada pública:

- `std.numeric.gcd`: garante que o resultado divide os dois argumentos (inclusive nos
  casos de zero); entradas inválidas continuam com o comportamento atual.
- `std.numeric.powMod`: garante `0 <= result < modulus`; `modulus <= 0` e `exponent < 0`
  continuam `RuntimeError`.
- `std.paths.normalize`: preserva absolute/relative e garante que o resultado não tem
  segmento vazio/`.` nem `..` fora do prefixo relativo. `normalize` foi separada em
  `_normalize` para a pós-condição ficar na fronteira pública.

A regra é deliberada: contrato é para **bug de implementação**, não para entrada do
usuário. Assim nenhum chamador válido passa a ver `ContractError`. O caso
`tests/cases/std_contracts_pilot.lx` (t2) roda nos dois motores e usa `forAll` para
gcd, powMod e idempotência de `normalize`.

A primeira onda tocou **2 módulos**. A segunda adicionou:

- `std.convert.base64Encode`: garante tamanho múltiplo de 4, alfabeto e padding válidos;
  `base64Decode(base64Encode(s))` é property test.
- `std.lists.sort`: separa `_sort` recursivo da fronteira pública e garante tamanho
  preservado e resultado ordenado por `compare`.

Com **4 módulos**, o gatilho de revisão de sintaxe do ADR foi atingido. A decisão
continua **biblioteca**: o piloto não mostrou necessidade de `requires`/`ensures`
automáticos, e qualquer sintaxe continua exigindo o portão do ADR-0066. A revisão fica
registrada como próximo passo, não como implementação automática.

## Consequências

### Positivas

- Zero sintaxe e zero dívida de gramática: não mexe em parser, keywords, newline, LSP,
  formatter, grammar ou no orçamento do ADR-0066.
- Roda nos dois motores e cabe num PR de stdlib; não abre `PENDING` nem adia I4.
- Erro distinto de `RuntimeError`, com integração natural a `std.test`/`std.property`:
  `ContractError` é `Exception`, então o `forAll` o captura, faz shrinking e reporta seed.
- O mesmo predicado serve de documentação, checagem de runtime e oráculo de teste.
- É reversível e mensurável: se não pegar, remove o módulo; se pegar, produz a evidência
  que falta para decidir a sintaxe.
- As correções de `this` e `Nil` fecham duas lacunas reais do backend, independentemente
  de contratos.

### Negativas / custos

- Não é automática nem fatal: sem chamada, não há contrato; `except Exception` pode engolir.
- Sem `old`/`invariant`/herança/Liskov/interface; invariantes seguem cooperativos.
- Sem checagem estática de predicados: contrato tautológico ou errado passa.
- Verbosa e com alocação de closures; não usar em caminho quente.
- Duplica parte de `std.asserts` (`assert` vs. `require`) e cria mais um tipo de erro para
  o usuário distinguir.
- Retrofitar a stdlib existente troca `RuntimeError` por `ContractError` e quebra
  chamadores; a adoção é aditiva (código/teste novo) até uma decisão de versão.
- Pode dar falsa confiança: contrato não é prova.

### Neutras

- A biblioteca é o fallback de uma futura sintaxe; a semântica e o tipo de erro foram
  desenhados para serem reusados.
- `checkVoid`/`checkMethodVoid` são conveniências para `Nil`; `check`/`checkMethod` são a
  forma geral.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Sintaxe `requires`/`ensures`/`invariant` agora | Não passa no gate: `old`, invariante com campos públicos, Liskov, fatalidade e orçamento de newline/keywords em aberto; backend teria que acompanhar no mesmo PR. |
| Só `std.asserts` | `RuntimeError` é capturável e não há `result`/ordem pre→body→post; é assert, não contrato. |
| Classe `Contract` em vez de `check` | Não adiciona capacidade sobre closures; mais alocação e superfície. |
| Wrapper `guarded(fn, pre, post)` | Exigiria uma função por aridade e complicaria tipos; sem ganho sobre `check`. |
| Contratos estáticos/refinamento | Fora do escopo do checker gradual, indecidível e promete mais do que testa. |
| Doc comment com contrato | Stringly, sem typecheck e sem runtime; não policia nada. |
| Tipos antes de contratos (`Result`, enums, smart constructors) | Complementar, não substituto: evita estados ilegais, mas não dá culpa no limite nem oráculo de teste. |

## Como verificar

- `tests/cases/std_contracts.lx`: pre, pós, invariante, `check`, `checkMethod`,
  `checkVoid`/`checkMethodVoid`, `check` com `Nil`, e `ContractError` não capturado por
  `RuntimeError`; `--check` limpo e os três canais iguais no corpus (`t2`).
- `tests/cases/std_contracts_property.lx`: `forAll` + contrato, com seed/shrinking.
- `tests/cases/std_contracts_pilot.lx`: contratos nas funções da stdlib e properties de
  gcd, powMod e `normalize`, nos dois motores.
- `tests/cases/this_in_lambda.lx` (`l5`): `this` em lambda direto, lambda retornado e
  função local, nos dois motores.
- `make check` (com backend) e `make stdlib-docs`; página gerada em
  `docs/stdlib/contracts.md`.
- Revisitar a sintaxe quando: (a) a biblioteca for usada em 3+ módulos da stdlib ou 10+
  property tests; (b) houver 2+ casos reais pós-#12 em que a falta de `old`/invariant/
  herança/culpa automática seja a dor principal; (c) houver protótipo de backend para uma
  cláusula com paridade byte a byte; (d) `old`/invariant/Liskov tiverem semântica escrita.
  Se a biblioteca bastar, a sintaxe continua adiada; se for bypassada, é evidência a favor.

## Referências

- [ADR-0014](0014-identidade-e-invariantes.md) — portão de admissão e I1–I4.
- [ADR-0066](0066-orcamento-e-gate-sintatico.md) — orçamento e gate sintático.
- [ADR-0107](0107-adiados-e-nao-objetivos.md) — itens adiados e gatilhos.
- [ADR-0022](0022-lambdas.md) — `this`/`super` lexicais em lambdas.
- [ADR-0096](0096-testes-biblioteca-e-runner.md), [ADR-0098](0098-property-based-testing.md)
  — testes e property-based testing.
- [ADR-0042](0042-excecoes.md) — `Exception`/`RuntimeError`.
- [`std/contracts.lx`](../../std/contracts.lx), [`std/asserts.lx`](../../std/asserts.lx).
