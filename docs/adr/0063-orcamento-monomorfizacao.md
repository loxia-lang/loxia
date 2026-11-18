# ADR-0063 — Orçamento de monomorfização e política para M8

- **Status:** accepted (implemented)
- **Data:** 2026-11-13
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0027](0027-generics-t3b.md), [ADR-0050](0050-monomorfizacao-t7.md),
  [`../../TODO.md`](../../TODO.md) §6/§9
- **Implementação:** `loxia_core/backend/lower_generics.py` (`MonomorphizationBudget`),
  `loxia/cli.py` (diagnóstico `E4003`), `tests/test_backend.py` e `bench/monomorph.py`

## Contexto

`id$Int`, `Box$String` e `map$Int$Int` funcionam bem, mas o custo é o produto cartesiano
das instanciações. `List[List[Box[Int]]]`, recursão polimórfica e bibliotecas genéricas
podem explodir código e tempo de compilação. Hoje não há teto nem diagnóstico: o cache
evita duplicata, mas não limita crescimento.

## Decisão proposta

- **Chave canônica** por `(nome, estrutura de Ty normalizada)`, nunca por `display`.
- **Worklist** com cache antes de emitir; cada instanciação consome orçamento.
- Limites iniciais (ajustáveis por ADR se benchmarks justificarem):
  - 256 funções especializadas por compilação;
  - 256 layouts de classe especializados;
  - profundidade máxima de tipo aninhado: 8;
  - nome mangled máximo: 1024 bytes.
- **Diagnóstico determinístico** ao estourar: `BackendError` no site da instanciação,
  mensagem `"Too many generic instantiations (limit ...); simplify type arguments."`,
  exit 65, sem binário parcial.
- A política cobre funções, classes e um futuro valor genérico; não cobre `Any`/containers
  boxeados, que não monomorfizam.
- **Antes do M8**, replay do corpus e um caso sintético de aninhamento para medir tempo e
  tamanho; só então fixar os números finais.

### Valor genérico (T7 restante)

`val id = fn(x) => x` ainda é 65. Opções:

| Alternativa | Custo | Observação |
| --- | --- | --- |
| Especializar no call site, guardando a AST genérica no valor | médio | Mantém unboxed; exige um valor “família de instâncias” e cache por tipo. |
| Boxar tudo (`Any`) no valor genérico | baixo | Contraria o unboxed do ADR-0027 e mistura com `Any`. |
| Continuar rejeitando | zero | Mantém `generic_lambda_value` como `PENDING`; aceitável pós-M8. |

Recomendação: call-site especialization, dentro do orçamento, **depois** de enums e
exceções; se o custo de representação do valor crescer, adiar para M8.

## Alternativas

| Alternativa | Por que não agora |
| --- | --- |
| Sem teto | Deixa a compilação imprevisível e transforma bug de performance em OOM do compilador. |
| Teto só por função | Não limita explosão entre funções/classes. |
| Teto configurável por CLI | Superfície nova antes de haver demanda; pode entrar depois. |
| Monomorfização especulativa | Piora exatamente o problema que o teto quer evitar. |

## Consequências

- Um programa válido pode ser recusado por orçamento; isso é uma **lacuna declarada**,
  não um erro de tipo (I4).
- Testes: um caso que passa no limite e outro que estoura com mensagem/exit 65.
- Medição de tamanho/tempo entra no M8, não no fechamento do L6.
