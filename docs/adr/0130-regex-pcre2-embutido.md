# ADR-0130 — Regex: PCRE2 embutido, um só motor para interpretador e binário

- **Status:** accepted (decisão; implementação pendente)
- **Data:** 2026-11-22
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0072](0072-stdlib-batteries.md) (não-objetivo reaberto),
  [ADR-0126](0126-modulo-nativo-embutido-sqlite.md) (camada de módulo nativo),
  [ADR-0128](0128-contrato-de-motores.md) (core/ambient/native-only),
  [ADR-0123](0123-orcamento-do-kernel-por-grupo.md) (orçamento),
  [ADR-0071](0071-primitivas-de-runtime.md) (sem FFI genérica),
  [ADR-0075](0075-diagnosticos-estruturados.md) (catálogo de códigos),
  [ADR-0077](0077-limite-de-pilha.md) / [ADR-0087](0087-heap-cap-e-self-hosting.md) (limites),
  [ADR-0035](0035-strings-texto.md) (UTF-8 por code point),
  [ADR-0066](0066-orcamento-e-gate-sintatico.md) (gate sintático),
  [#114](https://github.com/loxia-lang/loxia/issues/114) (issue de decisão)
- **Implementação:** `vendor/pcre2/`, `runtime/pcre_shim.c`,
  `loxia_core/execution/pcre_runtime.py`, `loxia_core/execution/primitives.py`
  (`NATIVE_MODULE_PRIMITIVES` e `NATIVE_MODULE_BUDGET`), `loxia_core/backend/driver.py`
  (`runtime_units(imports)`), `bundled/regex.lx`, `loxia_core/diagnostics/codes.py`
  (`E3022`), `tests/cases/std_regex/*.lx`, `tests/test_layers.py`,
  `tests/test_stdlib_docs.py`

## Contexto

Os checks de CI do projeto (Conventional Commits, título de PR, DCO, índice e links da
documentação) são Python em `tools/` e são o primeiro programa real com que vale a pena
dogfoodar a linguagem. Regex é o bloqueio concreto: [conventional.py](../../tools/conventional.py)
precisa de grupo nomeado, grupo não-capturante, classe com intervalo, `\S` e alternância;
[docs_index.py](../../tools/docs_index.py) precisa de `{n,m}` e `+?` lazy.

Três decisões já registradas delimitam o espaço:

- [ADR-0072](0072-stdlib-batteries.md) lista regex como **não-objetivo** da stdlib. A
  justificativa era "custo no kernel, risco ao I3 e nenhum programa real usa". O consumidor
  real agora existe; este ADR substitui **apenas** a linha de regex, não as de cripto, rede,
  async, timezone e i18n.
- [ADR-0126](0126-modulo-nativo-embutido-sqlite.md) define a camada de módulo nativo
  embutido (vendor pinado, `import` opt-in, link condicional, orçamento próprio), aceita e
  **não implementada**: não há `vendor/`, não há `bundled/` e `RUNTIME_NAMES` ainda é uma
  tupla fixa em [driver.py](../../loxia_core/backend/driver.py).
- [ADR-0128](0128-contrato-de-motores.md) define as camadas `core`, `ambient` e
  `native-only`, com recusa em compile-time via `E3021`.

Requisitos do dono do projeto, em ordem: **completo** (não um subconjunto de brinquedo:
backrefs, lookaround, grupos nomeados, lazy/possessivo, atômico, condicionais, `\p{...}`);
**Unicode completo**; **rápido desde o início**; **determinístico**.

A medição fecha a porta do motor em Lox: uma varredura de caractere no tree-walk faz
**222 mil visitas em 1,34 s ≈ 6 µs por visita** (~165 mil chars/s). Um Pike VM de ~20 estados
sobre um arquivo de 10 KB custa ~4 s; sobre um título de 60 chars, ~20–30 ms. Isso não é
"performático desde o início" e não cobre varredura de conteúdo.

Escrever o motor também não fecha: semântica PCRE é dezenas de milhares de linhas mais
tabelas Unicode mais JIT. O `re` do CPython é exatamente essa arquitetura (`re._parser` →
opcodes → VM de backtracking em `_sre.c`) e **não é PCRE**: não tem `\p{...}`, `\K`, `\G`,
recursão, branch reset, e o lookbehind é de largura fixa. Adotá-lo como espelho caparia a
feature no ponto que o requisito proíbe.

## Decisão

**Um motor PCRE2 vendorizado, usado pelo interpretador (via `ctypes`) e pelo binário (link
estático), com API de alto nível em `bundled/regex.lx`.**

### 1. Motor: PCRE2, pinado

| Requisito | PCRE2 |
| --- | --- |
| backref/lookaround/atômico/possessivo/condicional | sim |
| `\p{...}` e classes Unicode (UCP) | sim |
| performance | C, JIT opcional |
| licença e forma | BSD-3, vendorizável, sem servidor |

Flags fixas: `PCRE2_UTF | PCRE2_UCP`, `PCRE2_NO_UTF_CHECK` no match (as `String` da linguagem
são UTF-8 válido por construção, [ADR-0035](0035-strings-texto.md)). **JIT desligado na v1**:
o ganho não paga a superfície de memória executável e de plataforma; ligar depois é uma flag
no mesmo shim. Nada de descoberta de ambiente (sem `pkg-config`, sem lib do sistema).

### 2. Um motor nos dois caminhos

| Caminho | Como fala com o PCRE2 |
| --- | --- |
| interpretador (Python) | `ctypes` no `pcre_shim` construído sob demanda |
| binário (`--emit=exe`) | o mesmo `pcre_shim.c` linkado estaticamente pelo backend |

O shim é a única fronteira: expõe um ABI C mínimo, converte offset de byte para code point
num lugar só e não conhece a linguagem. Os dois caminhos usam **a mesma versão vendorizada**,
então não há drift de tabela Unicode nem de semântica entre `run` e `--emit=exe` — é o que
sustenta a classificação `core` (I1).

O custo é explícito: o primeiro `import regex` no interpretador precisa de `cc` e paga um
build (ordem de segundos), cacheado por `(versão do vendor, hash do shim, cc, flags,
plataforma)` em `$TMPDIR/loxia-build-<uid>/regex-<hash>/`, com `LOX_BUILD_CACHE` isolando o
cache. Sem `cc`, o `run` recusa antes de executar com diagnóstico dedicado (ver §4).

### 3. Camada e superfície

| Camada | Nome | O que é |
| --- | --- | --- |
| namespace primitivo | `pcre2` | espelho da ABI: `compile(pattern, flags) -> Int`, `match(handle, subject, start) -> List[Int]?`, `free(handle)` |
| módulo público | `bundled/regex.lx` | `Regex`, `Match`, `RegexError`; `compile`, `isMatch`, `find`, `findAll`, `replace`, `replaceAll`, `split` |

- **Fora de `std/`**: `std` é Lox puro e não importa módulo nativo
  ([ADR-0126 §1](0126-modulo-nativo-embutido-sqlite.md)). O import é `import regex`, como
  `import sqlite`.
- **Orçamento próprio**: 3 primitivas, teto 4 (`NATIVE_MODULE_BUDGET["pcre2"] = 4`), fora
  dos 40 do kernel ([ADR-0123](0123-orcamento-do-kernel-por-grupo.md)).
- **Handles** `Int` 1-based, `free` idempotente, uso depois de fechar é `RuntimeError`, sem
  finalizer (Boehm não é determinístico). O handle guarda o `pcre2_code` compilado.
- **Compilação** devolve `Result[Regex, RegexError]`: erro de sintaxe é falha esperada e
  carrega a mensagem e o offset do PCRE2 (não entra no I3 como texto de contrato).
- **Match** devolve `Match?`; `nil` é "não casou". Estouro de `match_limit`/`depth_limit` é
  `RuntimeError` — exaustão de recurso, não ausência de match (mesmo padrão de OOM).
- **Substituição** (`$1`, `${name}`) é expandida em Lox. **Sem callback C→Lox na v1**; o
  guarda de `setjmp` do [ADR-0126 §6.1](0126-modulo-nativo-embutido-sqlite.md) fica para
  quando houver consumidor.
- **`findAll`** avança um code point depois de match vazio, para não repetir para sempre; a
  regra vive no Lox, então vale igual nos dois motores.

### 4. Classificação e a recusa por falta de toolchain

`regex`/`pcre2` são **`core`**: mesma semântica nos dois motores, corpus diferencial. A
ausência de `cc` não é divergência semântica — é indisponibilidade de host, como o link sem
`libgc`. Ela vira diagnóstico próprio, **`E3022`** (faixa `E3xxx`, exit 65, antes de
executar): "`regex` requires the C toolchain (cc) to build its runtime; install cc or build
with `--emit=exe`." `check` continua agnóstico de motor; `capabilities --json` publica
`layer: core` e `requires: ["cc"]`.

O `E3021` continua reservado para o que é `native-only` de verdade; este ADR não cria
capacidade `native-only`.

### 5. Determinismo, limites e offsets

- Sem locale em nenhum ponto: classes e `\p{...}` vêm das tabelas do PCRE2 vendorizado, não
  de `LC_*`. O pin do vendor é o pin das tabelas Unicode.
- `match_limit = 1_000_000` e `depth_limit = 10_000`, fixos no shim (calibrar contra o
  corpus na implementação; mudar exige spec + teste). Padrão patológico — `(a+)+$` sobre
  `"aaaa...b"` — devolve erro estável em tempo e memória limitados, nunca estouro de C
  stack.
- Offsets devolvidos são **code points**, convertidos no shim a partir dos bytes UTF-8 do
  PCRE2; `run` e binário usam a mesma conversão.

### 6. Vendor, CVE e upgrade

`vendor/pcre2/` recebe a release pinada, `VERSION`, SHA-256 no repositório e nota no
`CHANGELOG.md`. Atualização por release de segurança ou por tabela Unicode nova; o lock de
pacote não se aplica (é código do toolchain). O ciclo de CVE passa a ser nosso — o mesmo
trade-off aceito para SQLite, com um vendor muito menor.

### 7. Link condicional e sequência

- `RUNTIME_NAMES` vira `runtime_units(imports)`: unidades base + `pcre_shim.c` + fontes do
  PCRE2 **só** quando `regex`/`pcre2` é importado. A chave do cache de build inclui o
  conjunto de unidades e a versão do vendor.
- Teste: binário sem `import regex` não tem símbolos `pcre2_*` (`nm`) e não cresce.
- **Regex inaugura a camada** (`vendor/`, `bundled/`, `runtime_units(imports)`), antes do
  SQLite: o vendor é menor, o consumidor existe hoje e o SQLite reusa a máquina pronta.

### 8. Sandbox e sintaxe

- Regex é puro cálculo: não lê arquivo, não abre socket, não consulta ambiente. `--sandbox`
  **não** nega `pcre2`; a spec declara isso.
- **Sem literal `/.../`**: regex continua biblioteca. Sintaxe nova seria gate do
  [ADR-0066](0066-orcamento-e-gate-sintatico.md), e não precisa.

## Consequências

### Positivas

- Um motor só: nada de `ambient` para regex e nada de divergir nas bordas que as pessoas
  usam (match vazio, lookbehind, possessivo).
- `loxia run` funciona, então os scripts de CI dogfoodam o interpretador, não só o compilador.
- Sem dependência de sistema e sem matriz de wheel: o vendor pinado torna Unicode e
  semântica reprodutíveis.
- Binário que não importa regex não paga nada; a feature inteira fica opt-in por `import`.
- PCRE completo de verdade, incluindo `\p{...}`, `\K`, `\G`, recursão e condicionais.

### Negativas / custos

- O interpretador deixa de ser "só Python": `import regex` exige `cc` e um build no primeiro
  uso (cacheado). É a primeira capacidade do `run` com pré-requisito de toolchain.
- Mais um eixo no cache de build e na tabela de unidades do runtime.
- Ciclo de CVE e de atualização de Unicode passa a ser do projeto.
- O binário que importa regex cresce (centenas de KB) e o build fica mais lento.
- **O diferencial perde valor como oráculo independente para matching**: os dois caminhos
  usam o mesmo PCRE2. O que continua sendo testado de forma independente são os bindings e o
  wrapper Lox; a referência de semântica é o PCRE2 (vetores do `pcre2test`), não o
  interpretador.
- Backtracking continua existindo: os limites tornam o pior caso bounded, não linear.

### Neutras

- `pcre2` é feio, mas é o nome da biblioteca (mesma regra de `sqlite3`).
- Handles são `Int` até existir tipo opaco; a casca (`Regex`) muda sem mudar o usuário.
- JIT fica para depois, atrás da mesma fronteira.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Motor em Lox puro (Pike VM) | 6 µs por char medidos; ~4 s por arquivo de 10 KB; não é "performático desde o início" |
| Espelho em `re`/`regex` no interpretador (`ambient`) | duas semânticas que divergem nas bordas, dependência Python nova e o caso de uso mais dogfoodado fora do corpus |
| `libpcre2` do sistema (`ctypes`) | versão e tabelas Unicode variam por máquina; quebra reprodutibilidade |
| `native-only` (só `--emit=exe`) | `run` recusaria; todo script de CI teria que ser compilado antes |
| Oniguruma | menos mantido e mais lento que PCRE2 para o mesmo conjunto |
| ICU | C++, grande, foco CJK; não é o custo certo para regex |
| RE2 | sem backref e sem lookaround: falha o requisito "completo" |
| Motor próprio | dezenas de milhares de linhas + tabelas + JIT; reescrever décadas |
| Literal `/.../ ` | gate sintático do ADR-0066; a biblioteca resolve sem gramática nova |

## Como verificar

- Golden `tests/cases/std_regex/*.lx`: grupos nomeados, lazy, backref, lookaround, `\p{L}`,
  Unicode multibyte, match vazio em `findAll`, `replace` com `$1`.
- Diferencial `run` × `--emit=exe` (mesmo shim, bindings diferentes) e `--check` limpo.
- Caso negativo: `(a+)+$` sobre entrada longa devolve `RuntimeError` estável dentro dos
  limites; teste com timeout de parede.
- Vetores de conformidade gerados do `pcre2test` (subconjunto versionado no repo).
- `nm`/`strings`: binário sem `import regex` não contém `pcre2_`; com import, contém.
- `tests/test_layers.py`: `pcre2` com camada e com `requires`, `E3022` registrado e
  documentado em `docs/spec/erros.md`.
- `tests/test_stdlib_docs.py`: página gerada de `regex` e das primitivas.
- `make bench`: caso do wrapper (`findAll` sobre N matches) para pegar regressão no Lox.
- Revisitar se: o build no primeiro `run` passar de poucos segundos de forma perceptível; o
  binário que importa crescer além do aceitável; aparecer um motor com ABI menor e mesmas
  garantias; ou o custo de CVE/upgrade superar o benefício.

## Referências

- [#114](https://github.com/loxia-lang/loxia/issues/114) — decisão e alternativas.
- [PCRE2](https://www.pcre.org/current/doc/html/) — sintaxe, flags e limites.
- [ADR-0126](0126-modulo-nativo-embutido-sqlite.md) — camada, link condicional e guarda de
  callback.
- [ADR-0128](0128-contrato-de-motores.md) — camadas e recusa explícita.
- [ADR-0072](0072-stdlib-batteries.md) — escopo original da stdlib (linha de regex
  substituída por este ADR).
