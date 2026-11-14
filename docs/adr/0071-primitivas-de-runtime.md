# ADR-0071 — Primitivas de runtime: fronteira nativa, tabela única e complexidade linear

- **Status:** accepted (plano; implementação pendente)
- **Data:** 2026-11-14
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0016](0016-api-stdlib-hibrida.md) (API da stdlib),
  [ADR-0035](0035-strings-texto.md) (strings como texto),
  [ADR-0059](0059-i4-check-limpo-compila.md) (I4),
  [ADR-0060](0060-orcamento-de-memoria.md) (memória),
  [ADR-0072](0072-stdlib-batteries.md) (stdlib),
  [ADR-0073](0073-imports-modulos.md) (imports), [`../../TODO.md`](../../TODO.md) §13
- **Implementação:** `runtime/runtime.c`, `src/execution/primitives.py` (novo),
  `src/execution/natives/`, `src/backend/lower_*.py`, `tests/cases/kernel/`,
  `bench/cases/string_scan.lox`

## Contexto

Hoje uma função nativa tem até **quatro definições independentes**:

1. o corpo Python que serve de oráculo (`src/execution/natives/*.py`);
2. a assinatura no checker (`_define_builtins` e `_native_modules` em
   [`src/semantics/checker.py`](../../src/semantics/checker.py));
3. o caso especial de lowering no backend ([`../../src/backend/lower_calls.py`](../../src/backend/lower_calls.py));
4. o símbolo e o corpo em C ([`../../runtime/runtime.c`](../../runtime/runtime.c)).

`math.*` são nove funções definidas nesses quatro lugares, sem nenhum teste que compare
as quatro. A divergência não aparece como falha de build: aparece como `miscompile`, como
aridade diferente ou como resultado diferente entre motores.

Além disso, o runtime nativo é **quadrático em strings**, e isso não é hipótese:

