---
name: lox-syntax
description: Procedimento para propor, aceitar ou recusar sintaxe na linguagem — quatro perguntas do gate, orçamento, não-objetivos, aprovação humana e o que registrar em ADR/spec/golden.
whenToUse: Quando a tarefa envolve adicionar ou mudar sintaxe (token, operador, forma de declaração, açúcar, gramática) ou quando alguém pede para "só aceitar" uma sintaxe nova.
---

# Sintaxe: propor, aceitar, recusar

O contrato está no [ADR-0066](../../../docs/adr/0066-orcamento-e-gate-sintatico.md).
Esta skill é o passo a passo; o ADR é a decisão.

## Regra zero

**Pergunte ao humano antes de implementar.** Agente não adiciona sintaxe por iniciativa
própria, nem "de passagem" enquanto conserta outra coisa. Diagnóstico dirigido (mensagem
melhor sem mudar a gramática) não conta como sintaxe nova e pode seguir direto — mas
ainda ganha caso de teste.

## As quatro perguntas (responda por escrito)

1. **Substituição** — a sintaxe nova substitui uma grafia existente, vem da stdlib, ou
   cria uma segunda forma de dizer a mesma coisa? Só as duas primeiras passam fácil.
2. **Decidibilidade local** — o parser decide sem lookahead arbitrário, sem depender de
   newline fora das regras documentadas e sem contexto de statement? Se não, precisa de
   caso negativo e de uma justificativa explícita.
3. **Precedência** — cabe na tabela atual ou cria nível novo? Nível novo exige teste de
   AST e justificativa.
4. **Forma canônica** — existe **uma** forma de escrever? Se o parser aceita duas, qual é
   a canônica e como o style guide/formatter a impõe?

Some a isso: **dor real** (caso no corpus ou programa concreto), **teste que policia** e
**impacto no LLVM** (I1/I4). Sem os três, a resposta é não.

## Orçamento

| Métrica | Teto |
| --- | --- |
| palavras-chave | 28 |
| níveis de precedência | 19 |
| formas de statement | 12 |
| formas de declaração | 6 |
| construções sensíveis a newline | não crescer |
| grafias por conceito | 1 (exceção documentada no ADR) |

Se a proposta estoura um teto, o caminho é ADR de revisão do orçamento — não exceção
silenciosa.

## Não-objetivos (recuse por padrão)

`//` como comentário · `?:` · `&&`/`||` · `++`/`--` · `switch` · declaração estilo C ·
conversão implícita · duas grafias para a mesma declaração · argumentos nomeados,
extension methods, operator overloading e trailing closure antes do LLVM MVP.

Para reabrir qualquer um: ADR + dor demonstrada. A lista completa está no
[ADR-0066](../../../docs/adr/0066-orcamento-e-gate-sintatico.md).

## Se aceita

1. Registre o ADR (contexto, decisão, consequências, alternativas, como verificar) e a
   linha em [`docs/decisoes.md`](../../../docs/decisoes.md).
2. Atualize [`docs/spec/sintaxe.md`](../../../docs/spec/sintaxe.md) (gramática + prosa) e,
   se mudou mensagem, [`docs/spec/erros.md`](../../../docs/spec/erros.md).
3. Atualize [`TODO.md`](../../../TODO.md) §1 e o `docs/adr/README.md`.
4. Escreva o **golden** antes/durante o parser (`tests/cases/*.lx`), mais unitário em
   `tests/test_parser.py` se a AST for não trivial.
5. Rode `make check`; se tocou caminho quente, `make bench`.

## Se recusada

Registre em [`IDEIAS.md`](../../../IDEIAS.md) ou `TODO.md` §11, **nunca** em ADR. Diga o
motivo em uma linha (custo no parser/backend, grafia duplicada, ambiguidade local). Isso
evita rediscutir o mesmo pedido na próxima sessão.

## Exemplo recente

O [ADR-0067](../../../docs/adr/0067-desambiguacao-sintatica.md) é a primeira aplicação:
`//` e mapa ganharam diagnóstico (sem gramática nova); operador em brackets, `fn` em
método e parênteses na união de `is` passaram pelas quatro perguntas; a união crua foi
recusada porque não é decidível localmente.
