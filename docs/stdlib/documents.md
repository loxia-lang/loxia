---
title: std.documents
sources:
  - std/documents.lx
  - loxia/docgen.py
---

# std.documents

Full-sync document store: opaque URIs, versions and text, without JSON or I/O.

## API

## Classes

### `class Document`

One open document and its last known version.

#### `val uri: String`

Opaque document identifier, usually a `file://` URI.

#### `val languageId: String`

Editor language id, e.g. `loxia`.

#### `val version: Int`

Monotonically increasing version supplied by the client.

#### `val text: String`

Full text of the document.

#### `fn init(uri: String, languageId: String, version: Int, text: String)`

Creates a document snapshot.

### `class DocumentError`

Why a store operation failed; `kind` is stable and `message` is for humans.

Kinds: `already_open` (opening an open URI), `not_open` (changing/closing an unknown
URI), `stale_version` (change not newer than the stored version), `invalid_version`
(negative version on open).

#### `val kind: String`

Stable machine-readable kind.

#### `val message: String`

Human-readable reason; a fixed message plus the caller-provided URI.

#### `fn init(kind: String, message: String)`

Creates an error with an explicit kind and message.

### `class DocumentStore`

Full-sync store keyed by opaque URI.

`change` replaces the whole text: range-based changes are not representable here and
belong to the adapter that parses the notification. Versions must increase on every
change; a stale version is rejected instead of silently overwriting newer text.

#### `var docs: Map[String, Document]`

Open documents keyed by URI, in insertion order.

#### `fn init()`

Creates an empty store.

#### `fn open(uri: String, languageId: String, version: Int, text: String) -> Result[Bool, DocumentError]`

Registers a document; fails when the URI is already open or the version is negative.

#### `fn change(uri: String, version: Int, text: String) -> Result[Bool, DocumentError]`

Replaces the full text of an open document.

`version` must be strictly greater than the stored one; otherwise the change is
rejected and the stored text is left untouched.

#### `fn close(uri: String) -> Result[Bool, DocumentError]`

Removes an open document; fails when the URI is unknown.

#### `fn get(uri: String) -> Document | Nil`

Returns the document snapshot, or `nil` when the URI is not open.

#### `fn text(uri: String) -> String | Nil`

Returns the current text, or `nil` when the URI is not open.

#### `fn version(uri: String) -> Int | Nil`

Returns the last version, or `nil` when the URI is not open.

#### `fn languageId(uri: String) -> String | Nil`

Returns the language id, or `nil` when the URI is not open.

#### `fn has(uri: String) -> Bool`

Returns `true` when the URI is open.

#### `fn uris() -> List[String]`

Returns the open URIs in ascending order, independent of insertion order.

#### `fn len() -> Int`

Returns the number of open documents.
