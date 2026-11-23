# Native runtime (C)

The C runtime behind `--emit`. It implements the parts of the language the LLVM IR
cannot express directly: boxed values, strings, containers, classes/interfaces,
exceptions, panics, the call stack and the host kernel.

The tree-walk interpreter is the specification. Every observable behavior here must
match it byte for byte (stdout, stderr, exit code) inside the declared corpus. When in
doubt, read `loxia_core/execution/interpreter.py` first and mirror it.

## Where to look

| Unit | Owns | Main symbols | Called from |
| --- | --- | --- | --- |
| [`lox_runtime.h`](lox_runtime.h) | Shared types, limits, prototypes and the ABI contract | `LoxStr`, `LoxValue`, `LoxFrame`, `LoxTryFrame` | Every unit |
| [`core.c`](core.c) | Startup, Boehm GC, call stack, panics, try/throw | `lox_init`, `lox_stack_*`, `lox_alloc*`, `lox_panic*`, `lox_throw*` | Generated `main`, every function, panic sites |
| [`objects.c`](objects.c) | Class/interface identity, `is`/`as` matcher | `lox_is_instance`, `lox_interface_method`, `lox_type_matches_*` | `lower_class_codegen.py`, `lower_instances.py`, `lower_model.py` |
| [`strings.c`](strings.c) | `String`, UTF-8, `print`/`str`/`repr`, container formatting | `lox_str_*`, `lox_print_*`, `format_*`, `buffer_*` | `lower_strings.py`, containers |
| [`containers.c`](containers.c) | `Range`, `List`, `Map`, tuple, enum, structural equality | `lox_range_*`, `lox_list_*`, `lox_map_*`, `lox_tuple_*`, `lox_enum_*` | `lower_range.py`, `lower_containers.py`, equality paths |
| [`numeric.c`](numeric.c) | Arithmetic guards, `math.*`, numeric parsing | `lox_int_*`, `lox_float_*`, `lox_math_*`, `lox_parse_*` | `lower.py`, `lower_math.py`, `lower_optionals.py` |
| [`kernel.c`](kernel.c) | Host primitives: strings, stdio, files, env, time | `lox_substr`, `lox_join`, `lox_io_*`, `lox_fs_*`, `lox_os_*`, `lox_time_*` | Generated code, `std/fs.lx`, `std/io.lx` |
| [`proc.c`](proc.c) | Processes, pipes and `poll(2)` | `lox_proc_*` | `std/proc.lx` |
| [`kernel_gen.h`](kernel_gen.h) | **Generated** ABI for host primitives | `lox_*` declarations | Included by `kernel.c` |
| [`gen_kernel.py`](gen_kernel.py) | Regenerates `kernel_gen.h` | `--write` / `--check` | `make primitives` |

Generated-code side of the contract lives in `loxia_core/backend/`:
`lower_model.py` mirrors the layouts, `lower_strings.py` emits string calls,
`lower_class_codegen.py` emits descriptor/interface data and `lower_enums.py` emits
`match` helpers.

## Reading order

1. [`lox_runtime.h`](lox_runtime.h) — layouts, limits, tag table and the unit map.
2. [`core.c`](core.c) — how a binary starts, allocates, tracks frames and fails.
3. [`strings.c`](strings.c) — the value most code paths touch.
4. [`containers.c`](containers.c) — list/map/tuple/enum and `==`.
5. [`objects.c`](objects.c) — nominal classes/interfaces and `is`/`as`.
6. [`numeric.c`](numeric.c) — defined-edge arithmetic and parsing.
7. [`kernel.c`](kernel.c) / [`proc.c`](proc.c) — the host.

## ABI at a glance

`LoxValue` is `{i64 tag, i64 payload}`. Float stores its bit pattern in `payload`.

| Tag | Value | Payload |
| --- | --- | --- |
| 0 | `nil` | unused |
| 1 | `Int` | i64 |
| 2 | `Float` | f64 bit pattern |
| 3 | `Bool` | 0/1 |
| 4 | `String` | `LoxStr *` |
| 5 | Class | `LoxClassDescRuntime *` |
| 6 | Instance | instance pointer |
| 7 | Function/closure | closure pointer or display pointer (dynamic path) |
| 8 | `Range` | `LoxRange *` |
| 9 | `List` | `LoxList *` |
| 10 | `Map` | `LoxMap *` |
| 11 | Tuple | `LoxTuple *` |
| 12 | Enum | `LoxEnumValue *` |

`LoxStr` is `{byte_len, cp_len, flat, cp_offsets, hash, left, right}`. A leaf has
`flat` pointing to UTF-8 bytes; a concatenation node has `flat == NULL` and
`left`/`right`, and `lox_str_bytes` flattens it on first observation (cached).
`cp_len` counts code points, `cp_offsets` is a lazy index allocated for strings
with at least 64 code points, and `hash` caches FNV-1a for map keys. Public
indices are code points, never bytes.

