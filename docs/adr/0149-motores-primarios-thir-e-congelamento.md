# ADR-0149 — Motores primários: nativo por padrão, THIR como eixo e congelamento por módulo

> **Especificado por** [ADR-0154](0154-fronteira-do-thir.md): a fronteira do THIR
> (declaração × layout, capturas sem `depth`).
>
> **Emendado por** [ADR-0156](0156-sem-desugaring-no-thir.md): o THIR **não desuga** controle
> — `for-in`, `match`, `?:`, `??`, `?.` e interpolação ficam explícitos no contrato.

- **Status:** accepted
- **Data:** 2026-11-26
- **Decisores:** Cassio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0002](0002-tree-walk-como-oraculo.md) (tree-walk como oráculo),
  [ADR-0014](0014-identidade-e-invariantes.md) (I1–I4), [ADR-0031](0031-backend-nativo.md)
  (backend nativo), [ADR-0046](0046-closures-celulas-l4.md) (closures),
  [ADR-0059](0059-i4-check-limpo-compila.md) (I4), [ADR-0064](0064-orcamento-do-corpus.md)
  (orçamento do corpus), [ADR-0065](0065-hir-lite-controle.md) (HIR-lite de controle),
  [ADR-0074](0074-gc-boehm-e-contrato-de-memoria.md) (GC), [ADR-0077](0077-limite-de-pilha.md)
  (pilha), [ADR-0087](0087-heap-cap-e-self-hosting.md) (heap e self-hosting),
  [ADR-0089](0089-stack-trace-de-runtime.md) (stack trace), [ADR-0107](0107-adiados-e-nao-objetivos.md)
  (adiados), [ADR-0115](0115-corpus-de-conformidade-adiado.md) (corpus de conformidade),
  [ADR-0121](0121-matriz-de-cobertura-de-features.md) (matriz de cobertura),
  [ADR-0124](0124-fmt-self-host-e-pacotes-por-repo.md) (self-host do front),
  [ADR-0128](0128-contrato-de-motores.md) (camadas de motor), [ADR-0129](0129-oraculo-do-front-end.md)
  (oráculo do front), [ADR-0133](0133-suite-rapida-in-process-e-xdist.md) (suíte rápida),
  [ADR-0148](0148-ponto-de-entrada-main-result.md) (entry point)
- **Implementação:** [`docs/plano-de-motores.md`](../plano-de-motores.md) (fases, portões,
  indicadores e painel). Este ADR decide; o plano opera; as issues são o status. O THIR, a
  IR de controle e os motores em Loxia entram nas fases F0–F6 do plano.

## Contexto

O projeto tem **um front, um checker e dois executores**:

| Superfície | Tamanho | Papel |
| --- | --- | --- |
| frontend (scanner/parser/AST) | ~2,4k linhas | sintaxe, spans, trivia |
| resolver | 736 linhas | `depth` para o tree-walk e o lowering |
| checker | 5.536 linhas | fonte única dos tipos (I4) |
| interpretador | 1.609 linhas | oráculo e `run`/REPL |
| lowering + driver | ~11k linhas | backend LLVM (opt-in) |
| runtime C | ~6,3k linhas | valores, GC, kernel, exceções |

Não há três versões da linguagem: há **um front, um sistema de tipos e duas execuções**
(~18,8k linhas de execução). O custo real por feature não é LOC; é a **mesma decisão
semântica tomada duas vezes** — desugar `for-in`, unwrap de `T?`, `match`, interpolação,
defaults, captura, layout de classe. Cada uma existe em Python e em lowering/C, e a
divergência entre elas é exatamente o que o diferencial tenta pegar.

Hoje:

- `loxia run` é o tree-walk; o nativo é opt-in (`build --emit`). O **oráculo e o motor do
  usuário são o mesmo artefato**, e ele é lento.
