# ADR-0078 — O nome é Loxia, a extensão é `.lx` e o prelúdio não carrega a marca

- **Status:** accepted (implementado)
- **Data:** 2026-11-15
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0014](0014-identidade-e-invariantes.md) (identidade),
  [ADR-0026](0026-freeze-1.0.md) (freeze da 1.0),
  [ADR-0042](0042-excecoes.md) e [ADR-0062](0062-l6-excecoes-unwinding.md) (exceções),
  [ADR-0072](0072-stdlib-batteries.md) (batteries),
  [`../../TODO.md`](../../TODO.md) §14 (publicação), [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** `loxia/` (pacote do CLI), `loxia_core/loader/loader.py` (`SOURCE_SUFFIX`),
  `loxia_core/execution/prelude.py`, `loxia_core/semantics/checker.py`,
  `runtime/core.c` (`lox_throw`), `tests/cases/*.lx`

## Contexto

A linguagem nasceu como "PyLox" com extensão `.lox`, herdando o nome do Lox do livro
(Crafting Interpreters). O nome e a extensão eram **nomes de trabalho**, declarados em
aberto no [ADR-0014](0014-identidade-e-invariantes.md) e no [ADR-0026](0026-freeze-1.0.md),
com a decisão pendente no `TODO.md` §11 item 2.

Três forças empurravam para longe do nome provisório:

1. **"PyLox" diz o que o projeto era, não o que ele é.** Descreve um porte do livro em
   Python; a linguagem hoje tem identidade própria (sintaxe, checker gradual, backend
   LLVM) e a promessa do [ADR-0014](0014-identidade-e-invariantes.md) — I1–I4.
2. **`.lox` não é registrado no GitHub Linguist.** Nem `.lox` nem `Lox` existem no
   `languages.yml`: hoje os fontes aparecem como texto puro de qualquer forma, então trocar
   a extensão não custa highlighting nenhum.
3. **O prelúdio carregava a marca no código do usuário.** `except LoxRuntimeError as e`
   expõe o nome da linguagem no programa do usuário; um prelúdio não deve ter o nome da
   linguagem no nome das suas classes (como Python não tem `PythonError`).

## Decisão

1. **Nome:** a linguagem se chama **Loxia**. "Lox" permanece o nome do *dialeto do livro*
   e do oráculo normativo — a linhagem continua declarada, não apagada.
2. **Extensão:** `.lx` é a extensão canônica dos fontes. `SOURCE_SUFFIX` em
   `loxia_core/loader/loader.py` é o único ponto que a conhece; `import a.b` resolve `a/b.lx`.
   O CLI continua aceitando qualquer nome de arquivo (não valida extensão), então scripts
   antigos rodam; só `import` deixou de resolver `.lox`.
3. **Pacote e comando:** o pacote Python é `loxia`, o comando é `loxia`
   (`python -m loxia`), e `main.py` mantém o alias `Lox = Loxia` para quem importa o driver.
4. **Prelúdio sem marca:** a classe de erro de runtime embutida passa a se chamar
   **`RuntimeError`** (era `LoxRuntimeError`); `Exception` continua a base. A classe
   **Python** `loxia_core/diagnostics/errors.py::LoxRuntimeError` mantém o nome: é herança de
   nomenclatura do livro, não superfície da linguagem.
5. **`Lox*` no código é herança e fica.** `LoxClass`, `LoxInstance`, `LoxFunction`,
   `LoxCallable`, `LoxList`, `LoxMap`, `LoxTuple`, `LoxRange`, `LoxExceptionValue` etc. são
   os nomes do livro; renomeá-los é churn sem ganho observável. O prefixo `lox.` dos
   símbolos do backend (`lox.ctor.*`) é **ABI do runtime** e também fica.

Regra de vocabulário, agora normativa: **Lox** = dialeto do livro e
oráculo; **Loxia** = a linguagem; **`Lox*`/`lox.`** = herança do livro no código.

## Consequências

### Positivas

- Nome próprio, buscável e sem colisão relevante: não há linguagem `Loxia` no Linguist;
  `Lume` (SSG do Deno + preprint) e `Lux` (LuxLang, Lisp na JVM) foram descartados por
  colisão; `.lx` está livre no Linguist (`.lex`, `.ll` e `.ly` estão ocupados).
- O programa do usuário não menciona mais o nome da linguagem em `except`.
- A migração foi mecânica e não tocou semântica: I1–I4 seguem intactos (nada de observável
  mudou além de nomes e da resolução de `import`).

### Negativas / custos

- Renomear arquivos invalida links antigos fora do repositório e `import` de módulos
  `.lox` escritos antes da troca. É aceitável por ser pré-publicação.
- O repositório passa a ter três grafias conviventes (`Loxia`, `Lox`, `lox.`). A regra de
  vocabulário existe exatamente para que isso seja lido como camadas, não como descuido.
- ADRs antigos citam `LoxRuntimeError`/`.lox` como fatos da época; eles são históricos e
  recebem nota de atualização no cabeçalho em vez de reescrita.

### Neutras

- O GitHub namespace `loxia` já está tomado (usuário dormente, 0 repositórios); a
  organização do projeto é `loxia-lang`. O PyPI `loxia` está livre.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| **Lux** (variante de Lox + luz) | Colide com a [Lux/LuxLang](https://docs.lux-lang.dev/docs/spec), linguagem documentada, e com a marca "Lux" em geral. |
| **Lume** (luz; "vir a lume") | Já é o SSG do Deno e um preprint de linguagem; bonito, porém ocupado. |
| **Patch/Quilt/Scrap** (colcha de retalhos) | Contam a *origem* (montagem por agentes), não a promessa; "retalho" sugere derivado, o oposto do ADR-0014. |
| **Chorus/Ensemble/Relay** (orquestração) | Descrevem o processo de desenvolvimento, invisível ao usuário, e são nomes concorridos em software. |
| **PyLox/`Loxley`** | Mantêm "Lox" inteiro no nome, lendo como "mais uma implementação do livro". |
| **`LoxiaError`** em vez de `RuntimeError` | Rebrandaria a marca em vez de removê-la do prelúdio; `RuntimeError` diz o que é e não envelhece com o nome. |

## Como verificar

- `make check` verde, incluindo `tests/test_docs_links.py` (links para `.lx`/`loxia/`) e
  `tests/test_docs_consistency.py` (título do README = `# Loxia`, versão do pacote).
- `uv run main.py --version` → `loxia 1.0.0`; `uv run python -m loxia --version` idem.
- `tests/cases/exceptions.lx` e `std_asserts.lx` provam `except RuntimeError`;
  `tests/test_interpreter.py` prova `Unhandled exception: RuntimeError: ...`.
- `tests/test_cli.py` prova que um script com extensão arbitrária ainda roda (o CLI não
  valida extensão) — a compatibilidade declarada na decisão 2.
- Revisitar se: a linguagem for publicada e precisar de entrada no Linguist (aí a extensão
  vira contrato público), ou se o prefixo `lox.` da ABI incomodar em `--emit=ll`.

## Referências

- [github-linguist/languages.yml](https://github.com/github-linguist/linguist/blob/main/lib/linguist/languages.yml)
- [Lux — especificação](https://docs.lux-lang.dev/docs/spec) (alternativa descartada)
- [`../../docs/decisoes.md`](../decisoes.md) — resumo executivo
