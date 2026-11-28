# ADR-0157 — Invocação e distribuição do THIR eval (decisão da #288)

- **Status:** accepted
- **Data:** 2026-11-28
- **Decisores:** Cássio Dalla (dono do projeto) e agente (DSH)
- **Relacionados:** [ADR-0149](0149-motores-primarios-thir-e-congelamento.md) (motores e
  congelamento), [ADR-0152](0152-run-aot-aceitacao-flags-e-cache.md) (`run` AOT e cache),
  [ADR-0154](0154-fronteira-do-thir.md) (fronteira do THIR),
  [ADR-0156](0156-sem-desugaring-no-thir.md) (forma do contrato),
  [ADR-0158](0158-json-sem-cap-de-aninhamento.md) (leitor JSON do payload),
  [ADR-0128](0128-contrato-de-motores.md) (camadas e sandbox),
  [ADR-0078](0078-nome-loxia-extensao-lx.md) (vocabulário Loxia/Lox),
  [ADR-0133](0133-suite-rapida-in-process-e-xdist.md) (suíte)
- **Implementação (F3):** [`loxia/cli_args.py`](../../loxia/cli_args.py),
  [`loxia/cli_commands.py`](../../loxia/cli_commands.py), [`loxia/engine.py`](../../loxia/engine.py),
  [`loxia_core/bundle.py`](../../loxia_core/bundle.py), `pyproject.toml`,
  `loxia_core/thir_eval/` (fontes empacotadas) e o smoke de três canais.

## Contexto

O [ADR-0149](0149-motores-primarios-thir-e-congelamento.md) decide que o interpretador é um
**THIR eval escrito em Loxia** e que ele vira o motor de REPL/`--interpret` no G3. A #288 abriu
a decisão de **como ele é chamado e distribuído** e a marcou como bloqueio da F3.

A issue propõe três formas (flag, entry point próprio, pipeline explícito) e exige honrar I1,
I3, o oráculo, o cache e a distribuição no wheel. A análise mostrou que a pergunta mistura
três eixos que precisam de resposta separada — **transporte do payload**, **motor hospedeiro**
e **o que “default” significa no G3** — e que dois fatos restringem a solução:

- o tree-walk não é só um motor: ele hospeda `--json`, `--json-lines`, `--error-format≠human`,
  `--sandbox`, `--stdin` e `--color=always`, que hoje **implicam** o caminho interpretado
  ([`cli_args.py`](../../loxia/cli_args.py));
- o payload do THIR não é JSON que o `std.json` atual consome: 56 de 269 casos do corpus
  passam de 16 níveis de aninhamento (máximo 32), e o leitor tem um cap explícito de 16
  (resolvido no [ADR-0158](0158-json-sem-cap-de-aninhamento.md)).

O REPL acrescenta um problema próprio: um processo por input perde o estado da sessão, então
o THIR eval no REPL exigiria processo persistente, protocolo e um canal dedicado — um ABI
novo que a F5 tende a apagar, porque o front end em Loxia permite uma REPL inteira em Loxia.

## Decisão

1. **Sem comando novo e sem nome de artefato no CLI.** A superfície pública é a que já existe:
   `loxia run --interpret prog.lx` (e `loxia test`). No G3, “interpretar” passa a ser THIR
   eval. Durante a transição/soak, `loxia run --engine=native|thir|tree` seleciona
   explicitamente (`native` é o default de hoje; `tree` é o oráculo Python congelado). Não
   existe `loxia loxvm`; “THIR eval” é o nome de conceito e `loxvm` fica como codename
   histórico das issues/plano.
2. **`run` continua nativo.** O G3 muda a superfície de **interpretação**, não o caminho de
   produção: `loxia run prog.lx` segue compilando com o backend (ADR-0149 §1 / F0). O G3
   cobre execução one-shot — `--interpret`/`--engine=thir`, `loxia test`, o harness
   diferencial. O tree-walk continua como oráculo sobre o corpus congelado.
3. **Payload por arquivo temporário, em `canonical`.** O front end Python produz o `TModule`
   em processo (o mesmo de `--emit=thir`) e grava a forma **compacta e ordenada** num arquivo
   `0600` de vida curta; o caminho vai no argv do avaliador. Stdin, stdout e stderr pertencem
   ao programa (I1): **nada de payload em stdin ou stdout**. Para depurar, `--keep-thir
   <path>` preserva o arquivo. `--emit=thir` continua escrevendo a forma legível (`dumps`).
4. **O avaliador é um programa Loxia empacotado no wheel.** As fontes viajam com o pacote
   (force-include, resolvidas como `std/`/`runtime/` pelo `bundle_dir`), e o build nativo as
   compila na primeira execução, com **cache por conteúdo próprio** (fontes do avaliador +
   runtime + toolchain + flags), nunca por programa do usuário. Não há binário pré-compilado
   por plataforma na F3. Sem `llvmlite`/`cc`/`libgc`, o caminho THIR **recusa** com `E4004` e
   aponta `--engine=tree` (explícito); não há fallback silencioso. Isso torna a superfície
   interpretada dependente do extra `llvm` a partir do G3 — quebra declarada no CHANGELOG
   quando o G3 chegar.
5. **argv e ambiente do programa são do programa.** O avaliador recebe o payload e, depois de
   `--`, os `script_args` do programa; `args()` no programa avaliado vê só os args do
   programa, nunca o caminho do payload. cwd/env são herdados do CLI. Os spans do payload são
   caminhos de exibição: o avaliador reporta `span.file`, nunca o temporário (I3).
