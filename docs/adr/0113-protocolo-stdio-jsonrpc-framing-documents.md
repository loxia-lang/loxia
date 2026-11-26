# ADR-0113 — Protocolo stdio em três módulos: `std.jsonrpc`, `std.framing` e `std.documents`

> **Atualizado por** [ADR-0145](0145-campo-any-slot-largo.md): campo de tipo `Any` passou a ser
> suportado pelo backend. Na issue [#215](https://github.com/loxia-lang/loxia/issues/215) o
> `RpcFailure` ganhou `data: Any` e `errorOf` devolve a falha tipada; a restrição registrada
> abaixo é histórica.

- **Status:** accepted (implementado em 2026-11-19)
- **Data:** 2026-11-19
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0072](0072-stdlib-batteries.md) (stdlib em Lox),
  [ADR-0094](0094-kernel-io-flush-e-read-utf8.md) (`io.readUtf8`/`io.flush`),
  [ADR-0090](0090-lsp-escopo-e-hospedagem.md) (LSP Python; nenhum servidor em Loxia),
  [ADR-0014](0014-identidade-e-invariantes.md) (portão de admissão),
  [ADR-0079](0079-stdlib-t2.md) (T2 e campo-container),
  [ADR-0041](0041-enums-match.md) (`Result`/enums), [ADR-0095](0095-processos-streams-poll.md)
  (`process.read`), issue [#9](https://github.com/loxia-lang/loxia/issues/9)
- **Implementação:** `std/jsonrpc.lx`, `std/framing.lx`, `std/documents.lx`,
  `std/json.lx` (`parseResult`/`JsonResult`), `tests/cases/std_{jsonrpc,framing,documents}.lx`,
  `tests/cases/std_json.lx`, `tests/cases/result_nil.lx`,
  `tests/test_protocol_lox.py`, `tests/corpus_manifest.py` e
  `loxia_core/backend/lower_enums.py`/`lower_variables.py` (bug do payload `Nil`).

## Contexto

A issue [#9](https://github.com/loxia-lang/loxia/issues/9) pedia um `std/lsp` com framing
`Content-Length`, envelopes JSON-RPC 2.0 e um `DocumentStore`, sem servidor e sem processo.
O [ADR-0090](0090-lsp-escopo-e-hospedagem.md) já tinha decidido que o servidor LSP fica em
Python até o self-hosting, porque um programa Loxia não alcança o front-end do compilador.
Ou seja: a issue pedia uma **fundação** cujo consumidor só existe depois — exatamente o caso
que o portão do [ADR-0014](0014-identidade-e-invariantes.md) manda interrogar.

A análise mostrou três coisas que a issue tratava como uma:

1. **JSON-RPC 2.0** é um padrão de envelopes, independente de transporte e de LSP; serve
   LSP, MCP e DAP. É puro e determinístico.
2. **`Content-Length`** é transporte; `std.io` é casca fina do kernel e `std.json` é RFC
   8259, então nenhum dos dois é o lugar. O kernel já entrega leitura exata por bytes
   ([ADR-0094](0094-kernel-io-flush-e-read-utf8.md)) e o `process.read` do
   [ADR-0095](0095-processos-streams-poll.md) entrega "até n bytes" cortando em fronteira
   UTF-8 — este é o único reader que pode devolver menos que o pedido.
3. **`DocumentStore`** é estrutura de dados: URI opaca, texto e versão. Não precisa de JSON
   nem de I/O, e é reusável por qualquer ferramenta de editor.

Três restrições do compilador moldaram a API, verificadas no checker e no backend:

- `Result[Any, E]` não é construível: `E3011` recusa instanciar a variável de tipo com
  `Any`, mesmo com tipo esperado. Daí `JsonResult` em `std.json` e `Result` com `T`
  concreto nos outros módulos.
- Campo de tipo `Any` era recusado pelo backend (`E4001`). As mensagens continuam
  `Map[String, Any]` + accessors; `FrameFailure`/`DocumentError` seguem só com campos
  `Int`/`String`, e `RpcFailure` passou a guardar `data: Any` quando o campo entrou
  ([ADR-0145](0145-campo-any-slot-largo.md), issue
  [#215](https://github.com/loxia-lang/loxia/issues/215)).
- O backend quebrava em `Result[Nil, E]` que casasse um payload `Nil` (E4002, violação da
  I4). O bug foi corrigido com caso de regressão `tests/cases/result_nil.lx`.

## Decisão

### 1. Três módulos planos, por contrato — não um `std/lsp`

O `std` é plano ([ADR-0072](0072-stdlib-batteries.md)), então as camadas são arquivos
irmãos, com dependência em uma direção:

```
std.documents   (puro; não importa os outros)
std.jsonrpc     -> std.json
std.framing     -> std.strings, std.utf8; std.io só nos adaptadores
std.lsp         (futuro) -> os três, só quando houver política de servidor
```

`std/lsp` não nasce nesta decisão: `initialize`, `capabilities`, diagnóstico e
`positionEncoding` são política de aplicação, não biblioteca. Se um dia nascer, ele é fino.

### 2. Tier T3 e lugar no `std`

Entram como T3 ("extra, entra com caso de uso") no bundle, não como `libs/`, repositório
separado ou exemplo. Motivos: uma implementação roda nos dois motores (I1 de graça), o
I3 não depende de terceiro, a documentação é gerada junto e não há registry para publicar
um pacote à parte. O consumidor desta entrega é o **harness de transcrição**
(`tests/test_protocol_lox.py`): um programa Lox real lê frames do stdin, responde e tem os
bytes de stdout comparados. Foi ele que fechou o requisito de "partial reads" com stdin de
verdade.

### 3. API

**`std.jsonrpc`** — envelopes, sem I/O:

```lox
class RpcFailure { val code: Int; val message: String; val data: Any }
fn decode(text: String) -> Result[Map[String, Any], RpcFailure]
fn encode(message: Map[String, Any]) -> String
fn request(id: Any, method: String, params: Any = nil) -> Map[String, Any]
fn notification(method: String, params: Any = nil) -> Map[String, Any]
fn success(id: Any, result: Any = nil) -> Map[String, Any]
fn failure(id: Any, code: Int, message: String, data: Any = nil) -> Map[String, Any]
fn isRequest/isNotification/isResponse/hasId(message) -> Bool
fn idOf(message) -> Any
fn methodOf(message) -> String?
fn errorOf(message) -> RpcFailure?
```

Os builders não validam; `decode` é a fonte da validação. Regras: `jsonrpc == "2.0"`;
request tem `method` e `id` (`Int` ou `String`,
nunca `Float`/`null`); notification não tem `id`; resposta tem exatamente um de
`result`/`error` e `id` (`Int`, `String` ou `nil`); `params` é array ou objeto; `error` tem
`code: Int`, `message: String` e `data` opcional (qualquer valor JSON, exposto como
`RpcFailure.data`); batch (array no topo) é recusado com `-32600`, porque LSP
não usa. Códigos: `-32700` parse, `-32600` invalid request, `-32601` method not found,
`-32602` invalid params, `-32603` internal.

**`std.jsonrpc` e `std.json`:** `parseResult(text) -> JsonResult` com
`enum JsonResult { Ok(Any), Err(String) }` separa `null` de JSON malformado — sem isso não
dá para distinguir `-32700` de `-32600`. `parse` continua devolvendo `Any?` e é
implementado sobre `parseResult`; `isOk`/`value`/`error` existem porque um enum exportado
não pode ser nomeado na anotação de outro módulo.

**`std.framing`** — `Content-Length`, sem conhecer JSON:

```lox
type Reader = fn(Int) -> String?
class FrameFailure { val kind: String; val message: String }
fn readFrame(read: Reader) -> Result[String?, FrameFailure]   # Ok(nil) = EOF limpo
fn encodeFrame(text: String) -> String
fn readStdin(count: Int) -> String?
fn writeStdout(text: String) -> Nil
```

Contrato do `Reader`: devolve **até** `count` bytes, nunca parte um code point, `nil` só no
fim limpo e pode devolver `""` quando uma sequência parcial está pendente. Cabeçalho é
ASCII e lido **1 byte por vez** (cada byte é um code point; sem `peek` e sem misturar
`readLine`, que é indefinido no oráculo). O corpo pede exatamente `Content-Length` bytes.
Caps: 8 KiB de cabeçalho e 16 MiB de corpo. CRLF estrito; `Content-Length` obrigatório,
único, não negativo; `Content-Type` aceito e ignorado. `readStdin` normaliza o erro
"expects exactly N bytes" para `nil`, para o codec reportar `truncated` em vez de `read`;
UTF-8 inválido continua `read`. `writeStdout` usa `io.write`, que já flusha (ADR-0094) —
`print` nunca entra no caminho de protocolo.

**`std.documents`** — full sync, sem JSON:

```lox
class Document { val uri: String; val languageId: String; val version: Int; val text: String }
class DocumentError { val kind: String; val message: String }
class DocumentStore {
  fn open(uri, languageId, version, text) -> Result[Bool, DocumentError]
  fn change(uri, version, text) -> Result[Bool, DocumentError]
  fn close(uri) -> Result[Bool, DocumentError]
  fn get/text/version/languageId/has/uris/len
}
```

URI é opaca: sem percent-decoding e sem `file://` → path. `change` substitui o texto; range
é erro do adaptador que parseia a notificação, não do store. Versão estritamente crescente;
`uris()` ordenado. O `Bool` é o sucesso (`Ok(true)`): `Result[Nil, E]` era o gatilho do bug
de lowering corrigido, e `Nil` como payload de `Result` não é uma superfície que a stdlib
deva exigir.

### 4. Erros

`Result[T, E]` com `T` concreto; `Ok(nil)` no framing é EOF limpo, não erro. Exceção só do
`io.readUtf8` na borda, convertida em `FrameFailure` dentro de `readFrame`.

## Consequências

### Positivas

- O mesmo código roda no tree-walk e no LLVM; os três casos entram no diferencial (t3) e o
  `result_nil` no l6, com stdout byte a byte.
- O kernel agora tem um consumidor real de `io.readUtf8`/`io.flush`: o teste de transcrição
  prova framing com corpo multibyte, dois frames colados, EOF e truncamento.
- `std.json` ganhou uma distinção que faltava (`null` × inválido) e o backend deixou de
  quebrar em `Result[Nil, E]` — dois bugs de contrato fechados no caminho.
- Módulos independentes: MCP pode reusar `std.jsonrpc` com JSONL depois; DAP reusa o
  framing; qualquer ferramenta de editor reusa o store.

### Negativas / custos

- Três superfícies públicas novas (T3) a manter; a API é promessa de release.
- `std.framing` ainda não fala JSONL (MCP): exige leitura byte a byte ou `peek`; fica para
  quando houver consumidor em Loxia.
- `Result[Nil, E]` continua evitado por precaução, embora o lowering já aceite; o store usa
  `Bool` de sucesso.
- `RpcFailure.data` é `Any`: quem consome precisa estreitar com `is`/`as` antes de usar
  ([ADR-0144](0144-any-dinamico-exige-estreitamento.md)); o builder omite `data` quando é
  `nil`, então `data: null` explícito não é representável, e o accessor devolve o mesmo
  `nil` para ausência e para `null`.
- O harness de transcrição cobre o oráculo com stdin real; o adaptador no binário é coberto
  pelo teste de kernel existente e pelos goldens, não por um transcript nativo próprio.

### Neutras

- Nenhuma sintaxe nova, nenhuma primitiva nova, nenhum tipo novo.
- O LSP continua Python ([ADR-0090](0090-lsp-escopo-e-hospedagem.md)); estes módulos não
  prometem um servidor em Loxia.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Um `std/lsp` monolito | Mistura transporte, protocolo e estado; o nome acopla a um protocolo que pode não vingar; MCP/DAP não reusam. |
| `libs/` incubadora fora do bundle | Sem I1 e sem docs geradas; invisível para quem instala via pip; promoção depois custaria o mesmo. |
| Repositório separado | Sem registry, fora do CI e do diferencial, fricção para ~450 linhas. |
| Só exemplo/cookbook | Não reutilizável e apodrece; o harness já é o consumidor. |
| `Bytes`/`io.readSome` no kernel | Tipo novo e quarta leitura de stdio; o ADR-0094 já recusou e o `process.read` cobre o caso "até n". |
| `Result[Any, E]` | Bloqueado por `E3011`; `JsonResult` preserva a informação sem mexer no checker. |
| Envelopes dentro de `std.json` | JSON é RFC 8259; JSON-RPC é protocolo. Misturar incharia um módulo estável. |
| Framing dentro de `std.io` | `std.io` é casca do kernel; framing é protocolo e tem contrato próprio. |
| JSONL na v1 | Sem consumidor em Loxia hoje; `Content-Length` é o que a issue pede. |
| Incremental/`positionEncoding` no store | Exige o inverso de `utf16Column` e decisão UTF-16 × UTF-8; full sync casa com o ADR-0090. |
| Servidor LSP mínimo | Seria um brinquedo sem análise; a política de servidor fica fora da biblioteca. |

## Como verificar

- `uv run python -m tests.runner std` — goldens de `std_jsonrpc`, `std_framing`,
  `std_documents` e `std_json`.
- `uv run pytest tests/test_protocol_lox.py` — transcrição com stdin binário real.
- `uv run pytest -m backend -k "jsonrpc or framing or documents or result_nil"` — paridade
  byte a byte nos dois motores, incluindo `std_jsonrpc_data.lx` (campo `Any` em `L6`).
- `make stdlib-docs` e `make docs-index` — páginas geradas.
- `make check` — ruff, mypy, suíte e frescor de docs.

## Critério para revisitar

- Se o self-hosting chegar e um LSP em Loxia virar objetivo, `std/lsp` nasce fino sobre os
  três, com `positionEncoding` explícito e incremental como issue própria.
- Se MCP-em-Lox ou DAP aparecer, `std.framing` ganha o codec JSONL com o mesmo `Reader`.
- Se um segundo consumidor real não aparecer até o self-hosting, a promoção a T3 é revista:
  módulo sem uso sai sem quebrar os outros dois.