A function uses `(i8* env, params...)`. A closure is `{fnptr, env, display}`. Class
descriptors start with `{super, id, name, vtable, ...}`; an instance stores its
descriptor in the first field, then a field bitmap and i64 slots. See
`lower_model.py` and ADR-0048 for the full instance layout.

Primitives declared with `site=True` in `loxia_core/execution/primitives.py` receive
`(int32_t line, int32_t column)` as the last two arguments. Pass them to `lox_panic`
so a runtime error points at the Lox call site.

## Invariants

- **GC only.** Boehm is the allocator; never call `free`. Use `lox_alloc` for blocks
  with pointers and `lox_alloc_atomic` for pure bytes.
- **Bounded stack.** `lox_call_depth` never exceeds `LOX_MAX_CALL_DEPTH`; overflow is
  R1015 before the frame is written.
- **Deterministic output.** No address, PID, timestamp, absolute path or hash order in
  output (I3). Container order is insertion order; `fs.listDir` is byte-sorted.
- **Tree-walk parity.** Formatting, panic messages, exit codes and trace shape must
  match the interpreter (I1). Change both engines and add a differential golden.
- **Generated header.** `kernel_gen.h` is produced from the primitive table; do not
  edit it by hand. `make primitives` writes it, `tests/test_primitives_gen.py` checks it.
- **Ambient is outside I1.** Files, stdin, environment, clock and processes are
  ambient; tests use fixed inputs and never print absolute paths.
- **Panic vs exception.** `lox_panic*` prints and exits 70 unless a try frame is active,
  in which case it becomes a catchable `RuntimeError`. `lox_throw*` unwinds to the
  current try frame (or reports an unhandled exception and exits 70).

## Common tasks

### Add a host primitive

1. Add the entry to `PRIMITIVES` in `loxia_core/execution/primitives.py` (`lox` name,
   C symbol, `params`, `result`, `site`).
2. Run `make primitives` to regenerate `kernel_gen.h`.
3. Implement the exact signature in `kernel.c` (or `proc.c` for process primitives).
4. Add a typed wrapper in `std/*.lx` and a golden/differential case.
5. Run the backend tests; a signature mismatch fails at compile time.

### Find where a symbol is emitted

```bash
rg 'lox_str_concat' loxia_core/backend runtime
uv run main.py --emit=ll prog.lx   # inspect the IR
```

### Debug a native mismatch

1. Reproduce with the smallest `.lx` input.
2. Run it with the tree-walk (`uv run main.py file.lx`) and with the native binary.
3. Compare stdout, stderr and exit code, not just the first line.
4. Locate the runtime symbol from the emitted call; compare the C path with the
   interpreter method that implements the same operation.
5. Add the case to `tests/corpus_manifest.py` so the differential suite polices it.

### Change a value layout

Layouts are shared by generated code and C. Update `runtime/lox_runtime.h`,
`loxia_core/backend/lower_model.py`, every accessor in `strings.c`/`containers.c` and
the formatter/matcher paths. Then rebuild the backend suite.

## Known rough edges

These are current behaviors, not endorsements. Document or fix them with a golden
case; do not change them silently.

- `lox_str_from_range` always prints `..`, even for inclusive ranges; `lox_print_range`
  uses the correct `..=`. No differential case covers `str(..=)` yet.
- `lox_io_read_file` and `lox_io_read_line` do not validate UTF-8, while the tree-walk
  rejects invalid input. `io.readUtf8` is the validating reader.
- `lox_enum_variant` is unused; `match` compares variants by name through
  `lox_enum_variant_index`.
- The type cache is keyed by string pointer identity, so it assumes the string is an
  immutable global emitted by the lowering.

## ADRs

- [ADR-0031](../../docs/adr/0031-backend-nativo.md) — native backend
- [ADR-0046](../../docs/adr/0046-closures-celulas-l4.md) — closures and cells
- [ADR-0048](../../docs/adr/0048-abi-classes-l5.md) — class ABI
- [ADR-0062](../../docs/adr/0062-l6-excecoes-unwinding.md) — exceptions
- [ADR-0071](../../docs/adr/0071-primitivas-de-runtime.md) — kernel primitives
- [ADR-0074](../../docs/adr/0074-gc-boehm-e-contrato-de-memoria.md) — GC and memory
- [ADR-0075](../../docs/adr/0075-diagnosticos-estruturados.md) — structured diagnostics
- [ADR-0077](../../docs/adr/0077-limite-de-pilha.md) — stack limit
- [ADR-0080](../../docs/adr/0080-interfaces-nominais-implementacao.md) — interfaces
- [ADR-0087](../../docs/adr/0087-heap-cap-e-self-hosting.md) — heap cap
- [ADR-0089](../../docs/adr/0089-stack-trace-de-runtime.md) — stack trace
- [ADR-0094](../../docs/adr/0094-kernel-io-flush-e-read-utf8.md) — I/O flush and readUtf8
- [ADR-0095](../../docs/adr/0095-processos-streams-poll.md) — processes and poll
