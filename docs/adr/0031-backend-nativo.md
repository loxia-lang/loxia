# ADR-0031 — Backend nativo: contrato de valor, runtime e corpus

- **Status:** accepted (L0–L3 completos; L4–L7 pendentes)
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0006](0006-int-float-separados.md) (`Int`/`Float`),
  [ADR-0014](0014-identidade-e-invariantes.md) (I1–I3), [ADR-0020](0020-assinaturas-explicitas.md)
  (anotações), [ADR-0026](0026-freeze-1.0.md) (`Any` fora do backend),
  [ADR-0027](0027-generics-t3b.md), [ADR-0028](0028-overflow-debug.md),
  [`../../TODO.md`](../../TODO.md) §6, [`../spec/garantias.md`](../spec/garantias.md)
- **Implementação:** `src/backend/`, `runtime/runtime.c`, `--emit=ll|obj|exe`,
  `tests/test_backend.py`

## Contexto

O tree-walk está completo (caps. 4–13, freeze da 1.0, T3b) e é a especificação
executável. O `TODO.md` §6 descrevia o backend, mas seis decisões continuavam abertas e
cada uma delas muda o formato do IR e o contrato com o runtime. Decidir durante a
implementação significaria refazer o lowering a cada descoberta.

As decisões abaixo foram tomadas em sequência, uma a uma, antes de escrever código.

## Decisão

### 1. Ferramenta: `llvmlite`, e o backend é opcional

Python + `llvmlite` (0.50, LLVM 22 embutido). O `llvmlite` constrói o módulo; o object
file é emitido pelo próprio LLVM embutido e o link é feito pelo compilador C do sistema
(`cc`/`clang`/`gcc`). Não se emite `.ll` + `clang` como caminho de build: o IR de uma
versão do LLVM não é garantidamente parseável por outra, e o `.ll` vira artefato de
inspeção (`--emit=ll`), não etapa.

`llvmlite` é **extra opcional** (`uv sync --extra llvm`), não dependência de runtime: o
interpretador continua sem dependências e `python main.py programa.lox` não importa nada
do backend. A lib fica isolada em `src/backend/llvm_ir.py`, a única fronteira sem tipos
(o resto do backend passa pelo mypy strict).

### 2. Modelo de valor: desboxado por tipo concreto

| Tipo | Representação |
| --- | --- |
| `Int` | `i64` |
| `Float` | `double` |
| `Bool` | `i1` |
| `String` | `{i64 byte_len, i64 cp_len, i8* data}` (L3) |
| classe/instância | ponteiro para struct (L5) |
| closure | `{fnptr, env*}` (L4) |

Rejeitado o modelo *tagged i64*: usar 3 bits de tag reduz o inteiro a 61 bits e conflita
com o wrap de **i64 completo** prometido pelo ADR-0006/0028. `Any`, `List` cru e `Map`
heterogêneo são **erro de compilação** (exit 65) até o L6; quando entrarem, ganham uma
caixa `LoxValue` usada só nos pontos dinâmicos, nunca no caminho estático.

Consequência de pipeline: `lox build` **sempre** roda o resolver e o checker; o backend
consome tipos concretos.

### 3. `T?`: ponteiro nulo para referência, `{i1, T}` para escalar

`String?`/`Obj?` são ponteiros (`null` = `nil`). `Int?`/`Float?`/`Bool?` são
`{i1, T}`. O narrowing (ADR-0018/0025) é o que paga a escolha: no bloco estreitado o
valor volta a ser `T` cru. Sentinela não serve para `Float` porque `NaN` é valor legítimo.

### 4. Erro de runtime: `lox_panic(linha, msg)`

O runtime faz `fflush(stdout)`, imprime `msg\n[line N]` no stderr e sai com **70**,
idêntico ao interpretador. `main` devolve `0` no sucesso — o `Int` de uma função `main`
do usuário não vira exit code. Traps de hardware (SIGFPE/SIGSEGV) estão proibidos: exit
136/139 violaria o I1. O teste diferencial compara **stdout, stderr e exit code**.

### 5. `Float` impresso: menor representação + regras do `repr` do Python

