# ADR-0079 — Stdlib T2: kernel mínimo, campos-container e módulos comuns

> **Atualizado por** [ADR-0145](0145-campo-any-slot-largo.md): campo `Any` passou a ser suportado com duas palavras inline (`{tag, payload}`); a recusa e a justificativa de §2 são históricas.
>
> **Emendado por** [ADR-0158](0158-json-sem-cap-de-aninhamento.md): o `std.json` deixou de ter
> cap de 16 níveis — o leitor é iterativo e o limite é a memória; os escritores continuam
> limitados pelo contrato de pilha de chamadas.

- **Status:** accepted (implementado)
- **Data:** 2026-11-15
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0071](0071-primitivas-de-runtime.md) (primitivas),
  [ADR-0072](0072-stdlib-batteries.md) (batteries),
  [ADR-0073](0073-imports-modulos.md) (módulos),
  [ADR-0017](0017-mapas-hash.md) (chaves de `Map`),
  [ADR-0048](0048-abi-classes-l5.md) (ABI de classes),
  [ADR-0055](0055-l6-any-casts.md) (`Any`),
  [ADR-0059](0059-i4-check-limpo-compila.md) (I4),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md) (gate sintático),
  [`../../TODO.md`](../../TODO.md) §13
- **Implementação:** `std/{json,fmt,paths,fs,io,cli,sets,csv,convert}.lx`,
  [`loxia_core/execution/primitives.py`](../../loxia_core/execution/primitives.py),
  [`loxia_core/backend/lower_instances.py`](../../loxia_core/backend/lower_instances.py),
  [`loxia_core/backend/lower_strings.py`](../../loxia_core/backend/lower_strings.py),
  [`loxia_core/backend/lower_containers.py`](../../loxia_core/backend/lower_containers.py),
  [`runtime/kernel.c`](../../runtime/kernel.c),
  `tests/cases/std_*.lx`, [`tests/test_std_t2.py`](../../tests/test_std_t2.py)

## Contexto

O [ADR-0072](0072-stdlib-batteries.md) fechou a política de batteries e a T1 entregou
`strings`, `lists`, `maps`, `numeric`, `asserts` e `results` sem sintaxe nova. A T2
(`json`, `fmt`, `paths`, `fs`, `io`, `cli`, `sets`, `csv`, `convert`) esbarrou em quatro
lacunas que não são "escrever mais Lox":

1. **Kernel incompleto.** `std.fs` precisa de `exists` e `listDir`; `std.io.readAll`
   precisa ler o stdin até EOF. Emular com `io.readFile`/`io.readLine` erra semântica
   (arquivo ilegível ≠ inexistente; `readLine` come a quebra final). O teto de 15 do
   [ADR-0071](0071-primitivas-de-runtime.md) bloqueava a entrada.
2. **Campos-container no backend.** `std.sets` é uma classe com um `Map` em campo.
   `--check` aceita, mas o lowering recusava `Field type 'MAP'` (e `LIST`, `TUPLE`,
   `RANGE`, `ENUM`): só escalares, `String`, função e instância tinham slot. Pela I4,
   um programa check-limpo não pode ser recusado fora de `PENDING` — e a stdlib não pode
   nascer `PENDING`.
3. **`str(Any)` no backend.** `fmt.format` recebe `List[Any]` e formata com `str`;
   o lowering recusava `Any in string conversion`, embora `print` dinâmico já soubesse
   formatar o valor boxeado.
4. **Chave de `Map` no runtime C.** O interpretador rejeita chave `Float`/lista
   (`Map keys must be strings, integers or booleans.`, [ADR-0017](0017-mapas-hash.md));
   o binário aceitava. A divergência existia antes da T2, mas `Set[T]` a expõe e a
   documentação de `std.sets` não pode prometer um erro que só um motor dá.

Além disso, `Set[T]` "sobre `Map[T, Bool]`" não é expressável hoje: o checker rejeita
`T` variável como chave (`Map keys must be String, Int or Bool`) e constraints de chave
genérica são pós-MVP (já declarado em `std.maps`).

## Decisão

### 1. Kernel: 15 → 17 primitivas

Entram na tabela única, todas `ambient` (SO/representação, fora do corpus I1):