- O [ADR-0065](0065-hir-lite-controle.md) definiu um gatilho para HIR-lite de controle: se
  `lower_exceptions.py`/`lower_enums.py` passar de ~350 linhas, parar e propor. Hoje são
  **385** e **434** linhas — o gatilho disparou.
- O lowering consome o AST e side tables por **identidade de nó** (`dict[Expr, Ty]`); não há
  IR intermediária. O desugaring e o controle são re-derivados no backend.
- O checker consome `list[Stmt]` Python. Enquanto isso, o front Python fica **pinado** pelo
  checker: sem uma ponte, "front em Loxia" não congela.
- O self-host é meta de credibilidade/pessoal. O checker é a maior peça e a última.

A pergunta que este ADR fecha: como o nativo vira o produto, o Python é aposentado por
partes e a linguagem continua tendo interpretador e compilador com **a mesma semântica**,
sem manter três implementações crescendo para sempre?

## Decisão

### 1. `run` compila com cache; o nativo é o produto

`loxia run prog.lx` **compila com o backend e executa o binário**, com cache
content-addressed (fonte + deps + identidade do compilador + flags + plataforma + heap),
reutilizando a infraestrutura do `loxia test --native`. `--interpret` mantém o tree-walk; o
REPL continua interpretado. O cache é só desempenho: não muda bytes, não entra na saída e
`--no-cache` força o build.

Não há divisão "dev interpreta / prod compila": dev e prod usam **o mesmo backend**, então
codegen é exercitado todo dia. O interpretador passa a ser REPL, `--interpret` e oráculo —
não o caminho padrão de execução de scripts. O `run` AOT usa o check do `build`;
`--interpret` mantém o check gradual do `run`; a issue F0 garante que a aceitação não
divirja (ou declara a diferença).

`loxia run app` (binário) **não** é contrato: o binário é executável direto. `run` é comando
de fonte; sobrecarregá-lo com binário confunde distribuição com execução.

### 2. THIR é o eixo

Uma árvore **tipada e desugarada** entre o checker e os motores. Não é CFG, não é SSA: é
árvore. Carrega:

- binding resolvido (slot/cell/global) e IDs estáveis, não `depth` por identidade de nó;
- tipo de armazenamento **e** tipo de fluxo (narrowing);
- desugaring explícito: `for-in`, `?.`/`??`, interpolação, ternário, `match`,
  destructuring, defaults;
- capturas explícitas e layout de classe (índices/bitmap);
- instanciações genéricas;
- spans preservados para diagnóstico (ADR-0075/ADR-0089).

O AST continua existindo para tooling (formatter, LSP, `ast_json`). O THIR é **serializado**
como contrato entre o checker Python (build-time) e os motores Loxia (runtime); o snapshot
do THIR é contrato de revisão, como o snapshot do front ([ADR-0129](0129-oraculo-do-front-end.md)).
O lowering deixa de re-derivar tipos/desugar; o interpretador deixa de resolver/desugar.
As side tables por identidade de nó desaparecem.

O THIR não vira CFG. Se um construto precisar de fluxo, ele desce para a IR de controle do
backend — esse é o sinal de que o THIR está no lugar certo.

### 3. IR de controle é interna ao backend

Blocos, terminadores, phi e pilha de cleanup, conforme o [ADR-0065](0065-hir-lite-controle.md),
para exceções, `match` e classes. É **interna ao backend**: não é pública, não toca o
oráculo, não substitui o THIR. A divisão é:

```
THIR (semântica, front)  →  IR de controle (codegen, backend)  →  LLVM IR (alvo)
```

### 4. Interpretador: THIR eval em Loxia primeiro; VM só com decisão

O interpretador Loxia consome THIR; é o motor de REPL/`--interpret` e o oráculo vivo.
Bytecode VM fica **adiada**: só entra se o REPL virar primeira classe ou a medição exigir,
e **nunca junto** com o THIR eval — um interpretador, não dois. Se a VM vier, ela consome
`THIR → bytecode` e o THIR eval permanece como referência.

### 5. Congelamento por módulo, com portões

