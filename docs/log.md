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
4. Feche o intervalo com um marcador no fim deste arquivo: `<!-- triaged: <sha> -->`.
   O `freshness.py` ignora commits até esse SHA (e ignora mudanças não commitadas, que
   ainda não são fato). Sem o marcador, `no-change` nunca silencia o relatório.
5. Se o código ganhou/removeu um módulo, ajuste as `sources:` da página no mesmo commit —
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
- Sem mudança em `loxia_core/`, `runtime/` ou `docs/spec/`: 0071/0072 são plano; a spec só muda
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
- `loxia_core/backend/llvm_ir.py`, `loxia_core/backend/driver.py` — **updated**: `LLVMVerificationError`,
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

## 2026-11-15 — Stdlib T2 (ADR-0079)

Intervalo: `d0804a5..HEAD` (nove módulos em `std/`, kernel em 17 primitivas,
campos-container, `str(Any)` e validação de chave de `Map` no runtime C).

- `docs/adr/0079-stdlib-t2.md` — **novo** (accepted): kernel T2, ABI de campo-container,
  `str(Any)`, `R1014` no C, `Set[T]` com `Map[Any, Bool]` e a superfície dos módulos.
- `docs/adr/README.md`, `docs/adr/0071-primitivas-de-runtime.md` — **updated**: linha no
  índice e nota "atualizado por ADR-0079" (teto 15 → 17; corpo histórico preservado).
- `docs/spec/semantica.md` — **updated**: seção `stdlib T2` com contrato de cada módulo,
  ambiente × determinístico e a lacuna de `Set[Float]`.
- `docs/spec/garantias.md` — **updated**: funções ambiente (incluindo `std.fs`, leitura de
  `std.io`, `time.*`) explicitamente fora do I3; bloco de níveis regenerado com `t2`.
- `docs/decisoes.md` — **updated**: cinco linhas (kernel T2, campos-container, `str(Any)`,
  chave de `Map` no C, stdlib T2).
- `TODO.md`, `README.md` — **updated**: T2 marcada como concluída; próximo é o limite de
  pilha; kernel documentado em 17 primitivas.
- `editors/` — **updated** (`make grammar`): `fs` entrou em `BUILTIN_NAMES`; a gramática é
  gerada, não editada à mão.
- `docs/spec/{lexico,sintaxe,erros}.md` — **no-change**: nenhuma sintaxe, palavra-chave ou
  código de diagnóstico novo.

## 2026-11-15 — Cache de build do runtime (infra)

Intervalo: `c4a4511..HEAD` (cache do `runtime.o` no driver + `make test-fast`/
`check-fast`; sem mudança de comportamento observável).

- `docs/spec/garantias.md` — **no-change**: I1–I4, canais e memória não mudaram; o cache
  do `runtime.o` afeta só o tempo de build e não entra na saída (caminho de erro continua
  sanitizado para `<build>`).
- `docs/tech/arquitetura.md` — **updated**: parágrafo do cache no pipeline nativo e o
  motivo (o backend dominava a suíte de testes).
- `README.md`, `Makefile`, `AGENTS.md` — **updated**: `make test-fast`/`check-fast` e
  `LOX_BUILD_CACHE` documentados.

## 2026-11-15 — Nomenclatura: traits → interfaces (ADR-0080)

Intervalo: `HEAD`..working tree (renomeação antes da implementação; sem mudança de
comportamento observável).

- `docs/adr/0080-interfaces-nominais-implementacao.md` — **novo** (accepted, plano):
  desenho da v1 (sintaxe, tipos, defaults, conflitos, backend B1/B2) com o conceito
  chamado de **interface**, não "trait".
- `docs/adr/0038-traits-nominais.md` — **updated** (só cabeçalho): status
  `superseded by ADR-0080 (nomenclatura)` e nota; corpo histórico preservado com "trait".
- `docs/adr/README.md` — **updated**: linhas 0038 e 0080 no índice.
- `docs/decisoes.md` — **updated**: linha "Interfaces (ex-traits)" apontando 0038+0080;
  o freeze passa a dizer "interfaces".
- `TODO.md`, `TIPOS.md`, `ESCOPO.md`, `IDEIAS.md`, `README.md` — **updated**: nomenclatura
  viva; o item do Lox2 continua identificado como "traits".
- `docs/spec/semantica.md` — **updated**: "até existir interface" na seção de generics
  (nenhuma gramática nova).
- `docs/spec/garantias.md` — **no-change**: a renomeação não muda I1–I4, corpus, canais
  nem o contrato de memória.
- `AGENTS.md` — **updated** (local): status e freeze com "interfaces".

## 2026-11-15 — Interfaces nominais v1 (ADR-0080, fases T1–T8)

Intervalo: `HEAD`..working tree (`interface`/`implements`, checker/tree-walk e backend B1).