| Primitiva | Assinatura | Semântica |
| --- | --- | --- |
| `io.readAll` | `() -> String` | lê stdin até EOF, sem normalizar quebras; stdin não-UTF-8 é `RuntimeError` |
| `fs.exists` | `(String) -> Bool` | `stat` segue symlink; distingue ilegível de inexistente |
| `fs.listDir` | `(String) -> List[String]?` | nomes ordenados por byte, sem `.`/`..`; `nil` se não for diretório legível |

O teto do [ADR-0071](0071-primitivas-de-runtime.md) passa de 15 para **17**; o critério
(SO ou representação) não mudou e nenhuma lógica de biblioteca entra no kernel.
`appendText` **não** ganha primitiva: `std.fs` relê e regrava, e o custo O(n) por append
está documentado no módulo.

Dois ajustes de paridade vieram junto: `io.readFile` abre com `newline=""` (preserva
`\r\n` como o `fopen(..., "rb")` do C) e stdin não-UTF-8 em `io.readLine`/`io.readAll`
vira `RuntimeError` em vez de vazar `UnicodeDecodeError` do Python.

### 2. Campos-container no backend

Slot de campo continua `i64`. `List`, `Map`, `Tuple`, `Range` e `Enum` passam a ser
armazenados como ponteiro (`ptrtoint`/`inttoptr`), exatamente como `String`, função,
classe e instância. O Boehm é conservador e varre o objeto da instância, então um
ponteiro em slot `i64` continua sendo raiz.

`Any` **não** entra: o valor boxeado é `{i64, i64}` e não cabe em um slot. Campo `Any`
continua recusado com `not supported by the backend yet` (lacuna declarada, não é
regressão da T2).

### 3. `str(Any)` e interpolação

`lox_str_from_any(tag, payload)` formata o valor boxeado com a **mesma** tabela do
`print` dinâmico (`format_value`). Regra de contexto preservada: no topo, `str` de
`String` é o conteúdo (sem aspas); dentro de container, a string continua citada.

### 4. Validação de chave de `Map` no runtime C

`lox_map_set`, `lox_map_has`, `lox_map_get`, `lox_map_get_checked` e `lox_map_remove`
recebem `line`/`column` e chamam `lox_map_check_key` (tags de `String`/`Int`/`Bool`),
produzindo o mesmo `R1014` do interpretador, na mesma posição. `lox_map_*` antigos sem
posição deixam de existir; o lowering passa as coordenadas do token.

### 5. `Set[T]` com `Map[Any, Bool]` interno

A API pública é genérica (`Set[T]`, `add(T)`, `has(T)`, `union(Set[T])`…), mas o campo é
`Map[Any, Bool]` para não exigir constraints de chave. Consequência declarada: `T` é
apagado no runtime e `Set[Float].add(1.5)` falha com o erro de chave do `Map`; quando
constraints entrarem (pós-MVP), o campo passa a `Map[T, Bool]` sem mudar a API.

### 6. Superfície da T2 (sem sintaxe nova)

| Módulo | Determinismo | API |
| --- | --- | --- |
| `std.json` | determinístico | `parse(Any)`/`stringify`/`pretty(value, indent = 2)`; ordem de inserção, `Int`/`Float` distintos, profundidade 16 |
| `std.fmt` | determinístico | `format(template, List[Any])`, `pad(text, width, fill = " ")`, `commas`, `fixed`, `percent`, `bytes` |
| `std.paths` | determinístico | POSIX lexical: `join`, `dirname`, `basename`, `ext`, `stem`, `normalize`, `isAbsolute`, `split` |
| `std.fs` | **ambiente** | `readText`, `readLines`, `writeText`, `appendText`, `exists`, `listDir` |
| `std.io` | escrita determinística; leitura **ambiente** | `write`, `writeErr`, `readLine`, `readAll`, `prompt` |
| `std.cli` | determinístico | `parse(args, spec)` com `flag:`/`option:`/`positional:`, `flag`, `option`, `positional`, `usage` |
| `std.sets` | determinístico | `Set[T]` com `add`/`has`/`remove`/`len`/`toList`/`union`/`intersect`/`difference` e `fromList` |
| `std.csv` | determinístico | RFC 4180: `parse` (CRLF/LF, `nil` se malformado), `stringify` (CRLF, quebra final) |
| `std.convert` | determinístico | `toInt`/`toFloat`/`toBool`, `base64Encode/Decode`, `hexEncode/Decode` sobre UTF-8, sem tipo `Bytes` |