6. **Contratos do CLI na segunda rota são explícitos.** `--json`, `--json-lines`,
   `--error-format≠human`, `--sandbox`, `--stdin` e `--color=always` precisam ser
   **implementados** pelo THIR eval ou **recusados** com diagnóstico por flag; nunca
   redirecionados em silêncio. `--sandbox` é requisito do G3 (é uma flag de segurança: quem a
   usa não pode cair no oráculo sem saber), com o avaliador aplicando a política ao programa
   e lendo o payload antes dela. `--json`/`--color`/`--error-format` podem esperar, com
   recusa declarada. `--stdin`, `--timeout` e `--max-heap` são naturais (stdio e processo do
   avaliador).
7. **REPL é exceção declarada até a F5.** O G3 não cobre o modo interativo: ele fica no
   tree-walk congelado (sem feature nova), porque um THIR eval persistente exige protocolo,
   framing e canal dedicado, e a F5 permite uma REPL inteira em Loxia sem essa ponte. Se a
   exceção doer antes, ela vira ADR de protocolo de REPL, não um remendo na flag.
8. **Harness (#289) usa a mesma superfície.** Um caso por processo via
   `run --engine=thir`, comparando os três canais; modo lote é decisão da #289, não desta.
   O avaliador trata `k`/`schema_version` desconhecido como diagnóstico estável (F3), nunca
   crash.

## Consequências

### Positivas

- Nenhum binário novo, nenhuma matriz de release por plataforma e nenhum nome de artefato
  no CLI: a chamada do usuário é a que já existe.
- Stdin/stdout ficam intactos para o programa; o payload não colide com `--stdin` nem com a
  saída (I1).
- O cache de build é reaproveitado com uma chave própria do avaliador; não há cache paralelo
  por programa.
- O REPL não bloqueia o G3, e o trabalho de protocolo não é feito para ser apagado na F5.
- O nome público descreve o contrato (“THIR eval”), não uma VM que não existe.

### Negativas / custos

- `--interpret` passa a exigir o toolchain nativo no G3 (quebra para quem usa o interpretador
  sem `llvmlite`); `--engine=tree` é a saída explícita, mas é o oráculo congelado.
- O tree-walk continua empacotado por mais tempo (oráculo + REPL), adiando o G5.
- As seis flags da rota interpretada precisam ser portadas ou recusadas uma a uma; a recusa
  é trabalho de UX e de teste.
- O sandbox muda de dono: a política passa a ser aplicada pelo avaliador ao programa, e o
  processo do avaliador roda confiável — uma fronteira de confiança nova, que precisa de
  teste próprio.
- Arquivo temporário tem ciclo de vida e limpeza; `--keep-thir` existe para debug, mas não é
  contrato de usuário.

### Neutras

- `--emit=thir` não muda (forma legível, para humanos/snapshot).
- O avaliador compilado ocupa o cache como qualquer build; o payload é derivado e não é
  cacheado.
- O nome `loxvm` pode continuar nas issues antigas; a documentação nova usa “THIR eval”.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Entry point próprio (`loxia loxvm`/binário) | Nome de artefato no CLI, segunda superfície e matriz de release; a flag existente já cobre o caso one-shot. |
| Binário pré-compilado por plataforma | Matriz de release, PATH e versionamento cedo demais; o wheel já precisa do runtime nativo para `run`. |
| Payload por stdin | Colide com `--stdin` do programa e com o canal de saída; um pipe anônimo não é nomeável para debug. |
| Payload por `stdout` do `build --emit=thir` | Mistura o canal do programa com o artefato; quebra `--json` e a comparação de bytes. |
| `run` default = THIR eval | Reverte F0/ADR-0149 e esvazia a F4; o nativo é o produto. |
| Protocolo de REPL agora | ABI novo (framing, canal, THIR incremental) que a F5 substitui por uma REPL toda em Loxia. |
| Avaliador hospedado no tree-walk sem toolchain | Preserva “sem deps”, mas dobra os hosts e mantém o tree-walk no caminho; a recusa explícita é mais honesta. |

## Como verificar

- F3, smoke de três canais: `run --engine=thir` num caso do corpus, comparando stdout, stderr
  e exit com o oráculo (o mesmo contrato do diferencial).
- F3, recusa sem toolchain: sem `llvmlite`, `--engine=thir` sai 65 com `E4004` e a dica de
  `--engine=tree`; sem payload em stdin/stdout.
- F3, payload: arquivo temporário com `canonical`, spans de exibição no stderr e `args()` do
  programa sem o caminho do payload.
- F3, contratos: cada uma das seis flags tem implementação ou recusa testada; `--sandbox`
  não pode ser ignorado.
- F3, cache: a segunda execução não recompila o avaliador (hit por conteúdo).
- Critério para revisitar: G3 medir startup/latência/memória (se o arquivo temporário ou o
  build do avaliador dominarem, volta ao ADR); F4 decidir binário se a distribuição exigir;
  F5 reabrir a REPL; #289 decidir lote.

## Referências

- #288 (a decisão), #284 (F3), #289 (harness), #244 (F0)
- [ADR-0149](0149-motores-primarios-thir-e-congelamento.md),
  [ADR-0152](0152-run-aot-aceitacao-flags-e-cache.md),
  [ADR-0156](0156-sem-desugaring-no-thir.md),
  [ADR-0158](0158-json-sem-cap-de-aninhamento.md)
- [`docs/plano-de-motores.md`](../plano-de-motores.md), [`docs/tech/thir.md`](../tech/thir.md)