- `docs/spec/sintaxe.md` — **updated**: EBNF de `interfaceDecl`/`implements`, abstrato ×
  default e `implements` contextual.
- `docs/spec/semantica.md` — **updated**: seção Interfaces (nominal, conformidade,
  defaults, ordem de resolução, `is`/`as` recusado, lacuna B1).
- `docs/spec/lexico.md` — **updated**: `interface` na lista de palavras-chave.
- `docs/spec/garantias.md` — **updated** (`make docs-sync`): dois casos novos em
  `PENDING` (interfaces no backend B1).
- `docs/spec/erros.md` — **no-change**: nenhum código de diagnóstico novo; a feature reusa
  `E3015`/`E3017`/`E3005`/`E1005`/`E1004`/`E2005`.
- `docs/adr/0066-orcamento-e-gate-sintatico.md` — **updated**: placar 28 palavras-chave e
  6 formas de declaração.
- `docs/adr/0080-interfaces-nominais-implementacao.md` — **updated**: status implementado
  (tree-walk/checker + B1) e nota de entrega.
- `docs/decisoes.md`, `TODO.md`, `TIPOS.md`, `ESCOPO.md`, `README.md` — **updated**:
  status da v1 e pendência da ABI B2.
- `editors/` — **updated** (`make grammar`): `interface` no grupo de declaração.
- `docs/tech/arquitetura.md` — **updated**: `LoxInterface` na tabela de módulos.
- `AGENTS.md` — **updated** (local): status da feature.

## 2026-11-15 — Interfaces no backend (ADR-0080, fase B2)

Intervalo: `HEAD`..working tree (ABI `interface_id` + `itab`, dispatch e casos no
diferencial; sem mudança de sintaxe).

- `docs/spec/garantias.md` — **updated** (`make docs-sync`): **136 casos** em `LEVELS`,
  **0 em `PENDING`**; `interfaces.lx` e `interface_decl.lx` promovidos.
- `docs/spec/semantica.md` — **updated**: conformidade por assinatura exata e ABI B2
  (`itab` no descritor); a lacuna B1 sai da descrição corrente.
- `docs/adr/0080-interfaces-nominais-implementacao.md` — **updated**: B2 implementada,
  B1 marcada como histórico e assinatura exata documentada.
- `docs/spec/erros.md` — **no-change**: nenhum código de diagnóstico novo.
- `docs/decisoes.md`, `TODO.md`, `TIPOS.md`, `ESCOPO.md`, `README.md`, `AGENTS.md` —
  **updated**: interfaces implementadas no tree-walk/checker e no backend; falta só
  constraints.

## 2026-11-15 — Constraints em funções genéricas (ADR-0081)

Intervalo: `HEAD`..working tree (sintaxe `T: Ord + Num + Interface`, checker, stdlib e
caso no corpus; backend inalterado).

- `docs/adr/0081-constraints-generics.md` — **new**: desenho de bounds, `Ord`/`Num`,
  regras de operador, checagem na chamada, limites da v1 e stdlib.
- `docs/spec/sintaxe.md` — **updated**: `functionTypeParameters`/`typeParameter`/
  `constraint` no EBNF e prosa (só funções aceitam bounds).
- `docs/spec/semantica.md` — **updated**: `Ord`/`Num`/interface, operadores, métodos e
  checagem de type arguments; classes/enums sem bounds.
- `docs/spec/garantias.md` — **updated** (`make docs-sync`): **137 casos** em `LEVELS`,
  **0 em `PENDING`**; `generic_constraints.lx` no `t7`.
- `docs/spec/erros.md` — **updated** (`make docs-sync`): contagem de `E3001` mudou com
  os bounds; nenhum código novo.
- `docs/decisoes.md`, `TODO.md`, `TIPOS.md`, `ESCOPO.md`, `README.md`, `AGENTS.md` —
  **updated**: constraints de função implementadas; classes/enums e interfaces genéricas
  seguem pós-MVP.
- `docs/adr/0038-traits-nominais.md` e `docs/adr/README.md` — **updated**: constraints
  entregues pelo ADR-0081, sem reabrir o modelo nominal.

## 2026-11-15 — Iterador de usuário no `for-in` (ADR-0082)

Intervalo: `HEAD`..working tree (protocolo `iter()`/`next() -> T?`, checker, tree-walk,
backend e caso no corpus; sem sintaxe nova).

- `docs/adr/0082-iterador-de-usuario.md` — **new**: protocolo estrutural, regras de
  checker, runtime, backend e limites (`nil` como sentinela, iterador stateful).
- `docs/adr/0007-ranges-e-iteracao.md` — **updated**: status aponta para o ADR-0082 e a
  fonte fechada deixa de ser a única.
- `docs/spec/semantica.md` — **updated**: fontes de `for-in`, protocolo de usuário,
  erros e `nil` como fim.