Zero sintaxe nova: o orçamento do [ADR-0066](0066-orcamento-e-gate-sintatico.md) não foi
tocado.

## Consequências

### Positivas

- A T2 inteira roda nos dois motores; os casos `std_*` entram no nível `t2` do manifesto
  e o I1 os cobre byte a byte.
- Campos-container destravam classes de biblioteca (`Set`, futuras `Stack`/`Queue`) sem
  representação nova: slot `i64` + ponteiro.
- A divergência de chave de `Map` morre com caso diferencial próprio
  (`tests/cases/map_key_any_error.lx`).
- `str(Any)` deixa de ser lacuna de I4 e a interpolação de valor dinâmico fica
  consistente.

### Negativas / custos

- Kernel em 17: +3 símbolos para manter Python×C em sincronia; o teto antigo era
  explícito e foi revisto neste ADR, como o próprio ADR-0071 exige.
- `Any` como campo continua ausente; `Set[Float]` falha só em runtime (constraints
  pós-MVP).
- `fs.appendText` é O(n) por chamada e não é atômico entre processos — documentado.
- As assinaturas `lox_map_*` mudaram; qualquer IR antigo (não versionado) deixa de
  linkar, sem impacto no contrato público.

### Neutras

- `std.json`/`std.csv`/`std.convert` são Lox puro; nenhum parser nativo, nenhuma
  dependência.
- `std.cli` troca variádicos por `List[String]` no spec, igual ao `fmt.format`.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Emular `fs.exists`/`listDir`/`readAll` em Lox | `readFile` não distingue ilegível de inexistente nem lista diretório; `readLine` perde a quebra final. Seria semântica errada, não só lenta. |
| Passar de 15 sem ADR | O ADR-0071 exige remover outra primitiva ou justificar; a decisão fica registrada aqui. |
| Guardar campos-container em células/box | Representação nova e custo extra; ponteiro em slot `i64` é a mesma ABI de `String`. |
| `Set[T]` sobre `Map[T, Bool]` com relaxamento do checker | Alargaria a regra de chave para qualquer programa e adiaria a checagem sem ganho; `Map[Any, Bool]` mantém a regra do checker intacta e a falha no runtime, como já acontece sem constraints. |
| `std.cli` com variádicos ou spec em `Map[Any, Any]` | Variádicos não existem; spec homogêneo em `List[String]` é checável e determinístico. |
| Devolver `nil` em toda falha de stdlib | `json`/`csv`/`convert` devolvem `nil`; `cli`, `fmt` e `sets` usam `RuntimeError` para erro de uso, capturável. A escolha por módulo está na spec. |

## Como verificar

- `tests/cases/std_{json,fmt,paths,sets,csv,convert,cli}.lx` no nível `t2` do manifesto
  (interpretado × binário, três canais).
- [`tests/test_std_t2.py`](../../tests/test_std_t2.py): `std.fs`/`std.io` com entrada
  fixa, `writeErr`, `appendText` criando arquivo e `--check` de todos os casos `std_*`.
- `tests/test_backend.py`: `test_kernel_fs_ambiente_nativo`,
  `test_kernel_read_all_nativo`, `test_campos_container_nativos`,
  `test_std_fs_nativo`, `test_std_io_nativo`, `test_map_key_any_error`.
- `tests/cases/map_key_any_error.lx` no nível `l6` prova o `R1014` idêntico.
- `examples/sales.lx` é o programa real (CSV → agregação → tabela → JSON) que roda e
  compila.
- Revisitar se: constraints de chave entrarem (campo de `Set` volta a `Map[T, Bool]`),
  `Any` virar campo (representação nova), ou o kernel passar de 17 (novo ADR).

## Referências

- [ADR-0071](0071-primitivas-de-runtime.md) — tabela única, teto e critério de kernel.
- [ADR-0072](0072-stdlib-batteries.md) — tiers e critério de admissão por módulo.
- [ADR-0017](0017-mapas-hash.md) — chaves de `Map` e igualdade.
- [ADR-0048](0048-abi-classes-l5.md) — layout de instância e slots.
- [ADR-0055](0055-l6-any-casts.md) — `Any` boxeado.
- [`../spec/semantica.md`](../spec/semantica.md) — comportamento observável da stdlib.
