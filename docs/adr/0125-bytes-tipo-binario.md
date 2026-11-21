# ADR-0125 — `Bytes`: tipo de valor binário

- **Status:** accepted
- **Data:** 2026-11-21
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0035](0035-strings-texto.md) (String é texto, não bytes),
  [ADR-0015](0015-listas-tipadas.md) (listas), [ADR-0017](0017-mapas-hash.md) (chaves),
  [ADR-0026](0026-freeze-1.0.md) (freeze), [ADR-0066](0066-orcamento-e-gate-sintatico.md)
  (gate sintático), [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md) /
  [ADR-0087](0087-heap-cap-e-self-hosting.md) (memória), [ADR-0119](0119-fs-open-handles-e-erro-de-host.md)
  (erro como `Result`), [ADR-0123](0123-orcamento-do-kernel-por-grupo.md) (kernel),
  [ADR-0126](0126-modulo-nativo-embutido-sqlite.md) (SQLite), [ADR-0127](0127-pacotes-com-codigo-nativo.md)
  (pacotes nativos)
- **Implementação:** `loxia_core/execution/lox_bytes.py`, `loxia_core/execution/numeric.py`
  (helpers), `loxia_core/semantics/checker.py` (tipo `Bytes`), `loxia_core/backend/lower_bytes.py`,
  `runtime/bytes.c`, `std/bytes.lx`, `tests/cases/bytes/*.lx`, `tests/corpus_manifest.py`

## Contexto

A linguagem tem texto (`String`, UTF-8, índice por code point, sem `s[i]` — [ADR-0035](0035-strings-texto.md))
e listas de inteiros (`List[Int]`), mas **não tem um tipo para dados binários**. Hoje o
workaround é `List[Int]` com 0..255: `std.convert` (`_utf8Bytes`, `base64Decode`),
`std.hash` (`_utf8Bytes`) e `std.utf8` fazem isso à mão.

O custo não é só estético:

- **Memória.** Um `List[Int]` gasta ~28 bytes por byte de payload (cabeçalho da lista +
  ponteiro + objeto `Int`). 1 MB de dado vira ~28 MB.
- **Tempo.** Converter byte a byte em Lox é O(n) com constante alta; para protocolo, hash e
  arquivo binário, é inviável.
- **Sem ABI.** Um módulo nativo (SQLite, libpq) não tem como devolver BLOB/buffer sem
  copiar para `List[Int]` e voltar.
- **Sem integridade de texto.** Guardar binário em `String` quebraria a invariante de UTF-8
  e o `len` por code point; é exatamente a assimetria que o [ADR-0035](0035-strings-texto.md)
  fechou.

Isso bloqueia, em ordem: BLOB do SQLite ([ADR-0126](0126-modulo-nativo-embutido-sqlite.md)),
protocolo do Postgres, compressão, hash binário e TLS ([ADR-0127](0127-pacotes-com-codigo-nativo.md)).
Sem `Bytes`, "baterias" param no texto.

## Decisão

### 1. `Bytes` é um tipo de valor imutável e contíguo

- Sequência contígua de **bytes 0..255**, com `len`, índice e igualdade estruturais.
- **Imutável**, como `String`: não há `push`/`set`, não há aliasing nem `version`.
- **Distinto de `String`**: `Bytes` não é texto, não valida UTF-8, não tem índice por code
  point. A conversão é explícita nos dois sentidos.
- Não é chave de `Map` (chaves continuam `Bool`/`Int`/`String` — [ADR-0017](0017-mapas-hash.md)).
- Novo tag de valor (13) na ABI, ao lado de `String`/`List`/`Map`/tupla/enum.

### 2. Operações de linguagem (sem sintaxe nova)

| Operação | Contrato |
| --- | --- |
| `len(b)` | número de **bytes** (não code points; contraste explícito com `len(s)`) |
| `b[i]` | `Int` 0..255; fora da faixa é `RuntimeError` |
| `b == c` | igualdade estrutural O(n); `b == s` é `false` (tipos diferentes) |
| `str(b)` / `repr(b)` | `0x<hex minúsculo>` (determinístico; interpolação usa o mesmo) |

`b[i]` reusa a sintaxe de índice que `List`/`Map`/tupla já têm: é semântica de tipo novo,
não sintaxe nova. **Não há literal** (`b"..."`), nem slice sintático (`b[a..z]`): construção
e fatias são funções/métodos. Um literal, se um dia doer, passa pelo
[ADR-0066](0066-orcamento-e-gate-sintatico.md).

### 3. Construção e conversão: namespace `Bytes` + métodos

`Bytes` é tipo **e** namespace, exatamente como `Int` (tipo + `Int.parse`):

