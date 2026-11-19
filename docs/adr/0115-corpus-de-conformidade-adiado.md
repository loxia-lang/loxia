# ADR-0115 — Corpus de conformidade: adiar a extração até existir spec `lox-core`

- **Status:** accepted (adiado; sem implementação)
- **Data:** 2026-11-19
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0031](0031-backend-nativo.md) (backend e corpus),
  [ADR-0064](0064-orcamento-do-corpus.md) (teto de `PENDING` e promessa do I1),
  [ADR-0107](0107-adiados-e-nao-objetivos.md) (adiados), issue
  [#10](https://github.com/loxia-lang/loxia/issues/10)
- **Implementação:** nenhuma (registro de decisão); `docs/roadmap.md` e
  `docs/decisoes.md` refletem o adiamento.

## Contexto

A issue [#10](https://github.com/loxia-lang/loxia/issues/10) propõe extrair o corpus de
conformidade como artefato `lox-core` para outras implementações: na fase 1, um subset
compatível com o livro, com o **livro** como oráculo (não o nosso tree-walk), runner
genérico, adaptador mecânico documentado e auditoria de licença; a fase 2 (dialeto Loxia)
viria depois.

O que existe hoje:

- `tests/cases/` é o corpus **interno** do I1, anotado por nível em
  `tests/corpus_manifest.py`; o I1 só promete o corpus declarado, e o teto de `PENDING` é
  5% ([ADR-0064](0064-orcamento-do-corpus.md)).
- `tests/official/` tem 120 casos adaptados do livro, mas o próprio README diz que **não é
  uma suíte de conformidade**: é uma rede extra para o interpretador. As adaptações
  (`fun`→`fn`, `//`→`#`, `class B(A)`, campos declarados, `print` função) são nossas, não
  do livro.
- Não existe uma **spec `lox-core` publicada** — um perfil versionado que diga o que o
  artefato certifica. Sem ela, o artefato seria um contrato sem documento: o corpus atual
  carrega expectativas do dialeto Loxia, e o livro sozinho não fixa as divergências
  (`val`/`var`, `Int`/`Float`, `fn`, `print` função etc.).

Extrair agora teria custo real (adaptador, runner, licença, README de divergências,
manutenção de duas expectativas) e criaria uma segunda fonte de verdade antes de existir
demanda externa. O corpus está maduro para o I1; isso não o torna um contrato externo.

## Decisão

1. **Não extrair o corpus agora.** A issue #10 é fechada como *not planned*; não há
   `conformance run`, artefato publicado nem adaptador nesta fase.
2. O corpus interno continua sendo o oráculo do I1 ([ADR-0031](0031-backend-nativo.md),
   [ADR-0064](0064-orcamento-do-corpus.md)) e não vira contrato de compatibilidade para
   terceiros.
3. **Gatilho de reabertura:** existir uma spec `lox-core` publicada e versionada **e** pelo
   menos uma implementação externa (ou mantenedor) pedindo o artefato. Quando isso
   acontecer, a fase 1 da #10 é o plano: subset compatível com o livro, livro como oráculo,
   runner genérico, adaptador mecânico documentado e auditoria de licença.
4. A extração, quando reaberta, não pode alterar o I1 nem promover o corpus interno a
   contrato externo; a fase 2 (dialeto Loxia) continua depois da fase 1.

## Consequências

### Positivas

- Não há manutenção de um artefato e de um adaptador sem consumidor.
- O I1 continua honesto: o corpus é interno e o que ele promete é o que é testado.
- Evita congelar expectativas antes de existir uma spec `lox-core`.

### Negativas / custos

- Outras implementações não têm um artefato oficial para validar contra o Loxia.
- A suíte do livro continua sendo só uma rede interna, não uma certificação.
- Se a demanda aparecer, o trabalho começa do zero (o desenho da #10 fica preservado no
  histórico da issue).

### Neutras

- Nenhum código, semântica, diagnóstico ou garantia muda; é uma decisão de release.
- A issue #10 fecha e o roadmap a move de **Next** para **Later**.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Extrair agora | Artefato sem spec publicada; adaptador/runner/licença/manutenção antes de demanda externa; segunda fonte de verdade. |
| Extrair só `tests/official/` | O README diz explicitamente que não é suíte de conformidade; ainda exigiria adaptador, licença e runner, e as expectativas são do livro, não do nosso dialeto. |
| Manter a #10 aberta em **Next** | As regras do roadmap dizem que trabalho fora das próximas ~6 semanas não é issue; issue aberta em Next sinaliza compromisso que não existe. |
| Apagar a ideia | Perde o desenho da fase 1 e o gatilho; fechar como *not planned* preserva o histórico. |

## Como verificar

- `gh issue view 10` mostra a issue fechada como *not planned*, com o comentário da decisão.
- `docs/roadmap.md` não lista a #10 em **Next**; ela aparece em **Later** com o gatilho.
- `docs/adr/README.md` e `docs/decisoes.md` apontam para este ADR.
- `uv run pytest tests/test_docs_consistency.py tests/test_docs_links.py -q` passa.
- Revisitar quando o gatilho da decisão 3 acontecer; não há código ou teste a manter.

## Referências

- Issue [#10](https://github.com/loxia-lang/loxia/issues/10)
- [`tests/official/README.md`](../../tests/official/README.md)
- [ADR-0031](0031-backend-nativo.md), [ADR-0064](0064-orcamento-do-corpus.md)
- [ADR-0107](0107-adiados-e-nao-objetivos.md)