- `docs/spec/erros.md` — **updated** (`make docs-sync`): contagem e mensagens de iterador.
- `docs/spec/garantias.md` — **updated** (`make docs-sync`): **138 casos** em `LEVELS`,
  **0 em `PENDING`**; `user_iterator.lx` no `l6`.
- `docs/decisoes.md`, `TODO.md`, `ESCOPO.md`, `README.md`, `AGENTS.md` — **updated**:
  iterador de usuário implementado no tree-walk/checker/backend.

## 2026-11-15 — Variádicos `...args` e spread final (ADR-0083)

Intervalo: `HEAD`..working tree (token `...`, parâmetro/spread, checker, tree-walk,
backend e stdlib; `fmt.format` migrado).

- `docs/adr/0083-variadicos.md` — **new**: assinatura `...xs: T`, spread final, regras,
  ABI, stdlib e alternativas.
- `docs/spec/sintaxe.md` — **updated**: `parameter`/`arguments`/`spread` no EBNF e prosa.
- `docs/spec/semantica.md` — **updated**: variádicos, spread, `init` fora e `FnTy`.
- `docs/spec/erros.md` — **updated**: mensagens de variádico/spread.
- `docs/spec/garantias.md` — **updated** (`make docs-sync`): **139 casos** em `LEVELS`,
  **0 em `PENDING`**; `variadic.lx` no `l6`.
- `docs/adr/0072-stdlib-batteries.md` — **updated**: `fmt.format` agora variádico.
- `docs/decisoes.md`, `TODO.md`, `ESCOPO.md`, `README.md`, `AGENTS.md` — **updated**:
  variádicos e `fmt.format`.
- `editors/` — **updated** (`make grammar`): `...` como operador.

## 2026-11-15 — `type` alias transparente (ADR-0084)

Intervalo: `HEAD`..working tree (`type Nome = Tipo`, resolução no checker, tree-walk,
backend e módulos; sem runtime novo).

- `docs/adr/0084-type-alias.md` — **new**: implementação do item 4 do ADR-0039,
  transparência, forward references/ciclos, backend, módulos e limites.
- `docs/adr/0039-decisoes-tipos-pendentes.md` — **updated**: item 4 aponta para a
  implementação.
- `docs/spec/sintaxe.md` — **updated**: `typeAliasDecl` no EBNF e prosa.
- `docs/spec/semantica.md` — **updated**: alias transparente, expansão e limites.
- `docs/spec/erros.md` — **updated**: mensagens de alias.
- `docs/spec/garantias.md` — **updated** (`make docs-sync`): **140 casos** em `LEVELS`,
  **0 em `PENDING`**; `type_alias.lx` no `l6`.
- `docs/decisoes.md`, `TODO.md`, `TIPOS.md`, `ESCOPO.md`, `README.md`, `AGENTS.md` —
  **updated**: type alias implementado.

## 2026-11-15 — `print` como função builtin (ADR-0085)

Intervalo: `HEAD`..working tree (statement/palavra-chave removidos, `print(valor)` nos dois
motores; migração mecânica de corpus, suíte oficial, exemplos, stdlib e bench).

- `docs/adr/0085-print-como-funcao.md` — **new**: `Any -> Nil`, REPL, backend, migração e
  orçamento (27 palavras-chave, 10 statements).
- `docs/adr/0026-freeze-1.0.md` — **updated**: item 4 substituído; histórico mantido.
- `docs/adr/0066-orcamento-e-gate-sintatico.md` — **updated**: placar 28→27 e 11→10.
- `docs/spec/sintaxe.md` — **updated**: `printStmt` removido; `print(valor)` builtin.
- `docs/spec/semantica.md` — **updated**: `print` como função, REPL e tabela de statements.
- `docs/spec/lexico.md`/`erros.md` — **updated**: keyword e mensagem de `print` removidas.
- `docs/spec/garantias.md` — **updated** (`make docs-sync`): **141 casos** em `LEVELS`,
  **0 em `PENDING`**; `print_function.lx` no `l6`.
- `docs/decisoes.md`, `TODO.md`, `ESCOPO.md`, `README.md`, `AGENTS.md`,
  `tests/official/README.md` — **updated**: `print` função e migração.
- `tests/official/cases`, `tests/cases`, `examples`, `std`, `bench` — **updated**:
  1.265 chamadas `print` migradas em 282 arquivos; testes Python e docs ajustados.

## 2026-11-15 — Narrowing: captura de `var` e merge de fluxo (ADR-0086)

Intervalo: `HEAD`..working tree (checker/resolver; sem mudança de runtime/backend).

- `docs/adr/0086-narrowing-captura-e-merge.md` — **new**: captura/invalidação de `var`
  mutável e merge estruturado de `if`/`while`/`for-in`/`try`.
- ADR-0018/0032/0045 — **updated**: limitações e status; CFG/aliasing completo continua
  fora.
