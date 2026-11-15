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

## 2026-11-14 — GC Boehm (ADR-0074) e gate `mod.verify`

Intervalo: `HEAD..working tree` (decisão registrada e GC implementado).

- `docs/adr/0074-gc-boehm-e-contrato-de-memoria.md` — **novo**: Boehm, hard cap de 128 MiB,
  I1 até 64 MiB de memória viva, OOM com ponto não determinístico, kernel depois do GC e
  `mod.verify()` como gate; alternativas (conservador próprio, híbrido, shadow stack,
  statepoints, RC, arena) registradas.
- `docs/adr/0060-orcamento-de-memoria.md` — **superseded**: status e nota para o ADR-0074;
  o corpo fica como histórico.
- `docs/adr/0031-backend-nativo.md`, `docs/adr/0046-closures-celulas-l4.md` — **updated**:
  notas de atualização da arena para o Boehm e status L0–L6.
- `docs/adr/0071-primitivas-de-runtime.md` — **updated**: `cp_offsets` vai para o heap
  coletado; literais estáticos precisam de root/cache não coletável.
- `docs/adr/README.md`, `docs/decisoes.md` — **updated**: índice (0074, 0060 superseded) e
  linhas de memória/verificação de IR.
- `docs/spec/garantias.md` — **updated**: seção de memória agora descreve o GC Boehm
  implementado (hard cap 128 MiB, I1 até 64 MiB live, OOM sem ponto determinístico) e o
  limite de "programas acima do orçamento"; o bloco de níveis não mudou (nenhum caso novo).
- `TODO.md` — **updated**: §0/§0.1/§0.2 (L6 fechado, `mod.verify` e GC feitos), §9
  (M6 ✅, M7 com GC implementado e bench/corpus completo pendentes), §13.3/§13.7 (GC antes
  do kernel).
- `README.md`, `ESCOPO.md`, `docs/tech/arquitetura.md` — **updated**: status L0–L6,
  dependência de `libgc` para `--emit=exe`, contrato de memória, GC e `mod.verify`.
- `AGENTS.md` — **updated** (local): contrato de memória, status do backend e regra de não
  aumentar o cap.
- `src/backend/llvm_ir.py`, `src/backend/driver.py` — **updated**: `LLVMVerificationError`,
  `verify`/`verify_text`, `_verify` no driver e link `-lgc` com dica de instalação;
  `tests/test_ir_verify.py` **novo**.
- `runtime/runtime.c` — **updated**: arena substituída por `GC_malloc`/`GC_MALLOC_ATOMIC`,
  `GC_INIT`, hard cap de 128 MiB, OOM handler e supressão dos warnings do Boehm.
- `tests/test_backend.py` — **updated**: teste de reciclagem (80 MiB de lixo), roots
  (globais, classe, closure, containers, ciclo), `try`/`except` com GC e hard cap de
  memória; o helper de float linka `-lgc`.
- `.github/workflows/ci.yml`, `pyproject.toml` — **updated**: `libgc-dev` no runner e
  marcador `backend` mencionando a dependência.
- `CHANGELOG.md` — **updated**: GC e gate de verificação.

## 2026-11-14 — diagnósticos estruturados (ADR-0075)

Intervalo: `HEAD..HEAD` (diagnósticos; sem commit anterior para comparar no log).

- `docs/spec/erros.md` — **updated**: formato `arquivo:linha:col: error[CODIGO]`, envelope
  JSON v1, tabela de códigos por fase, determinismo e o que ainda falta.
- `docs/spec/semantica.md` — **updated**: referência morta ao `TODO.md` §3.1 trocada pelo
  ADR-0075 (mensagem de erro de runtime).
- `docs/adr/0003-diagnosticos-por-execucao.md` — **no-change** de conteúdo; só o link
  `Relacionados` passou a apontar para o ADR-0075.
- `IDEIAS.md` — **updated**: I-4 teve a parte de erros estruturados movida para o ADR-0075;
  sobrou a discussão de contratos (DbC).
- `TODO.md` — **updated**: §3 restaurada com o que falta em diagnósticos (o §3.1 antigo
  tinha sido removido do arquivo; o texto sobrevive no histórico do git).
- `README.md` — **updated**: flags `--error-format`, `--color`, `--max-errors` e exemplos.
- `docs/spec/erros.md`, `docs/spec/semantica.md`, `docs/decisoes.md`, `CHANGELOG.md` —
  **updated** na fase 2: o erro de runtime passou a usar o mesmo cabeçalho do diagnóstico
  de compilação, com `lox_panic(line, column, code, message)` no runtime C.
- `TODO.md` e `CHANGELOG.md` — **updated** ao corrigir os achados: `Any as T` checa a tag,
  exceções sintéticas têm aridade 1, a exceção não capturada carrega a mensagem,
  `is/as` sobre `Any` checa recursivamente containers/identidade de enum e o caminho
  estático/opcional (boxing de `T?`, literal aninhado, classe local) usa o mesmo matcher.
