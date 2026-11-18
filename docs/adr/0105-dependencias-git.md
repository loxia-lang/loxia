# ADR-0105 — Dependências `git`: rev pinada, cache e fetch offline

- **Status:** accepted (implementado)
- **Data:** 2026-11-17
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0100](0100-dependencias-path.md) (`path`), [ADR-0104](0104-lock-e-frozen.md)
  (lock/hash/`--frozen`), [ADR-0066](0066-orcamento-e-gate-sintatico.md) (sem sintaxe nova),
  [ADR-0088](0088-distribuicao-e-raizes-de-modulo.md), [`../../TODO.md`](../../TODO.md) §14.7
  (fase 2), [`../../IDEIAS.md`](../../IDEIAS.md) I-10
- **Implementação:** `loxia_core/loader/manifest.py` (`git`/`rev`),
  `loxia_core/loader/deps.py` (mirror, checkout, resolução),
  `loxia/cli.py` (`lock`/`fetch` com `--offline`/`--cache-dir`),
  `examples/monorepo/`, `tests/test_dependencies.py`, `tests/test_monorepo.py` e
  `tests/test_backend.py`

## Contexto

A fase 1 ([ADR-0104](0104-lock-e-frozen.md)) tornou `path` reprodutível, mas monorepo e
pacote de terceiro exigem buscar código fora da árvore. Sem registry (fase 3), `git` é o
transporte que já existe e não pede servidor. A restrição continua a mesma: **`loxia run`
nunca acessa a rede** e o build tem que ser determinístico.

O [ADR-0100](0100-dependencias-path.md) tinha deixado `git`, cache e fetch explicitamente
fora de escopo; este ADR fecha a fase 2.

## Decisão

### 1. Formato e validação no manifest

```toml
[dependencies]
acme = { git = "https://github.com/acme/acme", rev = "v1.2.3" }
```

- Exatamente um de `path` ou `git`; `rev` só existe com `git` e é **obrigatório**.
- `rev` é commit completo (40 ou 64 hex) ou **tag**; branch nunca (não é reprodutível).
  `-x`, `..` e espaços são rejeitados.
- URL: `https://`, `ssh://`, `git://`, `file://` ou `user@host:path`. `ext::`/`fd::`
  (transporte que executa comando), URL começando com `-` e whitespace são rejeitados.
- `file://` é aceito para desenvolvimento/teste e é guardado **verbatim** no lock; não é
  portátil entre máquinas, então não é o caminho recomendado para pacote publicado.

Nada disso é sintaxe da linguagem: o `import` continua com identificadores
([ADR-0066](0066-orcamento-e-gate-sintatico.md)).

### 2. O lock fixa commit e conteúdo

Entrada `git` no `loxia.lock`:

```toml
[[package]]
name = "acme"
git = "https://github.com/acme/acme"
rev = "v1.2.3"          # o que o manifest declarou
commit = "…40 hex…"     # o que a tag resolvia no momento do lock
version = "1.2.3"       # [package].version do manifest da dependência (obrigatória)
sha256 = "…"            # hash da árvore .lx do checkout
```

`loxia lock` resolve tag → commit (rede permitida, salvo `--offline`) e grava o commit.
`--frozen`/`run` usam **sempre o commit do lock**: mover a tag depois não muda o build;
para atualizar, `loxia lock` de novo. Dependência `git` sem `[package].version` no próprio
`loxia.toml` falha no lock.

### 3. Cache por projeto, checkout limpo

- Default: `.loxia/cache/` na raiz do projeto (ignorado pelo git); `--cache-dir` troca.
- Mirror bare por URL: `.loxia/cache/git/<sha256(url)[:16]>.git`, reutilizado entre locks.
- Checkout por commit: `.loxia/cache/src/<hash>/<commit>/`, extraído com
  `git archive` + `tarfile` (`filter="data"`), sem `.git`, sem hooks, sem submódulos,
  sem LFS e sem scripts. Extração é atômica (diretório temporário + rename).
- O lock nunca guarda caminho de cache; o hash só depende do conteúdo.

### 4. Quem pode acessar a rede

| Comando | Rede |
| --- | --- |
| `loxia lock` | sim — clona/atualiza o mirror e resolve a tag |
| `loxia fetch` | sim — baixa o commit do lock e materializa o checkout |
| `lock`/`fetch` com `--offline` | não — só cache; falta de commit = erro |
| `run`/`check`/`build`/`ast`/`test` | **nunca** — checkout já materializado ou erro |

`run` com commit no lock e checkout ausente falha com `C0002` ("not available locally;
run `loxia fetch`"). `run --offline` é aceito e não muda nada (run já é offline por
construção). O checkout é verificado contra o `sha256` do lock em `--frozen`/`run`; cache
adulterado é erro, não miscompile.

### 5. Segurança e determinismo

- `GIT_TERMINAL_PROMPT=0`, timeout de 300 s por comando; falha de git vira mensagem
  estável (stderr do git não vaza).
- Diagnóstico não mostra credencial (`user:pass@`) nem caminho absoluto de `file://`
  (só o nome do repositório); o resto da URL aparece porque é a identidade declarada.
- Sem execução de código no fetch/build: o pior caso é compilar fonte hostil.
- Ordem determinística: dependências ordenadas por nome; mirror/checkout endereçados por
  hash de conteúdo/URL.

### 6. `C0002` continua sendo o código

Estado de dependência (não travada, não baixada, rev/tag inexistente, hash divergente)
usa `C0002` (fase `cli`) e exit 65; manifest inválido continua `E1001`.

## Consequências

### Positivas

- Monorepo/pacote externo funcionam sem registry e sem segundo comando.
- Tag é conveniência; o commit travado é a garantia (nada de build "que muda sozinho").
- CI offline é possível: `loxia fetch` uma vez, depois `--frozen`/`--offline`.
- O loader não mudou: continua recebendo raízes resolvidas.

### Negativas / custos

- `loxia lock` materializa o checkout para calcular o hash (precisa de rede na primeira
  vez, salvo cache).
- Cache por projeto duplica clonagem entre projetos; `--cache-dir` compartilhado é a
  válvula.
- `file://` no lock não é portátil; é ferramenta de dev/teste.
- Sem dependências transitivas na v1 (o manifest do pacote não é lido além de
  `[package].version`).

### Neutras

- Submódulos e LFS ficam de fora (fonte de não determinismo e de supply chain).
- O mirror bare cresce com o histórico do repositório; limpeza manual é aceitável por ora.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Rev = branch solto | Build muda sem diff; quebra I3 e o lock. |
| Só SHA completo (sem tag) | Tags são o jeito humano de versionar; o lock já resolve para commit. |
| Clonar com checkout git dentro do cache | Deixa `.git`, hooks e configuração local no material compilado. |
| `git clone` por projeto sem mirror | Rebaixa o mesmo repositório a cada fetch. |
| Suportar `ext::`/helpers | Executa comando arbitrário no fetch; viola "sem scripts". |
| Vendorizar no primeiro uso | Esconde a origem e duplica fonte; o cache explícito é auditável. |

## Referências

- [`../../docs/spec/semantica.md`](../../docs/spec/semantica.md) — regra normativa.
- [`../../TODO.md`](../../TODO.md) §14.7 — fase 2 (este ADR) e fase 3 (registry).