**Congelar** = parar de receber feature nova; o módulo continua rodando o corpus congelado
como rede de regressão. Os portões são:

| Portão | Critério |
| --- | --- |
| **G1 Paridade** | 100% dos casos do módulo (positivos, `NEGATIVE`, `COMPILE_ERRORS`) batem byte a byte |
| **G2 Soak** | 4 semanas / N execuções sem divergência; fuzz de 24 h sem diff |
| **G3 Default** | o substituto é o caminho padrão; o antigo só roda no corpus congelado |
| **G4 Docs** | `spec/garantias.md` + ADR + CHANGELOG registram o congelamento e a cobertura ("linguagem ≤ versão N") |
| **G5 Remoção** | após 2 releases sem rollback, mover para `oracle/` (read-only) ou remover |

Ordem de congelamento:

| # | Módulo | Substituto | Fica pinado por | Fase |
| --- | --- | --- | --- | --- |
| 1 | interpretador (+ resolver) | THIR eval em Loxia | REPL/oráculo | F3 |
| 2 | lowering + driver | compilador Loxia | — | F4 |
| 3 | frontend (+ loader) | front Loxia | checker (até a ponte) | F5 |
| 4 | checker | checker Loxia | — | F6 |

O **runtime C nunca congela** (é o produto). O CLI/tooling pode ficar em Python
indefinidamente; portá-lo é projeto separado.

### 6. O oráculo migra de Python para spec + corpus + golden

Enquanto o Python não congela, ele é normativo (o I1 de hoje). No portão F3, o Python
congela no release N e o **corpus dourado** passa a ser o contrato de máquina:

- cada caso tem stdout/stderr/exit em bytes, versionado;
- o golden do núcleo ≤ N é gerado pelo **Python congelado** (independente);
- o golden de feature nova é **escrito a partir da spec**, nunca gerado pelo motor sob teste;
- atualizar golden é revisão consciente, como o snapshot do ADR-0129; "consertar para
  passar" é proibido.

O diferencial continua: THIR eval × compilador para codegen. O Python congelado é o
desempate do núcleo antigo. **I1 não muda de promessa** — core continua byte a byte nos dois
motores; muda o **ciclo de vida** do oráculo e o texto de `spec/garantias.md`, atualizado no
portão, não neste ADR.

### 7. Self-host em níveis

| Nível | Definição | Quando |
| --- | --- | --- |
| **1 — self-executing** | front + interpretador + compilador em Loxia; checker Python como serviço de build; `loxia` nativo roda/compila; Python só no bootstrap | ano 1 |
| **2 — self-hosted** | checker em Loxia; o toolchain se constrói sozinho | ano 2 (objetivo pessoal) |
| **3 — bootstrap reprodutível** | stage0 → stage1 → stage2; stage1 ≡ stage2 (comportamental; bit a bit se possível) | depois do 2 |

O checker vira Loxia **quando for prudente dogfoodá-lo**, não antes de o resto estar pronto.
"Python congelado" nunca é total enquanto o checker for Python — e isso é uma escolha
declarada, não um esquecimento.

### 8. A ponte do checker

Para o front Loxia não ficar pinado: o front Loxia emite **AST JSON v2**
([ADR-0129](0129-oraculo-do-front-end.md)) e o checker Python desserializa. O round-trip é
testado (`AST Python → JSON → AST Python` idêntico; `front Loxia → JSON` igual). O checker
sobre THIR é a evolução, não o pré-requisito. **Sem a ponte, a fase F5 não congela o front.**

## Consequências

### Positivas

- Dev e prod no mesmo backend; codegen exercitado todo dia, não só no CI.
- O fim do Python como motor do usuário; REPL e `--interpret` continuam existindo.
- Uma dona para desugaring/semântica (THIR); I4 estrutural (o backend não inventa tipo).
- Controle (blocos/phi/cleanup) sai do ad-hoc; ADR-0065 honrado.
- O congelamento por módulo dá um caminho mensurável para aposentar o Python sem big bang.
- O corpus dourado vira um contrato auditável; o self-host vira processo, não salto de fé.

