# Log da documentação

Registro das triagens de frescor. O script `docs/_hooks/freshness.py` **detecta** as
páginas candidatas a desatualizadas (comparando o último commit da página com o último
commit das `sources:` declaradas no front matter); este arquivo é a parte **humana**:
o veredicto e o motivo.

## Protocolo

1. `make docs-fresh` lista as páginas cujas fontes mudaram depois da página.
2. Para cada página, olhe o diff das fontes e decida:
   - `updated` — o texto mudou (e o diff da página está no mesmo commit);
   - `no-change` — o texto continua verdadeiro (diga por quê, em uma linha).
3. Registre aqui: data, intervalo (commits) e uma linha por página.
4. Se o código ganhou/removeu um módulo, ajuste as `sources:` da página no mesmo commit —
   glob que não casa com nada é erro no `tests/test_docs_consistency.py`.

Regras:

- **Nunca** dê `updated` só para "marcar como revisado": tocar a página para silenciar o
  relatório apaga o único sinal que existe.
- **Nunca** documente intenção ("vai fazer X"). Se não está no código, não está na página.
- Página nova nasce com `sources:`; sem isso ela nunca aparece como candidata — e o gate
  de cobertura falha.

## 2026-11-13 — I4, orçamento de memória e gate de docs

Intervalo: `f3002d3..HEAD` (L6a–L6h + L6e/f + este trabalho).

- `docs/spec/garantias.md` — **updated**: I4 (`--check` limpo compila), orçamento de
  memória (ADR-0060), bloco de níveis agora gerado de `tests/corpus_manifest.py`, status
  do backend corrigido (dizia L0–L5 + T7).
- `docs/spec/lexico.md` — **updated**: front matter `sources:` **e** a tabela de
  palavras-chave, que estava sem `enum`, `except`, `finally`, `match`, `raise` e `try`
  (encontrado pela primeira execução do `freshness.py`, não por leitura manual).
- `docs/spec/{sintaxe,semantica,erros}.md` — **updated**: front matter `sources:`
  (texto já descrevia o código atual).
- `docs/decisoes.md` — **updated**: linhas de I4, promoção em armazenamento e memória.
- `README.md` — **updated**: promessas I4/memória, `--output` documentado, "próximo passo"
  corrigido (L6 restante), versão ainda 1.0.0.
- `ESCOPO.md` — **updated**: status do backend (L0–L5 + T7 + L6a–L6h) e contagem de testes
  removida do texto (número absoluto envelhece).
- `AGENTS.md` — **updated** (local, não versionado): I4, memória, DoD, skill `lox-docs`.

## 2026-11-13 — ADRs 0058–0060 e colisão de numeração

O ADR-0058 (L6h) foi commitado por outra sessão enquanto o ADR de I4 era escrito com o
mesmo número. Renumerado para 0059/0060 e o `tests/test_docs_consistency.py` passou a
verificar numeração única e sequencial — a colisão não pode se repetir em silêncio.

## 2026-11-13 — higiene do TODO

`TODO.md` reescrito para conter **só o que falta**: saíram os marcos `[x]` (L0–L5, L6a–L6h,
T1–T7), as tabelas de decisão já registradas em ADR (escolha do `llvmlite`, representação
de escalares, runtime C), o checklist do corpus e a lista de "fechadas recentemente".
Ficaram só as pendências reais e todas as âncoras citadas por outros documentos (§0.1,
§0.2, §6.3, §6.5, §6.6, §6.8, §6.11, §8, §9, §11). O status por nível não é mais copiado
aqui: é gerado em `docs/spec/garantias.md`.

## 2026-11-13 — gate sintático e desambiguação (ADR-0066/0067)

Intervalo: `HEAD..working tree` (mudanças ainda não commitadas).

- `docs/adr/0066-orcamento-e-gate-sintatico.md` — **novo**: quatro perguntas, orçamento,
  não-objetivos e aprovação humana; referenciado por `AGENTS.md` §1/§4/§7/§11.
- `docs/adr/0067-desambiguacao-sintatica.md` — **novo**: `//`, operador em brackets, `fn`
  em método, união em `is` e mapa no início de statement, com a justificativa de `|` (tipo)
  vs `or` (runtime).
- `docs/spec/{sintaxe,lexico,semantica,erros}.md` — **updated**: regra de operador em
  brackets, `fn` opcional em método, união de `is` com parênteses, diagnósticos dirigidos,
  bullet de `match`/lambdas corrigido.