`stringify` usa a menor string que faz round-trip, com as convenções do CPython (`1.0`,
`-0.0`, `1e-05`, `1e+16`). **Implementado no L1** sem vendorar Ryu: o runtime testa
`%.{p}e` para `p = 1..17` e usa o primeiro que `strtod` reconstrói (O(17) conversões,
microssegundos por print). O contrato é o mesmo do Ryu e é policiado por fuzz contra
`repr()` em `tests/test_backend.py` (400 bit patterns aleatórios + especiais). Ryu fica
como otimização se o perfil pedir. `printf("%g")` segue fora: depende de locale (viola o
I3) e `lox_init` fixa `LC_NUMERIC=C`.

### 6. `String`: bytes UTF-8 + `cp_len`

Header de 16 bytes com `byte_len`, `cp_len` e ponteiro. `len` é O(1); `cp_len` é
constante em literal e soma na concatenação, então não custa varredura. `byte_len ==
cp_len` detecta ASCII sem campo extra — o fast path para indexação/slice futuros.
Semântica de `s[i]`/slice fica congelada em *code points*, independente do layout.

### 7. Memória: arena com teto, Boehm depois

`lox_alloc` é o único ponto de alocação: bump allocator sobre blocos, sem `free`, com
teto configurável e `lox_panic` determinístico ao estourar (melhor que OOM killer). Trocar
por Boehm é mudar o corpo de uma função. Contagem de referência está fora (ciclos são
permitidos e vazariam); mark & sweep preciso fica para depois do L6.

### 8. Generics: monomorfização lazy com side table do checker

O checker publica `type_of(expr)` e a substituição de cada `Call`; o lowering instancia
sob demanda, cacheia por `(fn, tipos)` e usa mangling derivado dos tipos
(`id$i64$ptr`), nunca contador de ordem de visita. Limite de instâncias (10.000) com exit
65 evita explosão por recursão genérica. O backend **não** re-inferencia: duas fontes de
verdade de tipos é como se produz miscompile silencioso.

### 9. Erro estático vira panic site

O interpretador erra em runtime (exit 70) em casos que o checker pega em compile-time
(aridade, `true + 1`, chamar instância, variável indefinida). Para o I1 valer também nos
casos de erro, o backend **rebaixa** esse diagnóstico a `lox_panic` no ponto exato,
avaliando os operandos na ordem da linguagem (os efeitos colaterais antes do erro precisam
sair no stdout). Erros que não têm contrapartida em runtime (falta de anotação) continuam
exit 65.

**Parcialmente implementado**: o `ErrorReporter` classifica diagnóstico (`lowerable`) e o
lowering rebaixa erro de operando (`1 + true`, `-true`, `true // 2`), **aridade**
(`Expected N arguments but got M.`, mensagem montada no compile time) e **variável
indefinida** a `lox_panic` num bloco inalcançável, preservando stdout e exit code.
Propriedade indefinida e índice fora da faixa entram no L5/L6.

### 10. HIR: normalização leve, não HIR completa

`AST → AST normalizada → IR`. O L1 não tem açúcar, então o seam ainda não tem conteúdo; o
primeiro desugar (`for-in`, `??`, ternário) nasce no **L2**, quando existirem variáveis —
`for-in` precisa de variável de laço e `??` precisa de temporário para avaliar o receptor
uma vez. HIR completa (slots, SSA leve, células) só quando closures e classes pedirem.

### 11. Corpus e I1

O corpus diferencial é o **corpus inteiro anotado**: `tests/cases`, `exemplos/` e
`tests/official/cases`. Hoje a suíte do livro é código cru do Crafting Interpreters
(`fun`, `//`, nenhuma anotação) e não compila — anotá-la é pré-requisito do **critério de
saída do L1**, não do L0 (que não depende de corpus).

Regras de operação do harness:

- CI instala o extra `llvm` sempre; ausência de `llvmlite` é **falha**, não `skip`
  (`LOX_REQUIRE_LLVM=1`).
- Promoção monotônica: caso que passou no nível não pode voltar a falhar.
- `docs/spec/garantias.md` passa a dizer que o I1 vale para o corpus declarado, e a
  suíte oficial só entra quando estiver anotada.

### Quando cada decisão entra em vigor