| Forma | Contrato |
| --- | --- |
| `Bytes.empty()` | `Bytes` vazio |
| `Bytes.fromList(xs: List[Int])` | valida 0..255; fora da faixa é `RuntimeError` |
| `Bytes.fromText(s: String)` | codifica UTF-8 |
| `Bytes.fromHex(s: String) -> Result[Bytes, BytesError]` | RFC 4648 base16; ímpar/inválido = `Err` |
| `Bytes.fromBase64(s: String) -> Result[Bytes, BytesError]` | RFC 4648 |

Métodos do valor:

| Método | Retorno | Notas |
| --- | --- | --- |
| `b.slice(start, end)` | `Bytes` | O(n); mesmas regras de faixa de `substr` |
| `b.concat(other)` | `Bytes` | O(n+m) |
| `b.toList()` | `List[Int]` | interop com o código existente |
| `b.toText()` | `Result[String, BytesError]` | UTF-8 **estrito**; inválido = `Err` |
| `b.toHex()` | `String` | minúsculo |
| `b.toBase64()` | `String` | RFC 4648 |

`std.bytes` entra depois, só para o que é composição: `Builder` incremental (sobre
`List[Int]` na v1, documentado como O(n) de memória), `compare` lexicográfico e helpers de
inteiro big-endian/little-endian (`u16be`, `u32le`, …). Nada disso é primitiva.

### 4. Memória e backend

- Alocação via `lox_alloc_atomic` (buffer puro), imutável; sem finalizer (Boehm não é
  determinístico).
- `len` e índice O(1); `slice`/`concat` O(n); igualdade O(n) com short-circuit de identidade.
- Backend: tag 13, `LoxBytes { int64_t len; unsigned char *data; }` em `runtime/bytes.c`
  (9ª unidade do runtime), lowering em `lower_bytes.py`, boxe em `Any` como os demais.
- O interpretador usa `bytes` do Python; a igualdade/ordem de formatação é espelhada.

### 5. Fronteira com módulo nativo

`Bytes` é o **tipo de buffer** na ABI de módulos nativos ([ADR-0126](0126-modulo-nativo-embutido-sqlite.md)):

- entrada é somente leitura (imutável), sem empréstimo de ponteiro para o C;
- saída é sempre um `Bytes` novo alocado pelo runtime, nunca um ponteiro estrangeiro;
- o módulo nativo não guarda referência a `Bytes` depois de retornar.

### 6. Consequências no kernel (emenda ao ADR-0123)

`Bytes` em si **não adiciona primitiva de host**: construção/métodos são superfície do tipo,
como `List.push`. Duas primitivas ficam registradas para quando houver consumidor:

- `fs.readBytes(id, n) -> Bytes?` (grupo `fs`, +1) — ler binário sem passar por UTF-8;
- `digest.sha256Bytes(data: Bytes) -> Bytes` (grupo `digest`, +1) — hash binário;
  `std.hash.sha256(text)` continua como wrapper hex.

Com isso o orçamento do [ADR-0123](0123-orcamento-do-kernel-por-grupo.md) vai a `fs` 11,
`digest` 2 e **40 exatos**, retirando `time.monotonic` da reserva (sem consumidor).

### 7. Compatibilidade

`std.convert`, `std.hash` e `std.utf8` **não mudam** na v1: as APIs `String`/`List[Int]`
continuam válidas. Variantes `Bytes` são aditivas (ex.: `convert.base64EncodeBytes`), e a
migração é opt-in. Nada de quebra silenciosa.

## Consequências

### Positivas

- Desbloqueia BLOB (SQLite), protocolo binário (pg), compressão, hash binário e TLS.
- Memória de ~28 bytes/byte para ~1 byte/byte; base para streaming e mmap futuro.
- A ABI de módulo nativo passa a ter um tipo de buffer honesto.
- `String` continua sendo texto: a invariante de UTF-8 não é relaxada.

### Negativas / custos

- Mais um tag e mais um caminho em **dois** motores (interpretador e runtime C), mais
  checker, boxe, formatação e corpus.
- Imutabilidade torna construção incremental O(n²) sem um `Builder`; a v1 paga isso em
  payload pequeno e documenta.
- `str`/`repr` em hex podem imprimir megabytes; é determinístico, mas verboso.
- Duplicação temporária com `List[Int]` (`convert`/`hash`), até as variantes nascerem.
- `Bytes` não é chave de `Map`; agrupar por conteúdo exige `toHex` como chave.
- O tipo aumenta a superfície do `Any` e dos testes diferenciais.

### Neutras