- `docs/spec/semantica.md` — **updated**: chamadas de usuário invalidam capturadas,
  funções começam sem refinos e ramos fazem merge.
- `TODO.md` §8, `TIPOS.md`, `docs/decisoes.md` — **updated**: item de uniões/narrowing
  fechado com as limitações declaradas.
- `tests/test_checker.py` — **updated**: casos de captura local/global, iterador de
  usuário, chamadas nativas, merge de ramos, campos, `for-in` e `try`.
- `docs/spec/erros.md` / `docs/spec/garantias.md` — **no-change**: mudança é só no
  checker; nenhuma mensagem, corpus ou contagem de casos mudou.


## 2026-11-15 — Operator overloading estacionado

- `TODO.md` §8 — **updated**: linha de operator overloading removida; não é pendência de
  implementação.
- `IDEIAS.md` — **updated**: nova seção I-8 (ideias soltas), com operator overloading,
  motivos, escopo mínimo se um dia voltar e critério de reabertura.
- `ESCOPO.md` — **updated**: operator overloading aponta para IDEIAS I-8.


## 2026-11-15 — Trailing closure, match estrutural, extension methods e metaclasses estacionados

- `TODO.md` §8 — **updated**: removidas as linhas `trailing closure`,
  `match estrutural em uniões`, `extension methods` e
  `classes como valores / metaclasses`.
- `IDEIAS.md` — **updated**: I-8 ganhou as quatro ideias com utilidade, custos,
  alternativas e critério de reabertura.
- `ESCOPO.md` — **updated**: os itens apontam para IDEIAS I-8 ou para “fora por enquanto”.

## 2026-11-15 — Limite de pilha 10.000/64 MiB e heap 512 MiB (ADR-0077/ADR-0087)

Intervalo: `HEAD`..working tree (runtime, interpreter, backend, CLI, testes e docs).

- `docs/adr/0077-limite-de-pilha.md` — **updated**: contrato de 10.000 chamadas / 64 MiB,
  correção da medição (limite de frames do Python, não pilha C), contagem ctor+init e
  restauração no unwinding.
- `docs/adr/0087-heap-cap-e-self-hosting.md` — **new**: default de 512 MiB,
  `--max-heap` de build, I1 inalterado em 64 MiB live e nota de self-hosting.
- `docs/adr/0074-gc-boehm-e-contrato-de-memoria.md`, `docs/adr/README.md` — **updated**:
  nota de atualização do cap e índice/status.
- `docs/spec/garantias.md` — **updated**: orçamento de pilha (10k/64 MiB/R1015) e heap
  512 MiB/`--max-heap`; I1 continua em 64 MiB live.
- `docs/spec/erros.md` — **updated**: `R1015` no catálogo gerado.
- `docs/spec/semantica.md` — **updated**: limite de ativações Lox, R1015 catchable e
  restauração por `try`/`finally`.
- `docs/tech/arquitetura.md` — **updated**: limitações de recursão e memória.
- `docs/decisoes.md`, `TODO.md`, `ESCOPO.md`, `README.md`, `CHANGELOG.md`, `AGENTS.md` —
  **updated**: números, fila, flags e registro executivo.
- `tests/cases/stack_*.lx`, `tests/corpus_manifest.py`, `tests/test_backend.py`,
  `tests/test_cli.py` — **updated**: corpus e testes de borda, reserva de pilha e
  override de heap.

## 2026-11-15 — rename `src` → `loxia_core`

Renomeado o pacote do motor (`git mv src loxia_core`): 80 arquivos Python com imports
`from loxia_core.*`, 80 documentos com caminhos atualizados, `pyproject.toml` (mypy),
loader (`STD_ROOT`), `editors/build_grammar.py`, `docs/_hooks/{codes,freshness}.py` e o
teste de sombreamento da stdlib. Resolve a dívida registrada no
[ADR-0088](../docs/adr/0088-distribuicao-e-raizes-de-modulo.md) (pacote top-level `src` no
wheel). Nenhum comportamento mudou: suíte completa verde, incluindo o backend.

## 2026-11-15 — empacotamento (ADR-0088, parte entregue)

`pyproject.toml` ganhou `[build-system]` (hatchling), `[project.scripts] loxia`, metadados e
`force-include` de `std/` e `runtime/` para dentro de `loxia_core`. O novo
`loxia_core/bundle.py` resolve dev (raiz do repo) × instalado (`importlib.resources`), e o
loader/driver usam ele. Verificado com wheel real: `loxia --version`, `import std.json`,
`--emit=ll` e `--emit=exe` (runtime empacotado) fora do clone. README ganhou a seção
"Instalar"; workflow de release com Trusted Publishing.

## 2026-11-15 — triagem pós-empacotamento

Intervalo: mudanças do empacotamento (ADR-0088) ainda não commitadas no momento da
triagem; o marcador `<!-- triaged: <sha> -->` deve ser adicionado no commit que fecha
este lote.