| Decisão | Primeiro nível em que vale | Estado hoje |
| --- | --- | --- |
| 1. `llvmlite` opcional + `.o`/`cc` | L0 | ✅ |
| 2. Valor desboxado | L0 (`Int`/`Bool`/`nil`), L1 (`Float`); referências L3–L5; `Any` L6 | ✅ L0–L1 |
| 3. `T?` (nulo/tag) | L2 (escalar) e L3 (referência) | ⬜ |
| 4. `lox_panic` | L0 | ✅ |
| 5. `Float` + formatação | L1 (fuzz contra `repr`) | ✅ |
| 6. `String` UTF-8 + `cp_len` | L3 | ✅ |
| 7. Arena com teto | L3 (primeiro heap) | ✅ (64 MiB) |
| 8. Monomorfização | L6 (até lá, função genérica é rejeitada) | ⬜ |
| 9. Erro estático → panic site | L0 para operandos; L2/L5 para aridade e nomes | 🟡 |
| 10. Normalização leve | L2b: ternário/`and`/`or`/`??` ✅; `for-in` depende de `Range` | 🟡 |
| 11. Corpus anotado | bloqueia o L2 (corpus do nível) | 🟡 (54 de 78 `tests/cases` e 4 de 5 `exemplos/` passam no `--check`) |

## Consequências

### Positivas

- O IR do L0 é enxuto (`add i64`, `call lox_print_int`) e o wrap de i64 é nativo.
- Uma única fonte de tipos (checker) e uma única fonte de semântica de erro (runtime).
- O interpretador permanece sem dependências; o backend é opt-in.
- O teste diferencial nasce no primeiro commit, comparando três canais.

### Negativas / custos

- 203 arquivos precisam de anotação (78 de `tests/cases` + 5 de `exemplos/` + 120 da
  suíte oficial) antes do L1.
- `ErrorReporter` deixa de ser binário (teve erro/não teve) e passa a classificar.
- O backend rejeita `Any`, `List` cru, `Float` e `String` até os níveis correspondentes;
  cada rejeição é uma linha de código e um caso de teste.
- Ryu é código de terceiro no repositório (licença permissiva, com atribuição).

### Neutras

- `--emit` entra como flag do CLI atual; o subcomando `lox build` fica para quando o CLI
  ganhar subcomandos.
- Recursão profunda continua divergindo (SIGSEGV × traceback do Python) e fica fora do
  corpus até existir contador de pilha.
- A ordem de intercalação de stdout e stderr no mesmo descritor (`2>&1`) não faz parte do
  I1: a comparação é por canal. `lox_panic` faz flush do stdout antes de escrever o erro.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Emitir `.ll` textual e chamar `clang` | descompasso de versão do LLVM; sem verificador nem tipos |
| `tagged i64` (V1 do TODO §6.3) | 61 bits conflitam com o wrap de i64 do ADR-0006/0028 |
| Caixa uniforme estilo clox | fácil no L1, lento para sempre; o checker viraria decoração |
| `{i1, T}` uniforme para `T?` | dobra toda referência opcional no caminho quente de OO |
| Boehm desde o início | `libgc` vira dependência de build e de CI |
| Re-inferir tipos no backend | duas fontes de verdade → miscompile silencioso |
| Backend aceitar código sem anotação | exigiria inferência global (T4) e anularia o desboxamento |
| Excluir casos de erro do corpus | esvaziaria o I1 justamente onde ele é mais útil |

## Como verificar

```bash
uv sync --extra llvm
uv run pytest tests/test_backend.py -q          # diferencial do L0
uv run python main.py --emit ll exemplo.lox     # IR inspecionável
uv run python main.py --emit exe -o app exemplo.lox && ./app
```

Os testes comparam stdout, stderr e exit code com o interpretador. O L0 cobre wrapping de
i64, divisão/resto com sinal, panics de divisão por zero e rebaixamento de erro de operando
(`print 1 + true` sai com 70 e a mesma mensagem, sem imprimir diagnóstico no build). O L1
cobre `Float` (promoção, `/`, `%`, comparações com NaN, `-0.0`, `1e+16`), `if`/`while` e a
formatação de `double` com fuzz contra `repr`. O manifesto `tests/corpus_manifest.py`
declara os casos por nível (hoje `l0` e `l1`) e cresce de forma monotônica.

## Critérios para revisitar

- **L1**: antes de fechar, as anotações do corpus precisam existir e o rebaixamento de
  erro estático precisa estar pronto; senão o I1 mede menos do que promete.
- **L3**: se `String` virar gargalo de memória antes do L6, antecipar Boehm.
- **L4/L5**: se o lowering começar a duplicar o `interpreter.py`, promover a
  normalização da decisão 10 para HIR.
- **L6**: se `Any` for necessário antes do previsto, a caixa `LoxValue` entra como
  caminho separado — nunca substituindo o desboxado.