- `lox_str_char_at` ([`runtime.c:724`](../../runtime/runtime.c#L724)) varre o UTF-8 desde
  o byte 0 a cada acesso. `chars` chama por índice e `for c in s` no backend
  ([`lower_range.py:204`](../../src/backend/lower_range.py#L204)) idem: **n²/2 passos**.
- `lox_str_concat` ([`runtime.c:155`](../../runtime/runtime.c#L155)) copia os dois lados.
  Construir uma string de *m* caracteres com `+` custa **m²/2 bytes** na arena, que não
  tem `free`.
- Medido em 2026-11-14, mesmo programa nos dois motores: 20k code points → 0,09 s nativo
  × 0,10 s interpretado; 40k → 0,39 s × 0,14 s; 100k → **2,22 s × 0,25 s**. A cada
  dobra da entrada o nativo quadruplica.
- 5k linhas montadas com `src = src + linha` → `Out of memory` (arena), enquanto o mesmo
  conteúdo em literal roda em 1,5 s.

O I1 **não pega** isso: ele compara bytes, não tempo. A divergência de complexidade é
silenciosa, e é ela que decide se a stdlib pode ser escrita em Lox. Uma `split` em Lox
sobre `chars` é O(n²) no binário; com a arena sem `free`, o pior caso não é "lento", é
`Out of memory` determinístico. Sem consertar isso, toda função de string é empurrada
para nativo — exatamente a duplicação que se quer evitar.

## Decisão

### 1. O kernel é a fronteira do SO; o resto é Lox

Uma função só é **primitiva** se pelo menos uma condição valer:

- **SO**: precisa de syscall (arquivo, stdin, argv, relógio, env);
- **representação**: precisa de bytes/pontadores que a linguagem não expõe;
- **complexidade**: a versão em Lox seria assintoticamente pior, não só mais lenta.

O kernel v1 tem **no máximo 15 funções** (lista e assinaturas na §13.2 do `TODO.md`).
Tudo o mais — `split`, `trim`, `replace`, `json`, `csv`, `sort` — é Lox. Adicionar
primitiva acima do teto exige remover outra ou um ADR que justifique o crescimento.

### 2. Complexidade é contrato da representação

`LoxStr` ganha um cache preguiçoso de offsets por code point:

```text
LoxStr { i64 byte_len; i64 cp_len; const char *data; i32 *cp_offsets; }
```

- `cp_offsets` tem `cp_len + 1` entradas e é `NULL` até o primeiro acesso aleatório;
- só é construído para strings com `cp_len >= 64` (abaixo disso, varrer é mais barato
  que alocar o cache);
- é alocado na arena como todo o resto, então conta no orçamento de 64 MiB
  ([ADR-0060](0060-orcamento-de-memoria.md)) e continua sem `free`.

Garantias depois da mudança:

| Operação | Antes | Depois |
| --- | --- | --- |
| `char_at` / `chars` / `for-in` sobre `String` | O(n²) | **O(n) total** (O(1) por code point) |
| `substr(s, a, b)` | não existe | **O(1)** para localizar + O(b−a) para copiar |
| `join(parts, sep)` | não existe | **O(total)** |
| `+` em laço | O(m²) | continua O(m²) — documentado: use `join` |

`chars(s)` continua devolvendo `List[String]` (ADR-0035); `charCodeAt`/`fromCodePoint`
existem para o caminho quente (lexer, compilador) não alocar uma `String` por caractere.

Semântica das novas primitivas:

- `substr(s, start, end)`: `0 <= start <= end <= len(s)`, senão erro de runtime (mesma
  regra de índice de `List`); `strings.slice` na stdlib é a versão que clampeia.
- `join(parts, sep)`: só `List[String]`.
- `charCodeAt(s, i)`: índice de code point, erro fora dos limites.
- `fromCodePoint(cp)`: `0 <= cp <= 0x10FFFF`, sem surrogates (`0xD800..0xDFFF`), senão erro.

### 3. Uma tabela é a fonte única do contrato

`src/execution/primitives.py` (módulo folha: só `frontend.ty` e a stdlib do Python)
declara cada primitiva:

```python
@dataclass(frozen=True)
class Primitive:
    lox: str                     # "io.readFile"
    c_symbol: str                # "lox_io_read_file"
    params: tuple[Ty, ...]
    result: Ty                   # T? quando falível
    py: Callable[..., object]    # corpo do oráculo, sem regra de tipo
    ambient: bool                # fora do corpus I1 (SO/relógio/argv/env)
```

- o **checker** registra `FnTy(params, result)` a partir da tabela;
- o **interpretador** embrulha `py` num `LoxCallable` genérico (aridade e tipos vêm da
  tabela);
- o **backend** usa `c_symbol` e a assinatura LLVM da tabela em vez de um `if` por nome;
- os **testes** iteram a tabela e exigem um caso por entrada.

Polimórficos históricos (`len`, `chars`, `str`, `repr`, `range`) ficam fora do
dataclass porque o tipo deles é sobrecarregado; a tabela cobre primitivas **monomórficas
novas**. Migrá-los é opcional e não bloqueia nada.

### 4. Sem FFI genérica e sem `ctypes` agora

- **FFI genérica** (`extern fn`) fica fora: ABI, ownership, portabilidade e superfície de
  erro sem retorno proporcional. A tabela fixa cobre o que a stdlib precisa.
- **O interpretador não chama o runtime C via `ctypes`.** Isso eliminaria o segundo
  corpo, mas: (a) `uv run main.py` passaria a exigir compilador C; (b) quebraria a regra
  de "sem dependência de runtime"; (c) o oráculo deixaria de ser independente do código
  que ele policia; (d) a conversão por chamada inviabilizaria `charAt`/`substr`.
- **Gatilho para revisitar:** kernel acima de 15 funções **ou** divergência Python×C
  observada em teste. Aí a decisão volta em ADR novo.

### 5. Ambiente e determinismo

`ambient: true` marca o que depende do mundo e **não entra no corpus I1/I3**: arquivo,
stdin, argv, env, relógio, listagem de diretório. Os testes dessas primitivas usam
entrada fixa e nunca imprimem caminho absoluto, PID, timestamp nem ordem de diretório.
`io.write`/`io.writeErr` **não** são ambientes: bytes escritos são determinísticos e
podem entrar no corpus. `args()` devolve os argumentos **depois** do script/binário, para
que interpretador e binário vejam a mesma lista.

## Consequências

### Positivas

- A stdlib em Lox passa a ser viável no motor nativo; o kernel fica pequeno e estável.
- Uma assinatura, um símbolo, um teste: adicionar primitiva deixa de ser edição em quatro
  arquivos e deixa de poder divergir.
- `for c in s` e `chars` deixam de ser quadraticamente piores no binário.

### Negativas / custos

- `LoxStr` muda de layout; **todo** construtor precisa inicializar o cache (mecânico, mas
  toca todo o runtime).
- +4 bytes por code point nas strings acessadas aleatoriamente. O teto de 64 MiB não
  muda, mas o ponto exato do `Out of memory` pode mudar em programas que hoje morrem
  antes — os testes de memória precisam ser reavaliados.
- Quatro primitivas novas são superfície de linguagem: spec, checker e golden no mesmo
  commit.
- Complexidade não é testável no CI; o gate é o bench `string_scan.lox`, que não roda em
  CI (§6). O número antes/depois fica registrado aqui e no commit.
- O `for-in` sobre `String` no backend muda de lowering (índice + `char_at` → cursor ou
  cache), tocando código do L5/L6.

### Neutras

- O tree-walk não muda: Python já é O(1) por índice de `str`.
- O I1 continua comparando bytes; nenhum caso atual muda de resultado.
- `chars` mantém a semântica do ADR-0035; o que muda é o custo.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Detectar ASCII e indexar direto (`byte_len == cp_len`) | Resolve o código-fonte, mas a complexidade passa a depender do conteúdo: string não-ASCII continua quadrática e o contrato fica invisível. Pode ser um atalho **dentro** do cache, não a solução. |
| Duas representações (bytes + array de code points) | 4× de memória e toda operação duplicada; o cache de offsets entrega o mesmo ganho com custo menor. |
| `chars` devolver uma view preguiçosa | Nova espécie de valor; `List[String]` já é spec e o checker/backend teriam que representá-la. |
| Interpretador chamando o C via `ctypes` | Dependência de build para rodar o oráculo, perde independência e inviabiliza operações por caractere. |
| Deixar como está e escrever a stdlib em nativo | É a duplicação crescendo: cada função nativa = 4 definições + teste diferencial manual. |
| Otimizar `+` com ropes/`StringBuilder` implícito | Muda a representação de valor e o I2 ("nada implícito"); `join` explícito resolve o caso real. |

## Como verificar

- `tests/cases/kernel/*.lox`: um caso por primitiva, com entrada fixa; os de I/O rodam em
  diretório temporário e não imprimem caminho.
- `tests/corpus_manifest.py`: novo nível `k0` com os casos de `substr`/`join`/
  `charCodeAt`/`fromCodePoint`; os três canais (stdout, stderr, exit) têm que bater.
- `bench/cases/string_scan.lox`: varre 100k code points. Antes: 2,22 s. Alvo: ≤ 0,05 s.
  O número medido fica neste ADR e no commit.
- Testes de memória do backend: o teto de 64 MiB continua falhando de forma determinística
  (`exit 70` + `Out of memory.`).
- **Critério para reverter:** se o cache não reduzir o bench em ≥ 5×, ou se o custo de
  memória estourar casos legítimos, volta para ADR.

## Referências

- [ADR-0035](0035-strings-texto.md) — strings como texto, `chars` e code points.
- [ADR-0060](0060-orcamento-de-memoria.md) — arena de 64 MiB como contrato.
- [ADR-0016](0016-api-stdlib-hibrida.md) — builtins globais × métodos × namespaces.
- [`../spec/garantias.md`](../spec/garantias.md) — I1–I4.
- [`../../TODO.md`](../../TODO.md) §13 — inventário do kernel e ordem de entrega.