- `docs/spec/garantias.md` — **no-change**: `loxia_core/bundle.py` mudou a *localização*
  de `std/` e `runtime.c` (dev × wheel), não o contrato de I1–I4 nem os orçamentos.
- `docs/spec/semantica.md` — **no-change**: a mudança em `loxia_core/loader/**` é de
  resolução de bundle; a semântica de módulos e imports não mudou.
- `docs/decisoes.md` — **updated**: linha de distribuição passa a dizer que o
  empacotamento foi entregue (comando + `std/` + `runtime.c` no wheel).

## 2026-11-15 — fonte de módulo nos diagnósticos (`Token.file`)

Intervalo: `HEAD`..working tree. Diagnóstico de compilação em módulo passou a apontar o
arquivo do módulo (com trecho/caret e `span.file` no JSON); runtime e nativo intocados,
então o I1 não muda. O marcador `<!-- triaged: <sha> -->` fica para o commit que fechar o
lote (junto do empacotamento acima).

- `docs/spec/erros.md` — **updated**: caminho do módulo e `std/...`, span por token e
  limite declarado do runtime (arquivo da entrada até o frame stack).
- `docs/tech/arquitetura.md` — **updated**: as seções de diagnósticos/limitações diziam
  “sem spans, códigos ou JSON”; reescritas para o estado do ADR-0075.
- `TODO.md` — **updated**: §0.2 item 5 e §11.9 (fonte de módulo entregue; resta `..`).

## 2026-11-15 — stack trace de runtime (ADR-0089)

Intervalo: `HEAD`..working tree. Erro de runtime não capturado passa a imprimir frames
(nome + call site) nos dois motores, com recorte 5+5+elisão; `R1015` ganha posição e o
runtime em módulo aponta o módulo. O marcador `<!-- triaged: <sha> -->` fica para o commit
que fechar o lote.

- `docs/adr/0089-stack-trace-de-runtime.md` — **new**: formato, captura, ABI, recorte,
  revisão do R1015 e o que fica de fora.
- `docs/adr/0077-limite-de-pilha.md` — **updated** (nota): R1015 com posição e frames;
  limite 10.000/64 MiB inalterado.
- `docs/spec/erros.md` — **updated**: stack trace, `trace` no JSON, `short` sem frames,
  runtime em módulo.
- `docs/spec/garantias.md` — **updated**: I1 inclui o trace em stderr; R1015 com posição;
  stack trace saiu da lista de fora-de-garantia.
- `docs/spec/semantica.md` — **updated**: R1015 com posição/trace e exceção não capturada
  com frames.
- `docs/tech/arquitetura.md` — **updated**: captura no tree-walk × array no nativo.
- `docs/decisoes.md`, `docs/adr/README.md`, `README.md`, `CHANGELOG.md`, `TODO.md` —
  **updated**: índice, resumo, diagnóstico de runtime, changelog e fila.
- `docs/spec/lexico.md` — **updated**: a página ainda dizia que não havia módulos e que
  "um arquivo `.lx` é um programa"; agora reflete arquivo=módulo (ADR-0073). O resto da
  página (regras léxicas) não mudou com `Token.file`, então não foi tocado.

## 2026-11-15 — labels, notas e sugestão nos diagnósticos

Intervalo: `HEAD`..working tree. O modelo já tinha `labels`/`notes`/`help`; esta rodada
adiciona produtores (E2001/E2002/E3003) e o render humano do segundo trecho. Sem ADR: é o
uso do contrato do ADR-0075, não uma decisão nova.

- `docs/spec/erros.md` — **updated**: seção de labels/notas/ajuda com exemplos e a regra
  do `short`/JSON; catálogo de códigos não mudou.
- `CHANGELOG.md` — **updated**: item de diagnóstico com labels/sugestão.
- `docs/log.md` — **updated**: esta triagem.

## 2026-11-15 — ADRs de ecossistema: LSP, docs, estilo/formatter e CLI

Intervalo: `HEAD`..working tree. Decisões de ecossistema fechadas com o dono do projeto;
tudo é **plano** (implementação pendente), então nenhuma página de `docs/spec/` mudou.

- `docs/adr/0090-lsp-escopo-e-hospedagem.md` — **new**: LSP em Python no repo, JSON-RPC à
  mão, fases LSP-0/1/2, mapeamento e paridade.
- `docs/adr/0091-doc-comments-e-geracao-de-docs.md` — **new**: `///`, Markdown, anexação,
  API em inglês, `loxia doc`, registry de builtins e política da stdlib.
- `docs/adr/0092-estilo-e-formatter.md` — **new**: nomes, perfil 2/100/K&R/`;`/`fn`, escopo
  minimal, fases Python → Lox e dogfood após T3.
- `docs/adr/0093-cli-agent-friendly-e-reparo.md` — **new**: subcomandos, JSONL/watch,
  timeout `C0001`, warnings `W1xxx`/`-Werror` e schema/loop de `fixes[]`.