- `docs/decisoes.md`, `docs/adr/README.md`, `TODO.md` — **updated**: índice, resumo e §1
  (itens fechados + não-objetivos).
- `AGENTS.md` — **updated** (local): portão sintático, DoD e tabela de decisão.
- `.dsh/skills/lox-syntax/SKILL.md` — **novo**: procedimento operacional do gate.
- `tests/test_docs_consistency.py` — **updated**: guarda as frases defasadas de `match` e
  lambdas.

## 2026-11-13 — `not`, destructuring aninhado e strings `"""`/raw (ADR-0068/0069/0070)

Intervalo: `HEAD..working tree` (mudanças ainda não commitadas).

- `docs/adr/0068-not-substitui-bang.md` — **novo**: `not` substitui `!` no nível unário,
  `!` vira diagnóstico dirigido e `!=` continua; sem alias (uma grafia).
- `docs/adr/0069-destructuring-aninhado.md` — **novo**: padrão recursivo em `val`/`var`,
  erros por nível e a correção do I4 na captura por closure.
- `docs/adr/0070-strings-multilinha-e-raw.md` — **novo**: `"""` canônico para multilinha,
  raw `r"..."`/`r"""..."""` e `"..."` de uma linha (substituição, não segunda grafia).
- `docs/adr/0066-orcamento-e-gate-sintatico.md` — **updated**: scoreboard de keywords com
  a regra de contagem explícita (25) e os novos não-objetivos (parênteses opcionais, corpo
  de expressão, bloco-expressão, `match` estrutural, `loop`, trailing closure, `!`).
- `docs/spec/{lexico,sintaxe,semantica}.md` — **updated**: tokens/keywords (`not`), strings
  `"""`/raw e regras de erro, padrão de destructuring recursivo, negação e precedência.
- `docs/spec/garantias.md` — **generated**: bloco de níveis regerado (`docs-sync`) com os
  casos novos de string e destructuring no corpus L3/L6.
- `TODO.md` §1 — **updated**: fila aprovada (`break`/`continue`, spread, variádicos,
  named args bloqueados até o LLVM MVP, imports, traits/extension/operator/`derive`,
  `type` alias) e lista de descartados; `assert`/`panic`/`exit` e subclasses de runtime
  movidos para §3.2 (não são sintaxe).
- `docs/decisoes.md`, `docs/adr/README.md`, `CHANGELOG.md`, `README.md` — **updated**:
  índice, resumo, changelog e exemplos (`not`, `"""`, raw).
- `AGENTS.md` — **updated** (local): tabela de arquivos, semântica de strings/tuplas e
  histórico da negação.
- `tests/test_docs_consistency.py` — **updated**: o scoreboard de keywords do ADR-0066
  agora é verificado contra `KEYWORDS`.

## 2026-11-14 — primitivas, stdlib e imports (ADR-0071/0072/0073)

Intervalo: `HEAD..working tree` (planejamento; nenhum código tocado).

- `docs/adr/0071-primitivas-de-runtime.md` — **novo**: kernel = SO/representação, teto de
  15 primitivas, tabela única, cache de offsets (`chars`/`for-in` O(n), `substr` O(1),
  `join` O(total)), sem FFI genérica e sem `ctypes` no oráculo.
- `docs/adr/0072-stdlib-batteries.md` — **novo**: três camadas, módulos só de declaração,
  tiers T0–T3, critério de admissão e não-objetivos (regex, cripto, rede, async...).
- `docs/adr/0073-imports-modulos.md` — **novo (proposed)**: `import std.<módulo>`, desugar
  para programa plano com nomes manglados, fase A só std; quatro perguntas do gate
  respondidas, aguardando aprovação humana.
- `docs/adr/README.md`, `docs/decisoes.md` — **updated**: índice e resumos (primitivas,
  stdlib; módulos marcados como propostos).
- `TODO.md` — **updated**: §0.3/§0.4 (plano fora da fila), §8 (imports/FFI/stdlib), §10
  (self-host reclassificado), §11 (imports, kernel, escopo) e **§13 novo** com o kernel,
  a tabela, os imports e o inventário de batteries.
- Sem mudança em `src/`, `runtime/` ou `docs/spec/`: 0071/0072 são plano; a spec só muda
  quando a implementação começar.
