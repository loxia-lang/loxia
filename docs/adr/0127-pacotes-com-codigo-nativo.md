# ADR-0127 — Pacotes com código nativo: contrato adiado, forma registrada

- **Status:** proposed
- **Data:** 2026-11-21
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0071](0071-primitivas-de-runtime.md) (sem FFI genérica),
  [ADR-0100](0100-dependencias-path.md) / [ADR-0104](0104-lock-e-frozen.md) /
  [ADR-0105](0105-dependencias-git.md) (deps, lock e git),
  [ADR-0119](0119-fs-open-handles-e-erro-de-host.md) (sandbox),
  [ADR-0123](0123-orcamento-do-kernel-por-grupo.md) (kernel),
  [ADR-0125](0125-bytes-tipo-binario.md) (`Bytes`),
  [ADR-0126](0126-modulo-nativo-embutido-sqlite.md) (módulo nativo embutido),
  Discussions [#31](https://github.com/loxia-lang/loxia/discussions/31) (net),
  [#32](https://github.com/loxia-lang/loxia/discussions/32) (registry)
- **Implementação:** nenhuma (adiado); quando o gatilho disparar, `loxia_core/loader/manifest.py`,
  `loxia_core/loader/deps.py`, `loxia/cli_commands.py` e `loxia_core/backend/driver.py`

## Contexto

Hoje um pacote é **só Lox**: o manifest aceita `package`/`modules`/`dependencies`
([`manifest.py#L25`](../../loxia_core/loader/manifest.py)), o lock hasheia apenas a árvore
`.lx` ([`deps.py#L48-L68`](../../loxia_core/loader/deps.py)) e o loader só lê `.lx`. Código
nativo só existe **dentro do toolchain**, no runtime e no módulo embutido do
[ADR-0126](0126-modulo-nativo-embutido-sqlite.md).

Isso é uma decisão, não um esquecimento: um pacote com `.c` traria código arbitrário para o
processo, fora do sandbox, com binários por plataforma, supply chain e um lock que hoje não
veria o binário. A pergunta concreta que abriu o assunto foi o **Postgres**:

- **Bindar `libpq`** — o cliente oficial implementa protocolo, SCRAM e TLS; a cola em Lox é
  fina (~500–1000 linhas). Custo: dependência nativa por plataforma.
- **Protocolo em Lox** — `pgx`/`asyncpg` fazem isso, mas exigem `net`, `Bytes`, TLS e I/O
  assíncrono maduro; em Loxia seriam ~10 mil linhas e um TLS escrito em casa.

Nenhuma das duas cabe em `std` (e nenhuma é para agora). O que precisa ficar registrado é a
**forma** que um pacote nativo terá, para não ser improvisada quando o primeiro consumidor
aparecer.

## Decisão

### 1. Agora: nenhum código nativo de terceiro

Só o toolchain linka C, e só através de módulo nativo embutido ([ADR-0126](0126-modulo-nativo-embutido-sqlite.md)).
Um pacote de terceiro continua sendo uma árvore `.lx`. Isso mantém, nesta ordem:
reprodutibilidade (o lock vê tudo), sandbox (código importado não pode mais que o programa),
e distribuição (um wheel, sem binário por plataforma).

### 2. Forma quando o gatilho disparar

- **Manifest**: seção `[native]` explícita — fontes (`sources`), bibliotecas (`libs`) e
  `pkg-config` opcional; **nada de flags de linker arbitrárias** (allowlist).
- **Lock**: além da árvore `.lx`, um hash da árvore nativa (fontes e artefatos declarados);
  `--frozen` verifica os dois. Pacote nativo sem hash de nativo falha no `lock`.
- **Build**: compila com `cc` o que o manifest declarar, com flags fixas e cache por hash
  (fontes + versão do compilador + plataforma); `--emit=exe` linka; `run`/`check` exigem
  artefato já construído (nunca rede).
- **Plataforma**: o pacote declara `platforms = [...]`; fora da lista, falha fechado com
  mensagem clara. Binário pré-compilado só entra com hash e origem declaradas.
- **Segurança**: `import` de pacote nativo é **ambient**; `--sandbox` nega; a documentação
  diz que o código roda com os privilégios do processo. Sem `extern fn`, sem `dlopen`, sem
  símbolo arbitrário — o C fala a ABI do runtime, como um módulo embutido.
- **Distribuição**: sem registry, `git` + tag + hash; um repo por pacote (o loader não
  aponta para subdiretório). Descoberta pelo índice `loxia-lang/packages`.

### 3. Postgres: `libpq` primeiro, protocolo depois (se um dia)

- A rota barata é **bindar `libpq`** por pacote nativo: o TLS e o SCRAM ficam dentro dela.
- A rota pura (protocolo em Lox) só faz sentido com `net`, `Bytes`, TLS e async maduros; é
  outro projeto, não um item de stdlib.
- `std` não ganha driver de banco. O que std/kernel dão é a base: `Bytes`, `net`, `Result`.

### 4. Gatilhos

1. Um consumidor real de biblioteca C que **não** caiba em módulo embutido (segundo banco,
   cliente de mensageria, compressão específica);
2. `Bytes` implementado ([ADR-0125](0125-bytes-tipo-binario.md)) — sem ele, protocolo
   binário não existe;
3. módulo embutido provado (link condicional, vendor, sandbox) pelo [ADR-0126](0126-modulo-nativo-embutido-sqlite.md);
4. uma história de distribuição por plataforma (pré-compilado com hash ou build no install).

Sem os quatro, não há ADR de implementação; o assunto fica aqui.

### 5. Não-objetivos

`extern fn` e símbolo arbitrário, `dlopen` em runtime, FFI dentro do interpretador, flags
de linker livres, pacote nativo sem hash, e Windows enquanto o runtime for POSIX-first.

## Consequências

### Positivas

- A fronteira fica explícita antes de existir código: nada de "só um `.c` no pacote".
- O lock continua sendo a fonte de verdade do que roda.
- `libpq`/SQLite deixam de competir com o kernel: são bibliotecas, não primitivas.

### Negativas / custos

- Sem pacote nativo, o ecossistema não cobre banco de rede; o Postgres espera.
- Quando vier, cada plataforma vira matriz de build e de teste.
- Supply chain: um pacote nativo é código executável; revisão e hash não substituem auditoria.
- O lock cresce em complexidade (duas árvores, dois hashes).

### Neutras

- O índice de pacotes ([#32](https://github.com/loxia-lang/loxia/discussions/32)) continua
  fora; sem registry, a descoberta é manual.
- `net` continua parked ([#31](https://github.com/loxia-lang/loxia/discussions/31)); `libpq`
  não precisa dele.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Permitir `.c` em pacote já | O lock não vê o binário, o sandbox não segura, e não há distribuição por plataforma; seria uma porta dos fundos para FFI. |
| Só Lox para sempre | Fecha a porta de banco de rede e de bibliotecas maduras; o custo de reimplementar TLS/protocolo é maior. |
| FFI genérica (`extern fn`) | [ADR-0071 §4](0071-primitivas-de-runtime.md): ABI, ownership, portabilidade e superfície de erro; e destrói a independência do oráculo. |
| Registry primeiro | Projeto maior e não resolve o problema do binário; `git` + hash já cobre o transporte. |
| Driver pg em Lox agora | `net` parked, TLS inexistente, `Bytes` recém-decidido e sem async; seria refém de quatro projetos. |

## Como verificar

Nada a verificar enquanto adiado. Quando o gatilho disparar, o ADR de implementação precisa
provar: lock com hash nativo, `--frozen` falhando em divergência, `--sandbox` negando o
import, build reprodutível em duas plataformas e ausência de símbolo não declarado no
binário.

Critério para revisitar: os quatro gatilhos da §4, ou uma decisão de produto que exija banco
de rede antes disso.

## Referências

- [ADR-0105](0105-dependencias-git.md) — `git`, lock e cache.
- [ADR-0126](0126-modulo-nativo-embutido-sqlite.md) — a camada embutida que vem antes.
- [ADR-0125](0125-bytes-tipo-binario.md) — pré-requisito binário.
- [libpq](https://www.postgresql.org/docs/current/libpq.html) — cliente oficial do Postgres.
