# Security Policy

Loxia runs untrusted programs by design when you invoke `loxia run`; that is not a
vulnerability. This policy covers defects in the implementation and its supply chain.

## Supported versions

The latest 1.x release receives security fixes. Older 1.x releases are supported on a
best-effort basis; report the version from `loxia --version`.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private vulnerability reporting:

- Go to the repository's **Security** tab.
- Choose **Report a vulnerability**.
- Open the form at
  <https://github.com/loxia-lang/loxia/security/advisories/new>.
- Describe the impact, the affected version, the command you ran and a minimal `.lx`
  reproduction. If the report is about the native backend, include the target and whether
  `--emit=exe` was used.

Only the maintainers can see the report. There is no email-based reporting channel.

If the report is about the **Code of Conduct**, use the same form with `[conduct]` at the
start of the title; see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Do not use the
`[conduct]` prefix for security reports.

If the issue is about the maintainer, or about abuse on GitHub itself, use
[GitHub's Report Abuse form](https://github.com/contact/report-abuse).

## What is in scope

- A crash, panic, abort or segmentation fault in the interpreter or in generated code
  where the documented behavior should be an error or a normal exit.
- A miscompilation that violates the I1 contract: the same program produces different
  stdout, stderr or exit code in the tree-walk and in the native backend for the declared
  corpus.
- A sandbox escape or path traversal in the module loader, the LSP, `loxia run` or the
  `--emit` driver.
- A denial of service that bypasses the documented budgets: 10,000 calls / 64 MiB stack,
  512 MiB default heap, `--timeout`, or the process/stream limits.
- A vulnerability in a dependency that ships in the wheel or sdist (Python packages,
  `libgc` link, C runtime).
- Leaked secrets, tokens or private paths in a release artifact or in CI logs.

## Out of scope

- Semantic disagreements, missing features, performance, diagnostics wording or docs.
- An error that is supposed to be fatal (`exit 70`) or a checker rejection.
- Running untrusted Loxia code: `loxia run` and `--emit=exe` execute code by design; use an
  external sandbox if you need one.
- Reports that require a malicious local user with write access to the project files.
- Vulnerabilities in third-party tools (editor, OS, GitHub) that are not caused by Loxia.

## What to expect

- Acknowledgment within 3 business days.
- Triage and a mitigation plan after the report is reproduced.
- A GitHub Security Advisory and credit when the fix is released, unless you ask to remain
  anonymous.
- No bug bounty is offered.

## Safe harbor

We will not pursue legal action for good-faith research that follows this policy, avoids
privacy violations and data destruction, and gives us reasonable time to fix the issue
before public disclosure.

## Conduct

Conduct reports are not security reports. They use the same private form with `[conduct]`
in the title; the maintainers handle them under the
[Code of Conduct](CODE_OF_CONDUCT.md).
