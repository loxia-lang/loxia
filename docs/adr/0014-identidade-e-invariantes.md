# ADR-0014 — Identidade: três invariantes e um portão de admissão

- **Status:** accepted — **atualizado** por [ADR-0059](0059-i4-check-limpo-compila.md) (I4) e [ADR-0060](0060-orcamento-de-memoria.md) (memória). O texto abaixo é o registro original: onde ele diz "enquanto o backend não existe", leia o `docs/spec/garantias.md` e o manifesto do corpus.
- **Data:** 2026-11-11
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0002](0002-tree-walk-como-oraculo.md),
  [ADR-0003](0003-diagnosticos-por-execucao.md), [ADR-0006](0006-int-float-separados.md),
  [ADR-0010](0010-tipagem-estatica.md), [ADR-0014](0014-identidade-e-invariantes.md), [TODO §11](../../TODO.md)
- **Implementação:** [`docs/spec/garantias.md`](../spec/garantias.md),
  [`tests/test_determinism.py`](../../tests/test_determinism.py)

## Contexto

A pergunta que originou este ADR: *"a linguagem tem algum atributo único, algo que fizesse
outras pessoas quererem ela? ou é só uma colcha de retalhos de C/Python/Kotlin?"*

O inventário honesto está no [TODO §8](../../TODO.md): toda feature implementada é
emprestada — `?.`/`??` (Kotlin/Swift/TS), `val`/`var` (Kotlin/Swift), `;` opcional
(Go/Kotlin), interpolação (Kotlin), `class B(A)` (Lox2), `Int`/`Float` separados (Rust/C),
`fn` no lugar de `fun` (Rust). Nenhuma peça é original, e isso **não é um problema por
si**: linguagens boas são colchas de retalhos bem costuradas.

O problema real é outro: sem um critério, a próxima feature é avaliada por *"isso é
legal?"* em vez de *"isso fortalece o que somos?"*. O resultado previsível é uma linguagem
que tenta agradar a todos, acumula superfície semântica que o backend precisa replicar
exatamente, e não tem nada que faça alguém trocar Python por ela.

Diferencial não nasce de feature — feature se copia em um fim de semana. Nasce de
**invariante**: uma promessa que custa caro manter e que, por isso, ninguém copia.

Felizmente o projeto já tem 90% da infraestrutura para três invariantes fortes, e uma
atitude consistente que ninguém tinha nomeado.

## Decisão

A identidade da linguagem é um **contrato de três invariantes** mais **uma regra de
admissão de feature**. Feature nenhuma é identidade; os invariantes são o que se promete
ao usuário e o que qualquer agente deve proteger.

**Frase de posicionamento (a única que se usa):**

> Uma linguagem pequena onde o interpretador **é** a especificação: o mesmo programa dá o
> mesmo resultado interpretado e compilado, byte a byte — e nada acontece implicitamente.

### I1 — Equivalência executável

Para todo programa do corpus (golden cases, suíte oficial, exemplos), o tree-walk e o
backend nativo produzem **o mesmo stdout (bytes), o mesmo exit code** e o mesmo diagnóstico
normalizado. O interpretador é a **spec normativa**: quando divergir, o bug é do backend
([ADR-0002](0002-tree-walk-como-oraculo.md)).

Enquanto o backend não existe, a parte verificável de I1 já vale: **a mesma execução
repetida produz os mesmos bytes**, e o corpus é o teste diferencial do futuro (nada de
escolher casos depois — o corpus de conformidade é o mesmo desde hoje).

### I2 — Nada acontece implicitamente

Nenhuma conversão, coerção, truncamento, arredondamento, truthiness ou fallback acontece
sem estar escrito no código. Esta é a atitude que já está no projeto e agora vira regra:

- `Float → Int` nunca é implícito; int com int e float com float, promoção só para cima
  ([ADR-0006](0006-int-float-separados.md));
- inconversão entre `Int`/`Float` e `String` ([ADR-0006](0006-int-float-separados.md));
- `+` não coage número com string; divisão por zero é erro, não `inf`;
- só `nil` e `false` são falsy; `??` troca **só** `nil`
  ([ADR-0013](0013-ternario-nil-aware-escapes.md));
- `val` e parâmetros são imutáveis por padrão ([ADR-0005](0005-val-var-imutabilidade.md));
- sem estado global de erro ([ADR-0003](0003-diagnosticos-por-execucao.md)).

### I3 — Determinismo observável

Mesma entrada + mesmas flags ⇒ **mesmos bytes** de saída e de diagnóstico. Proibido na
saída: endereço de memória, PID, timestamp, caminho absoluto, ordem de `set`/`dict`,
locale, `os.listdir`. Vale hoje para stdout/stderr e vale amanhã para o JSON estruturado
de diagnósticos e `fixes` ([I-4](../../IDEIAS.md)).

Determinismo entre **versões** não é prometido: a redação de uma mensagem pode mudar. O
que não muda é o exit code — e, quando existirem, os códigos estáveis (`E3xxx`…).

### Portão de admissão de feature

Uma feature só entra se passar nos quatro:

1. **Não viola I1/I2/I3.** Precisa de comportamento implícito? Não entra — ou entra como
   opt-in explícito e documentado.
2. **Cabe na semântica que o LLVM consegue reproduzir**, ou vem com o plano de como
   (e o plano é verificável, não esperança).
