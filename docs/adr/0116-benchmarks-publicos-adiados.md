# ADR-0116 — Benchmarks públicos: adiar a publicação até haver protocolo e release

- **Status:** accepted (adiado; sem implementação)
- **Data:** 2026-11-19
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0031](0031-backend-nativo.md) (backend e corpus),
  [ADR-0063](0063-orcamento-monomorfizacao.md) (orçamento e política do M8),
  [ADR-0115](0115-corpus-de-conformidade-adiado.md) (outro artefato adiado), issue
  [#13](https://github.com/loxia-lang/loxia/issues/13)
- **Implementação:** nenhuma (registro de decisão); `docs/roadmap.md` e
  `docs/decisoes.md` refletem o adiamento.

## Contexto

A issue [#13](https://github.com/loxia-lang/loxia/issues/13) propõe publicar a suíte de
benchmarks como artefato público (`fib`, `nbody`, `mandelbrot`) para acompanhar regressões
entre releases. O critério de pronto pede casos determinísticos nos dois motores, baseline
amarrado a um release/commit, nota curta de metodologia e CI fora do circuito (ruído de
runner). A issue cita o [ADR-0063](0063-orcamento-monomorfizacao.md), que fixa o orçamento
de monomorfização e a política do M8, não uma política de benchmarks públicos.

O que existe hoje:

- `bench/run.py` mede o processo inteiro do CLI, com mediana de `--repeat` amostras e
  tolerância de regressão; `bench/README.md` descreve a metodologia e já publica uma
  tabela de resultados de 2026-11-14.
- `bench/baseline.json` guarda data, versão do Python, plataforma e **milissegundos
  absolutos** de uma máquina específica. O baseline é local e intencionalmente regravado
  ao adicionar casos.
- `bench/cases/` tem 11 casos internos de throughput (laços, chamadas, classes, coleções,
  GC etc.); `fib`, `nbody` e `mandelbrot` não existem.
- [`docs/spec/garantias.md`](../spec/garantias.md) diz explicitamente que **speed não é
  prometido**: os benchmarks servem para detectar regressão, não para competir.

Publicar agora teria o mesmo anti-padrão da #10 em outra roupa: um artefato público antes
de existir contrato e consumidor. Só que aqui o contrato é **metodológico**, não normativo.
Números absolutos de uma máquina, sem hardware/flags/variância declarados, viram uma
promessa implícita de performance e convidam comparações cross-machine que o harness não
sustenta. A suíte proposta também é trabalho novo, não a publicação do que já existe.

## Decisão

1. **Não publicar a suíte de benchmarks agora.** A issue #13 é fechada como *not planned*;
   `bench/` continua sendo o harness interno de regressão, fora do CI.
2. **Gatilho de reabertura:** um release em que performance faça parte da mensagem
   (release notes, blog ou comparação) **e** um protocolo reprodutível — hardware/OS,
   flags do compilador, aquecimento, `N`, mediana e dispersão, commit/release — **e** um
   consumidor concreto.
3. Quando reabrir, o caminho mais barato é promover a metodologia e a tabela que já existem
   em [`bench/README.md`](../../bench/README.md) a um relatório reprodutível; só depois
   adicionar casos padrão como `fib`/`nbody`/`mandelbrot`. Número absoluto sem ambiente e
   método declarados não é publicado.
4. Benchmarks públicos continuam **descritivos**, nunca uma garantia: a seção "Speed" de
   [`docs/spec/garantias.md`](../spec/garantias.md) não muda e nenhum número público entra
   no I1/I3.

## Consequências

### Positivas

- Não há promessa implícita de performance nem comparação cross-machine enganosa.
- O harness interno continua rápido, local e barato de manter.
- Evita uma segunda suíte e a manutenção de números absolutos.

### Negativas / custos

- Não há uma história pública de performance para a 1.1.
- Usuários e terceiros não têm uma suíte oficial para comparar implementações.
- Se a demanda aparecer, o trabalho começa do zero (o desenho da #13 fica preservado no
  histórico da issue).

### Neutras

- Nenhum código, semântica, diagnóstico ou garantia muda; é uma decisão de release.
- A issue #13 fecha e o roadmap a move de **Next** para **Later**.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Publicar agora com o harness atual | Baseline por máquina, números absolutos e nenhum protocolo de hardware/flags/variância; vira promessa implícita. |
| Publicar só a tabela do `bench/README.md` | Ainda é medição local, não amarrada a release/commit nem a um método reprodutível. |
| Manter a #13 aberta em **Next** | A label `P2` e as regras do roadmap dizem que trabalho fora das próximas ~6 semanas não é issue; não há consumidor. |
| Nunca publicar | Perde o valor quando performance entrar na comunicação de um release; o gatilho mantém a opção viva. |

## Como verificar

- `gh issue view 13` mostra a issue fechada como *not planned*, com o comentário da decisão.
- `docs/roadmap.md` não lista a #13 em **Next**; ela aparece em **Later** com o gatilho.
- `docs/adr/README.md` e `docs/decisoes.md` apontam para este ADR.
- `uv run pytest tests/test_docs_consistency.py tests/test_docs_links.py -q` passa.
- Revisitar quando o gatilho da decisão 2 acontecer; não há código ou teste a manter.

## Referências

- Issue [#13](https://github.com/loxia-lang/loxia/issues/13)
- [`bench/README.md`](../../bench/README.md), [`bench/baseline.json`](../../bench/baseline.json)
- [`docs/spec/garantias.md`](../spec/garantias.md) ("What is not promised — Speed")
- [ADR-0063](0063-orcamento-monomorfizacao.md), [ADR-0115](0115-corpus-de-conformidade-adiado.md)