- `docs/adr/0066`, `docs/adr/0075` — **updated**: notas de atualização (doc comment e
  fixes/C/W).
- `docs/adr/README.md`, `docs/decisoes.md`, `TODO.md` — **updated**: índice, resumo e fila
  §0.2/§7/§10/§13.7/§14.
- `docs/spec/garantias.md` — **no-change**: os ADRs 0090–0093 são planos; I1–I4 e os
  orçamentos atuais não mudam até a implementação.
- `docs/spec/semantica.md` — **no-change**: `///`, `loxia doc`, CLI/LSP ainda não são
  comportamento implementado; a spec continua descrevendo o estado atual.


<!-- triaged: 3cacb66 -->

## 2026-11-16 — CLI agent-friendly (core), warnings e C0001

Intervalo: `HEAD`..working tree. Implementa a primeira fatia do ADR-0093: subcomandos
aditivos, `capabilities`/`explain`, `--json`/`--json-lines`, `--stdin`, `--timeout`
(`C0001`/124), `--watch` restrito a `check` e `W1001`/`-Werror`. `fixes[]`, `W1002`,
`fmt`, `doc` e `lsp` continuam pendentes.

- `loxia/cli.py` — **updated**: subcomandos, JSONL, timeout, watch, stdin, warnings.
- `loxia_core/diagnostics/codes.py` — **updated**: `C0001`, `W1001`.
- `loxia_core/diagnostics/error_reporter.py` — **updated**: `warning`/`werror`.
- `loxia_core/semantics/resolver.py` — **updated**: local não lido.
- `loxia_core/diagnostics/render.py` — **updated**: `diagnostic_json` público.
- `docs/spec/erros.md` — **updated**: fases CLI, warnings e `--json-lines`/timeout.
- `README.md`, `docs/tech/arquitetura.md`, `CHANGELOG.md`, `TODO.md`,
  `docs/adr/0093`, `docs/adr/README.md`, `docs/decisoes.md` — **updated**: contrato e status.
- `tests/test_cli.py`, `tests/test_docs_consistency.py` — **updated**: cobertura nova.

<!-- triaged: 20de298 -->

## 2026-11-16 — doc comments `///` e `loxia doc`

Intervalo: `HEAD`..working tree. Implementa a primeira fatia do ADR-0091: doc comments
`///` no scanner/AST/parser, `loxia doc` Markdown/JSON e scope de documentação na grammar.
Docs obrigatórias da stdlib/builtins e a geração de `docs/stdlib/` continuam pendentes.

- `loxia_core/frontend/tokens.py`, `scanner.py`, `parser.py`, `stmt.py` — **updated**:
  `doc` no token/AST e anexação por linha imediatamente anterior.
- `loxia/docgen.py` — **new**: extração e render Markdown/JSON.
- `loxia/cli.py` — **updated**: subcomando `doc` (`--stdin`, `--json`).
- `editors/build_grammar.py` e artefatos gerados — **updated**: scope
  `comment.line.documentation.loxia`; `tests/test_editor_grammar.py` ajustado.
- `docs/spec/lexico.md` — **updated**: `///` e regra de vínculo.
- `README.md`, `CHANGELOG.md`, `TODO.md`, `docs/adr/0091`, `docs/adr/README.md`,
  `docs/decisoes.md`, `docs/tech/arquitetura.md` — **updated**: contrato/status.
- `tests/test_cli.py` — **updated**: cobertura de doc/Markdown/JSON/anexação.

<!-- triaged: ed30798 -->

## 2026-11-16 — estilo e formatter mínimo

Intervalo: `HEAD`..working tree. Implementa a primeira fatia do ADR-0092: guia de estilo
normativo e `loxia fmt` Python mínimo (indentação de bloco, `;` de fim de linha, newline
final, preservação de strings/comentários), com `--check`/`--stdin`. `fn` em método,
trailing comma/reflow e o dogfood Lox continuam pendentes.

- `docs/guia-estilo.md` — **new**: nomes, formatação, imports e doc comments.
- `loxia/formatter.py` — **new**: formatter Python de referência.
- `loxia/cli.py` — **updated**: subcomando `fmt`.
- `tests/test_formatter.py` — **new**: idempotência, check/stdin, strings/comentários.
- `docs/adr/0092`, `docs/adr/README.md`, `docs/decisoes.md`, `TODO.md`, `CHANGELOG.md`,
  `README.md`, `docs/tech/arquitetura.md` — **updated**: status/contrato.

<!-- triaged: 18f0697 -->

## 2026-11-16 — LSP-0

Intervalo: `HEAD`..working tree. Implementa a primeira fatia do ADR-0090: servidor
`loxia lsp` em Python com JSON-RPC stdio à mão, full sync, `publishDiagnostics` e
`documentSymbol`; LSP-1/2 (hover/definition/completion) continuam pendentes.