- `docs/spec/erros.md` — **updated** pelo novo `docs/_hooks/codes.py`: a tabela de códigos
  passou a ser gerada de `CODE_DESCRIPTIONS` (`make codes`), com `--check` em CI.

## 2026-11-14 — M7 fechado e L7b (O2 + bench nativo)

Intervalo: `3642c52..HEAD` (GC/M7, passes de otimização e benchmark nativo).

- `docs/spec/garantias.md` — **no-change**: GC, hard cap e orçamento de memória já estavam
  documentados; `-O2`/benchmark são desempenho, não alteram I1–I4.
- `docs/spec/lexico.md` — **no-change**: o scanner e os tokens não mudaram; a pendência de
  frescor vem de commits anteriores, sem alteração de comportamento léxico.
- `docs/spec/sintaxe.md` — **no-change**: parser/AST não mudaram neste intervalo.
- `README.md` — **updated**: `make bench-native` e status do L7b.
- `TODO.md` — **updated**: M7 marcado como concluído; L7b com `-O2`/bench feito; JIT no
  REPL virou pendência futura (P3) e restou a revisão dos erros de codegen.
- `CHANGELOG.md` — **updated**: passes `-O2`, benchmark nativo e classificação dos erros
  de codegen.
- `bench/README.md` — **novo**: metodologia e tabela de speedup interpretador × nativo.

## 2026-11-14 — Kernel 13.3/13.4 (strings e tabela de primitivas)

Intervalo: `HEAD..HEAD` (cache de code points, primitivas e benchmark).

- `docs/spec/semantica.md` — **updated**: `substr`, `join`, `charCodeAt` e
  `fromCodePoint` no prelúdio, com índices em code points e erros de limites.
- `docs/spec/garantias.md` — **pending**: bloco de níveis regenerado (`k0`); o commit fecha.
- `docs/decisoes.md`, `docs/spec/erros.md` — **no-change** de conteúdo de kernel; o diff é
  gerado/estado de ADR e não muda as garantias I1–I4.
- `docs/spec/lexico.md`, `docs/spec/sintaxe.md` — **no-change**: scanner/parser e gramática
  não foram tocados; a pendência de frescor vem de commits anteriores.
- `ADR-0071` — **updated**: status de implementação e medição `string_scan` (9,1 ms nativo).
- `ADR-0035` — **updated**: nota de atualização para o cache de code points.
- `bench/README.md` — **updated**: tabela e leitura do `string_scan`.

## 2026-11-14 — Kernel 13.2 (SO, args e I/O)

Intervalo: `HEAD..HEAD` (primitivas de SO e `main(argc, argv)`).

- `docs/spec/semantica.md` — **updated**: `args`, `io.*`, `os.*`, `time.*`, ambiente e
  códigos de `os.exit`.
- `TODO.md` — **updated**: tabela 13.2 marcada como entregue e ordem do kernel.
- `ADR-0071` — **updated**: status 13.2/13.3/13.4 e `main(argc, argv)`.
- `README.md`, `CHANGELOG.md` — **updated**: kernel v1 pronto e próximo passo imports/stdlib.
- `tests/test_kernel.py` — **novo**: args, getenv, os.exit e leitura/escrita de arquivo no
  interpretador; `test_backend.py` cobre `args()` no binário.

## 2026-11-14 — Imports/módulos (ADR-0073)

Intervalo: `HEAD..HEAD` (sintaxe, loader, privacidade, desugar e std mínima).

- `docs/spec/sintaxe.md` — **updated**: formas `import`/`from`, aliases, topo e módulo-arquivo.
- `docs/spec/semantica.md` — **updated**: módulo/pasta, `_` privado, sem módulo-valor e
  resolução pelo root do entry.
- `docs/adr/0073-imports-modulos.md` — **updated**: aceito e implementado; decisões de
  arquivo=módulo, pasta=namespace, `std.` reservado, `from`/`as` e desugar.
- `docs/adr/0066-orcamento-e-gate-sintatico.md` — **updated**: 27 palavras-chave e 11
  formas de statement.
- `docs/adr/README.md`, `docs/decisoes.md` — **updated**: status accepted.
- `tests/test_modules.py` — **novo**; coverage de from/namespace/privado/ciclo/declarações.

## 2026-11-14 — T1 base: std.strings e std.lists

Intervalo: `HEAD..HEAD` (primeiros módulos T1 sobre imports/kernel).

- `std/strings.lox`, `std/lists.lox` — **novos**: funções em Lox puro; privacidade `_`
  dentro do módulo e uso de `substr`/`join`/`charCodeAt`.
- `docs/spec/semantica.md` — **updated**: API T1 e garantia de determinismo.
- `TODO.md` — **updated**: T1 em andamento; strings base completa e lists base parcial.
- `tests/cases/std_strings.lox`, `std_lists.lox` — **novos** no nível `t1`.
- `CHANGELOG.md` — **updated**: T1 base.

