---
title: Next steps
description: Where to go after the tour.
---

You have the shape of Loxia. The next step depends on what you want to build.

## The standard library

The [standard library reference](../../stdlib/) is generated from the `///` documentation
in `std/*.lx`. Start with:

- `std.json` — RFC 8259 JSON with insertion-ordered objects.
- `std.fmt` — formatting and templates.
- `std.fs`, `std.io`, `std.proc` — ambient file, stdin/stdout and process APIs.
- `std.lists`, `std.maps`, `std.sets` — collection combinators.
- `std.property` — property-based testing with generators and shrinking.

## The reference

The [reference](../../reference/) is the normative description of the language. It is
currently in Portuguese; the English translation is tracked separately.

## The native backend

`loxia build program.lx --emit=exe -o program` compiles with LLVM. The backend is tested
against the interpreter for the declared corpus, byte for byte. See the
[guarantees](../../pt/reference/guarantees/) for the exact contract.

## Contributing

The [contribution guide](https://github.com/loxia-lang/loxia/blob/main/CONTRIBUTING.md)
explains the gates for features and syntax, the commit convention and the DCO. The
[roadmap](https://github.com/loxia-lang/loxia/blob/main/TODO.md) records what is in scope.