- `loxia/lsp.py` — **new**: servidor LSP-0.
- `loxia/cli.py` — **updated**: subcomando `lsp`.
- `tests/test_lsp.py` — **new**: transcrições initialize/didOpen/diagnostics/change/
  documentSymbol/shutdown.
- `README.md`, `CHANGELOG.md`, `TODO.md`, `docs/adr/0090`, `docs/adr/README.md`,
  `docs/decisoes.md`, `docs/tech/arquitetura.md` — **updated**: contrato/status.

## 2026-11-16 — LSP-1 básico (hover/definition)

Intervalo: `HEAD`..working tree. Complementa o LSP-0 com `SymbolIndex` e
`Resolver.references`: hover de assinatura/tipo/doc e go-to-definition para variáveis,
funções, classes, campos/métodos, enums e variantes. LSP-2 segue pendente.

- `loxia/symbols.py` — **new**: índice de declarações/referências/tipos.
- `loxia_core/semantics/resolver.py` — **updated**: `references` uso→declaração.
- `loxia/cli.py` — **updated**: estado da última análise para o LSP.
- `loxia/lsp.py` — **updated**: hover/definition e capabilities.
- `tests/test_lsp.py` — **updated**: hover/definition de função, variável e campo.
- `README.md`, `CHANGELOG.md`, `TODO.md`, `docs/adr/0090`, `docs/adr/README.md`,
  `docs/decisoes.md`, `docs/tech/arquitetura.md` — **updated**: status.
- `docs/spec/erros.md` — **no-change**: `Resolver.references` é estado interno do LSP;
  catálogo, spans e exit codes de erro não mudaram.

<!-- triaged: fab93f6 -->

## 2026-11-16 — docs da stdlib e builtins

Intervalo: `HEAD`..working tree. Implementa a fatia de documentação do ADR-0091: doc
comments `///` em toda a API pública de `std/*.lx`, registry de builtins e geração de
`docs/stdlib/` (índice + 15 módulos + builtins) por `docs/_hooks/stdlib.py`, com
`make stdlib-docs` e teste de cobertura.

- `std/*.lx` — **updated**: doc comments English da API pública.
- `loxia/builtins_docs.py` — **new**: registry de builtins.
- `docs/_hooks/stdlib.py`, `docs/stdlib/*` — **new/updated**: geração e páginas.
- `Makefile`, `README.md`, `docs/spec/semantica.md`, `CHANGELOG.md`, `TODO.md`,
  `docs/adr/0091`, `docs/decisoes.md`, `docs/tech/arquitetura.md` — **updated**.
- `tests/test_stdlib_docs.py` — **new**: cobertura e drift.

<!-- triaged: 43f76a2 -->

## 2026-11-16 — LSP-2 parcial

Intervalo: `HEAD`..working tree. Complementa o LSP com `completion` (global e por membro),
`signatureHelp`, `documentFormatting` (reusa `loxia/formatter.py`) e
`semanticTokens/full`; `codeAction`/fixes, rename e spans formais seguem pendentes.

- `loxia/lsp.py` — **updated**: capabilities/handlers/helpers.
- `loxia/cli.py` — **updated**: features em `capabilities`.
- `tests/test_lsp.py` — **updated**: formatting, completion, signature e semantic tokens.
- `README.md`, `CHANGELOG.md`, `TODO.md`, `docs/adr/0090`, `docs/decisoes.md`,
  `docs/tech/arquitetura.md` — **updated**: status.

<!-- triaged: 14cded2 -->

## 2026-11-16 — modelo de fixes estruturados

Intervalo: `HEAD`..working tree. Implementa o pré-requisito do ADR-0093: `Fix`, `Edit` e
`Applicability` no `Diagnostic`, com `fixes[]` no JSON. Os produtores e a análise de
confiabilidade ficam em [`tech/fixes.md`](tech/fixes.md) e no TODO.

- `loxia_core/diagnostics/diagnostic.py`, `render.py`, `error_reporter.py` — **updated**.
- `docs/spec/erros.md`, `docs/tech/fixes.md`, `docs/adr/0093`, `TODO.md`,
  `CHANGELOG.md`, `README.md` — **updated**.
- `tests/test_diagnostics.py` — **updated**: JSON e reporter com fixes.

<!-- triaged: fbe7f8e -->

## 2026-11-16 — fixes restantes, spans e rename cross-file

Intervalo: `30d0275`..`055fd49`. Fecha os produtores de fix restantes, adiciona
`loxia/source_index.py` e rename cross-file conservador no LSP.

