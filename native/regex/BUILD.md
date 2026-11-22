# native/regex — Rust regex engine (C ABI)

Engine behind Loxia's regex ([ADR-0131](../../docs/adr/0131-regex-motor-rust-dois-modos.md)).
It exposes a small, stable C ABI (`include/lox_regex.h`) used by the C runtime and by the
Python interpreter through `ctypes`. It knows nothing about Loxia values: strings cross as
UTF-8 bytes and offsets are converted here.

## Modes

| Mode | Crate | Guarantee |
| --- | --- | --- |
| `LOXR_MODE_LINEAR` (default) | [`regex`](https://docs.rs/regex) | linear time, `size_limit` bounded |
| `LOXR_MODE_FULL` | [`fancy-regex`](https://docs.rs/fancy-regex) | backtracking with `backtrack_limit` (1,000,000 steps) |

Regular patterns in `FULL` mode are delegated by `fancy-regex` to the linear engine, so they
stay linear; the backtracking limit only matters for backreferences and lookaround.

## ABI

`include/lox_regex.h` is the contract; the constants are mirrored in `src/lib.rs`.

- `loxr_abi_version()` — the loader refuses a mismatch.
- `loxr_compile(pattern, len, flags, mode, out_handle, out_offset)` — 1-based handle on
  success, `LOXR_ERR_COMPILE` plus the byte offset of the first syntax error on a syntax
  error (`0` for `"("`, `1` for `"a(b"` in both modes; `-1` when unknown), or
  `LOXR_ERR_TOO_BIG` when a per-program compiled-memory limit is hit.
- `loxr_match(handle, subject, len, start, out_spans, capacity)` — `start` in code points;
  writes `(start, end)` pairs in code points and returns how many `int64` were written, or
  `LOXR_NO_MATCH`.
- `loxr_free(handle)` — idempotent, safe on an unknown handle.

Flags: `CASELESS`, `MULTILINE`, `DOTALL`, `EXTENDED`.

## Safety and determinism

- Every `extern "C"` entry point is wrapped in `catch_unwind`; a Rust panic becomes
  `LOXR_ERR_PANIC`, never an abort. The release profile keeps `panic = "unwind"`.
- The panic **hook is silenced at init**: without it, `catch_unwind` still lets the default
  hook print `thread ... panicked` on stderr, which is an I1 channel.
- Handle table: 1-based, idempotent `free`, a free list for reuse, cap of 4096 live patterns
  (`LOXR_ERR_HANDLES`). No finalizer.
- Limits are constants, not settings: `backtrack_limit = 1_000_000`, `size_limit = 10 MiB`
  (linear and delegated sub-regexes), `delegate_dfa_size_limit = 2 MiB` and
  `max_prog_size = 100_000` instructions (full). Changing them changes behavior and needs a
  spec/test update.
- Rust allocations are **outside** the Boehm heap cap of the binary (ADR-0131 §2): the
  contract is per compiled program, not a total byte budget across handles. Closing handles
  is the way to release memory.

## Build and test

The toolchain is pinned in `rust-toolchain.toml` (1.93.1). Crates are vendored
(`vendor/`), so builds never touch the network:

```bash
cargo build --release --locked --offline
cargo test  --release --locked --offline
```

Measured on 2026-11-22 (Linux x86_64, rustc 1.93.1): clean build **~14 s** with
`lto = "fat"`; `liblox_regex.so` **2.3 MB**; `liblox_regex.a` **11.0 MB**; a binary linked
from the staticlib **~1.7 MB stripped** (a binary without regex is ~84 KB).

## Vendoring and upgrade

- `cargo vendor vendor` writes the crates; `.cargo/config.toml` replaces crates.io with that
  directory; `Cargo.lock` is committed.
- Upgrade: `cargo update -p <crate>`, `cargo vendor vendor`, review the lock diff, rebuild
  offline, and note it in `CHANGELOG.md` when it changes Unicode tables or semantics.
- Vendored crates keep their own license files under `vendor/<crate>/` (all MIT/Apache-2.0);
  `tests/test_license_headers.py` excludes the `vendor/` prefix on purpose.
- `vendor/` is upstream code: `.gitattributes` marks it `-diff linguist-vendored`, so the
  PR lists the files instead of ~230k lines and reviewers check the versions in `Cargo.lock`.

## Not in this crate

The public Lox API (`bundled/regex.lx`), the `regex_engine` primitives, the build cache and
the conditional link live in the main tree. This crate is only the engine.