## 2026-11-14 — `std.lists.sort` e lacunas T1

Intervalo: `HEAD..HEAD` (decisão do comparador e funções restantes de lists).

- `docs/adr/0076-std-lists-sort.md` — **novo**: comparador de três vias, merge sort
  estável, lista nova; `sortBy`/`groupBy` adiados.
- `docs/spec/semantica.md` — **updated**: contrato de `sort` e utilitários genéricos.
- `TODO.md`, `CHANGELOG.md`, `docs/adr/README.md`, `docs/decisoes.md` — **updated**.
- `std/lists.lox` — **updated**: `sort`, `zip`, `flatten`, `flatMap`, `unique`, `chunk`,
  `partition`; testes no caso `t1`.

## 2026-11-15 — cleanup de `try`/`return` e bordas do runtime

Intervalo: `HEAD..HEAD` (frame de `try` no `return`, igualdade de mapa e `charCodeAt`).

- `docs/spec/garantias.md` — **updated**: bloco de níveis regenerado; 3 casos novos em
  `l6` (`try_return_cleanup`, `map_equality_depth`, `char_code_at_bounds`).
- `docs/spec/erros.md` — **updated**: erro de runtime dentro de `try` é capturável como
  `LoxRuntimeError` e `e.message` funciona; `Result` é alternativa explícita.
- `docs/spec/lexico.md` — **no-change**: scanner, keywords, `token_type` e `tokens` não
  mudaram; o léxico continua o mesmo.

## 2026-11-15 — T1 completa (maps, numeric, asserts, results)

Intervalo: `HEAD..HEAD` (stdlib T1, inferência de `T?`, math em contexto esperado).

- `docs/spec/semantica.md` — **updated**: seção `stdlib T1` com `std.maps`, `std.numeric`,
  `std.asserts` e `std.results`, semântica de lista vazia/erros e limite `Map[String, V]`;
  `sources:` ganhou `std/**`.
- `docs/spec/garantias.md` — **updated**: bloco de níveis regenerado; 4 casos em `t1` e
  `math_optional` em `l6`.
- `docs/spec/erros.md` — **no-change**: catálogo de códigos e mensagens não mudou; as
  correções de inferência no checker (`T?` × `Int?` e tipo de chamada em contexto
  esperado) não alteram diagnóstico.
- `README.md`, `TODO.md`, `CHANGELOG.md`, `TIPOS.md` — **updated**: T1 concluída, próximo
  é T2; lacuna de enum genérico em lambda registrada.

## 2026-11-15 — ADR-0077: limite de pilha (proposto)

Intervalo: `HEAD..HEAD` (decisão de profundidade de chamadas; código não implementado).

- `docs/adr/0077-limite-de-pilha.md` — **novo** (proposed): limite compartilhado de
  1.000 chamadas Lox, erro `R1015`/`Stack overflow.`, restauração da profundidade no
  unwinding e medições dos dois motores.
- `docs/adr/README.md` — **updated**: linha 0077 no índice.
- `TODO.md` — **updated**: contador de pilha na fila depois de T2; stack trace depende
  do ADR.
- `docs/decisoes.md` — **no-change**: ADR-0077 está `proposed`; o resumo só lista
  decisões fechadas.
- `docs/spec/erros.md`, `docs/spec/lexico.md` — **no-change**: sem mudança de
  comportamento, código de erro ou léxico nesta rodada.

## 2026-11-15 — Loxia/`.lx` e `RuntimeError` (ADR-0078)

Intervalo: `HEAD..HEAD` (renomeação de pacote, extensão e classe embutida; sem mudança de
semântica).

- `docs/adr/0078-nome-loxia-extensao-lx.md` — **novo** (accepted): nome, extensão, camadas
  de nomenclatura e a alternativa `LoxiaError` rejeitada.
- `docs/adr/README.md` — **updated**: linha 0078 no índice.
- `docs/decisoes.md` — **updated**: linha de Exceções com `RuntimeError` + nova linha
  "Nome e extensão".
- `docs/spec/semantica.md`, `docs/spec/erros.md` — **updated**: `RuntimeError` no lugar de
  `LoxRuntimeError` (nomes de classe embutida; nenhum comportamento mudou).
- `docs/tech/arquitetura.md` — **updated**: links para `loxia/`, `Loxia.run` e o nome
  embutido; a classe Python `LoxRuntimeError` continua documentada como interna.
- `README.md`, `TODO.md`, `CHANGELOG.md` — **updated**: título, comandos, extensão e item
  §11 de nome/extensão fechado.
- `docs/adr/0003`, `0042`, `0062`, `0072`, `0077`, `0014`, `0026` — **updated** (só
  cabeçalho): nota "atualizado por ADR-0078"; corpo histórico preservado.
- `docs/spec/lexico.md`, `sintaxe.md`, `garantias.md` — **no-change**: renomear a extensão
  e a classe embutida não altera léxico, gramática nem as garantias I1–I4.