### Negativas / custos

- O Python fica vivo por anos no checker; "congelar o Python" nunca é total sem o port.
- THIR é mais um contrato para versionar; snapshot e serialização custam.
- O oráculo perde independência no **desugaring** (THIR compartilhado); o diferencial passa a
  pegar codegen, não front. É a troca consciente por uma dona única da semântica.
- Golden drift é risco real; a disciplina de revisão é o preço.
- A ponte AST JSON é um contrato a mais e um round-trip a manter.
- O port do checker é o maior risco do programa (5,5k linhas, fluxo e narrowing).
- `run` AOT paga compilação no primeiro run e não serve para REPL.

### Neutras

- O I1 de hoje não muda; muda o ciclo de vida do oráculo no portão.
- O AST não morre: fica para tooling.
- O runtime C é o produto e não congela.
- O binário continua executável direto; `loxia run app` fica fora de contrato.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Status quo (tree-walk default, nativo opt-in) | O Python lento é o motor do usuário; dev/prod divergem; a duplicação cresce por feature. |
| Só nativo, matar o oráculo | Perde a referência independente; miscompile silencioso; o [ADR-0128](0128-contrato-de-motores.md) já rejeitou. |
| HIR completa (CFG/SSA) | O LLVM já otimiza; a dor é semântica, não otimização; custo alto para um alvo. |
| VM de bytecode agora | Segundo IR antes do THIR; o `run` é AOT; o REPL é best-effort; constrói antes da dor. |
| Python checker para sempre | Sem self-host; o Python nunca congela; o front fica pinado sem ponte. |
| Dev interpreta / prod compila | Dois caminhos; bug de codegen só em prod; o oposto do I1 na prática. |
| `loxia run app.bin` | O binário não depende da toolchain; sobrecarregar `run` confunde distribuição com execução. |
| Manter side tables por identidade de nó | Acoplamento invisível; o THIR com IDs estáveis é o mesmo trabalho com contrato. |

## Como verificar

- `loxia run` cold/warm: cache hit/miss, `--no-cache`, stdout/stderr/exit/args/stdin iguais
  ao `--interpret`; latência registrada no plano.
- `make test-backend` + `make test` verdes; I4 (`check` limpo compila); I1 no corpus.
- THIR: 100% do corpus via THIR; snapshot revisado; side tables removidas; `mypy`/camadas.
- IR de controle: `lower_exceptions`/`lower_enums` simplificados; corpus verde; `--emit=ll`
  verificado.
- Congelamento: painel de [`docs/plano-de-motores.md`](../plano-de-motores.md) com G1–G5;
  `PENDING` ≤ 5%; 4 semanas de soak; fuzz de 24 h.
- Golden: cada caso com stdout/stderr/exit em bytes; núcleo gerado pelo Python congelado,
  feature nova escrita da spec.
- Self-host: Nível 1 = front+interpretador+compilador Loxia rodando o corpus; Nível 2 =
  toolchain se construindo; Nível 3 = stage1 ≡ stage2.

Critério para revisitar: o checker portar antes do previsto; o REPL virar primeira classe
(reabre a VM); o THIR não cobrir um construto sem virar CFG (sinal de escopo errado); o
self-host exigir o checker antes do Nível 1 (antecipa F6); o `run` cold passar de 1 s em
programa pequeno (repensar cache/flag).

## Referências

- [`docs/plano-de-motores.md`](../plano-de-motores.md) — fases, portões, indicadores e painel.
- [`docs/roadmap.md`](../roadmap.md) — "Programa de motores".
- [`docs/spec/garantias.md`](../spec/garantias.md) — I1–I4.
- [`docs/tech/arquitetura.md`](../tech/arquitetura.md) — mapa de módulos.
- Issues F0/F1 do programa (ver o plano).