- `Bytes` é nominal e não-genérico; não há `Bytes[T]`.
- `is Bytes`/`as Bytes` seguem a mesma regra dos outros tipos de valor (a validar no checker).

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Continuar com `List[Int]` | ~28 bytes por byte, lento e sem ABI; cada módulo nativo copiaria duas vezes. |
| `String` em Latin-1 para binário | Quebra a invariante de UTF-8 e o `len` por code point ([ADR-0035](0035-strings-texto.md)); I2 morre. |
| `Bytes` mutável (como `List`) | Aliasing, `version` e igualdade mutável; protocolo/crypto preferem valor imutável. Um `Builder` cobre a construção. |
| Literal `b"..."` agora | Sintaxe nova: gate do [ADR-0066](0066-orcamento-e-gate-sintatico.md), sem necessidade na v1. |
| Slice `b[a..z]` | Sintaxe nova; `slice` como método cobre. |
| Buffer nativo com `mmap`/zero-copy | Sem consumidor e sem contrato de lifetime; fica para depois. |

## Como verificar

- Golden `tests/cases/bytes/*.lx`: construção (vazio, `fromList`, `fromText`), hex/base64
  round-trip, UTF-8 inválido → `Err`, índice fora da faixa, `slice`/`concat`/igualdade,
  `len` em bytes vs code points, `str`/`repr`, `Bytes` dentro de `Any` e de `List`.
- Property test: `Bytes.fromList(b.toList()) == b`; `Bytes.fromText(s).toText() == Ok(s)`
  para `s` UTF-8 válido; `fromHex(toHex(b)) == b`.
- Diferencial no backend (tag, boxe, igualdade, formatação) no corpus I1.
- Bench de buffer grande (1 MB) contra `List[Int]` para registrar o ganho.
- `--check` com anotação `Bytes`, `Bytes?` e união; I4 preservado.

Critério para revisitar: necessidade de construção incremental eficiente (aí um `Builder`
nativo, não mutabilidade), slice sintático, ou `Bytes` como chave de `Map` (mudança de
[ADR-0017](0017-mapas-hash.md)).

## Nota de implementação (2026-11-21)

O 79a/79b (interpretador/checker e backend) fica com:

- `Bytes` como `Prim("Bytes")`, namespace `Bytes` e o enum built-in `BytesError`
  (`InvalidHex`/`InvalidBase64`/`InvalidUtf8`, cada um com `message`, sem import). A
  decisão inicial era uma classe com `kind`/`message`; o 79b trocou por enum porque o
  backend constrói enums em C (`lox_enum_new`/`lox_enum_set`) sem sintetizar uma classe
  com ctor/layout, e porque o conjunto de erros é fechado e casa com `match` exaustivo;
- métodos como **tabela nativa** (`bytes_api.py`), compartilhada por checker e dispatcher —
  `b.slice` é um valor chamável, como `List.push`;
- decode **hex em ambas as caixas** e **base64 canônico** (padding obrigatório, sem espaços,
  bits de padding não-zero rejeitados); `toText` é UTF-8 estrito;
- `Bytes` **não** é chave de `Map` no checker e `_canonical_key` também a recusa em runtime
  (`Map[Any, V]`);
- o 79b acrescenta o tag 13, `runtime/bytes.c` (9ª unidade), boxe em `Any`/`List`,
  `Bytes?`, `is`/`as`, formatação e o corpus diferencial em `tests/cases/bytes/`;
- `for byte in b` produz `Int` 0..255 nos dois motores (laço de índice no lowering);
- método como **valor** (`val f = b.toHex`) continua lacuna declarada no backend, igual a
  `List.push`: o caso fica em `PENDING`, e a ABI de method values para List/Map/Bytes está
  registrada na Discussions #92;
- `BytesError` é enum com payload de mensagem (id reservado -1), e o C constrói
  `Result`/`BytesError` com `lox_enum_new`/`lox_enum_set`, sem classe sintética.
- O 79c fecha a superfície: `std.bytes` (`Builder` sobre `List[Int]`, `compare`, helpers
  `u16be/le`, `u32be/le`, `u64be/le`), `fs.readBytes`/`File.readBytes` (grupo `fs` 11) e
  `digest.sha256Bytes`/`std.hash.sha256Bytes` (grupo `digest` 2), total **40** primitivas.

## Referências

- [ADR-0035](0035-strings-texto.md) — por que `String` é texto.
- [ADR-0123](0123-orcamento-do-kernel-por-grupo.md) — orçamento de kernel.
- [ADR-0126](0126-modulo-nativo-embutido-sqlite.md) — BLOB e a fronteira nativa.
- RFC 4648 (base16/base64) e UTF-8 (RFC 3629).