3. **A ausência dói de verdade.** Dor real de quem escreve `.lox` hoje, não simetria com
   outra linguagem ("Python tem, então nós devemos ter").
4. **Ganha teste que a policia** — golden case, e diferencial quando houver backend.

E a regra de recusa, que vale tanto quanto as de aceitação: **feature que só compra
superfície é dívida paga pelo codegen.** Superfície semântica tem custo de manutenção no
interpretador e custo de fidelidade no backend.

## Consequências

### Positivas

- Critério objetivo para dizer não, hoje e daqui a dois anos: qualquer agente (ou eu
  mesmo, de madrugada) decide feature olhando o portão, não o gosto do momento.
- Identidade verificável: I3 roda em CI hoje; I1 vira gate quando o backend nascer.
- Dívida semântica é paga no **design**, não no codegen — cada feature nova já nasce com
  a obrigação de equivalência.
- O corpus de conformidade (`tests/cases` + `tests/official` + `exemplos/`) vira produto:
  é o teste diferencial e a especificação executável ao mesmo tempo.
- Diferencia de concorrentes reais: Python/PyPy, Lua/LuaJIT e a maioria das linguagens
  **não** prometem equivalência byte a byte entre interpretado e compilado.

### Negativas / custos

- **Corta features populares.** `match` estrutural cedo, extension methods, operator
  overloading, `**kwargs`, exceções recuperáveis: todas ficam depois do backend, ou não
  entram (ver "lista de recusa" em [ADR-0014](0014-identidade-e-invariantes.md)).
- **"Nada implícito" é mais verboso que Python.** `1 + 2.0` é ok, mas não há açúcar de
  coerção; quem vem de scripting estranha.
- **I1 limita otimizações observáveis.** Reassociação de float, eliminação de código que
  "só" muda a ordem de efeitos, contagem/`id` instável: tudo isso vira bug, não liberdade
  do otimizador.
- **Disciplina contínua em mensagens de erro.** Nada de caminho absoluto, nada de ordem de
  hash — inclusive em código futuro de checker e codegen. É fácil escorregar.
- **I1 hoje é meia verdade.** Sem backend não há equivalência a provar; o que existe é a
  metade do determinismo. O risco é a promessa no README parecer maior que a realidade —
  por isso `docs/spec/garantias.md` diz explicitamente o que ainda **não** se promete.

### Neutras

- Não decide feature nenhuma; o roadmap continua no [TODO](../../TODO.md) §0/§9.
- Feature que não fortalece nem viola o eixo segue o fluxo normal (golden case + spec +
  ADR quando muda semântica).
- O nome "PyLox" e a extensão `.lox` seguem em aberto ([TODO §11](../../TODO.md) item 1).

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Identidade como catálogo de features ("Lox moderno") | É copiável, não diferencia e produz exatamente a colcha diagnosticada. |
| Identidade como sintaxe fluida | Todo mundo vende isso; é a parte mais copiável de todas e não sobrevive a "o Python já é fluido". |
| Identidade como "agent-friendly" | Envelhece com a moda e feature só-agente apodrece. Virou **consequência** de I3 (determinismo), não eixo próprio. |
| Identidade como performance | Competir com Rust/Go no eixo deles, saindo de um tree-walk em Python. Fora de escopo. |
| Identidade como compatibilidade com o Lox do livro | O projeto já divergiu de propósito; compatibilidade total impediria `val`/`var`, `Int`/`Float` e a sintaxe própria. |
| Nenhuma decisão (deixar emergir) | Foi exatamente o que gerou a pergunta; sem critério escrito, o drift volta no próximo `match`. |

## Como verificar

- **I3 hoje:** [`tests/test_determinism.py`](../../tests/test_determinism.py) roda o mesmo
  caso com `PYTHONHASHSEED` diferentes e exige igualdade **byte a byte** de stdout, stderr
  e exit code; também proíbe endereço, timestamp, PID e caminho absoluto na saída. Falha
  nesse teste = violação de I3, não flake.
- **I1 amanhã:** um `tests/test_differential.py` rodando exatamente o mesmo corpus nos dois
  backends e comparando stdout/exit. Critério de conclusão do marco M6/M7
  ([TODO §9](../../TODO.md)).
- **I2 hoje:** os golden cases de erro já fixam as recusas (coerção mista, `nil`
  surpresa). Feature nova que precise de coerção deve falhar nesses casos antes de passar
  nos novos.
- **Revisitar/reverter:** se I1 se mostrar impossível para alguma feature (ex.: timing de
  finalizador de GC), a feature é rejeitada **ou** o invariante é restringido por um ADR
  novo que diga exatamente o que deixa de valer. Nunca restringir em silêncio neste ADR
  (ADR aceito é imutável).

## Referências

- [ADR-0002](0002-tree-walk-como-oraculo.md) — tree-walk como especificação executável.
- [ADR-0006](0006-int-float-separados.md) — modelo numérico determinístico.
- [ADR-0010](0010-tipagem-estatica.md) — tipos apagados em runtime (o que permite I1).
- [ADR-0014](0014-identidade-e-invariantes.md) — diagnóstico da "colcha" e lista de recusa.
- [TODO §8](../../TODO.md) — inventário do que é emprestado.
- `docs/spec/garantias.md` — a versão para quem usa a linguagem.
- Crafting Interpreters: <https://craftinginterpreters.com/>