- `docs/decisoes.md` — **updated**: linha de property-based (ADR-0098).
- `docs/spec/erros.md` — **updated**: bloco gerado de códigos (W1002 incluso).
- `docs/spec/garantias.md` — **updated**: contagens/status do corpus gerados.
- `docs/spec/semantica.md` — **updated**: pureza de módulo/W1002 e `std.property`.
- `docs/spec/sintaxe.md` — **no-change**: nenhuma sintaxe nova; os campos de token
  (`Import.start/end`, `Var.keyword`, `Field.end`, `Function.end`, `Call.commas`) são
  internos do AST/parser.

<!-- triaged: 055fd49 -->

## 2026-11-16 — tooling de editor

Intervalo: `3fbf12f`..`fb48480`. Fecha o formatter fase 1, `workspace/symbol` e o cliente
VS Code.

- `docs/adr/0090-lsp-escopo-e-hospedagem.md` — **updated**: `workspace/symbol` e cliente.
- `docs/adr/0092-estilo-e-formatter.md` — **updated**: fase 1 implementada; dogfood adiado.
- `docs/guia-estilo.md` — **updated**: `fn`/trailing comma no formatter.
- `docs/spec/sintaxe.md` — **updated**: trailing comma aceito.
- `docs/spec/garantias.md` — **updated**: contagem do corpus (`trailing_comma`).
- `TODO.md`, `README.md`, `CHANGELOG.md`, `docs/tech/arquitetura.md`, `editors/README.md` —
  **updated**: fila, comandos, capacidades e instruções.
- `docs/decisoes.md` — **no-change**: nenhuma decisão nova; formatter/LSP já estão nos
  ADR-0090/0092.
- `docs/spec/erros.md` — **no-change**: nenhum código de diagnóstico mudou.

<!-- triaged: fb48480 -->

## 2026-11-16 — completion do LSP por escopo

Intervalo: `abbd3a3`..`64dfea4`. A completion deixa a AST reescrita e passa a usar a AST
original: escopo, imports, módulos, `this`/`super`, enums e membros nativos.

- `docs/adr/0090-lsp-escopo-e-hospedagem.md` — **updated**: completion por escopo/imports.
- `docs/tech/arquitetura.md` — **updated**: `loxia/completion.py`.
- `editors/vscode/README.md` — **updated**: completion.
- `docs/decisoes.md` — **no-change**: nenhuma decisão nova; é refinamento do LSP-2 já
  registrado no ADR-0090.

<!-- triaged: 64dfea4 -->

## 2026-11-17 — Fase 0: histórico limpo e links públicos

Nota: a reescrita do histórico removeu `IDEIAS-REDDIT.md`; os SHAs anteriores a este dia
não existem mais. O marcador abaixo usa o SHA reescrito.

- `docs/spec/garantias.md` — **no-change**: `levels.py --write` regenerou o bloco idêntico;
  a fonte `7f3f9af` mudou backend/stdlib, mas o contrato e o status não.
- `docs/stdlib/index.md` — **no-change**: `stdlib.py --write` regenerou as 27 páginas sem
  diff; a API documentada já cobre `std.property.listOf`.
- `docs/adr/0066-orcamento-e-gate-sintatico.md`, `docs/adr/0078-nome-loxia-extensao-lx.md`,
  `docs/README.md`, `docs/tech/arquitetura.md`, `docs/glossario.md` — **updated**: links
  para o `AGENTS.md` local trocados por alvos públicos (ADR-0014, guia de estilo,
  garantias, spec/erros); o `CONTRIBUTING.md` entra na próxima etapa.
- `docs/spec/semantica.md` — **updated**: `io.readLine`/`io.readAll` exigem UTF-8 estrito,
  independente do locale.

<!-- triaged: 7f3f9af -->

## 2026-11-17 — pós-fix de stdin e links

- `docs/decisoes.md` — **no-change**: os ADR-0066/0078 só trocaram links locais por alvos
  públicos; nenhuma decisão mudou.
- `docs/stdlib/builtins.md` — **no-change**: `make docs-sync` regenerou sem diff; a mudança
  em `primitives.py` foi só o decode estrito de stdin, sem API nova.

<!-- triaged: 47f9f45 -->

## 2026-11-17 — SPDX headers

- `docs/spec/*.md` (5 páginas) — **no-change**: o header SPDX é comentário; nenhum
  comportamento, gramática ou mensagem de erro mudou.
- `docs/stdlib/*.md` (27 páginas) — **no-change**: `stdlib.py --write` não produziu diff;
  o header não altera os doc comments.
- `docs/decisoes.md` — **no-change**: a linha do ADR-0101 já entrou no PR de licença; o
  header SPDX não toca decisões.

<!-- triaged: 7629214 -->

## 2026-11-17 — site de documentação

- `docs/decisoes.md` — **updated**: entrou a linha do ADR-0103 (Starlight em `site/`,
  staging de `docs/`, i18n com referência pt-BR e arquivo 1.0). Nenhuma decisão de
  linguagem mudou; o restante é infraestrutura de publicação.

<!-- triaged: 3055e2b -->
