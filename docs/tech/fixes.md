# Fixes confiáveis: quem produz, o que é seguro e o que fica para depois

**Status:** análise/design; modelo `Fix`/`Edit` e `fixes[]` implementados; **nenhum
produtor** emite fixes ainda (2026-11-16).
**Decisão:** [ADR-0093](../adr/0093-cli-agent-friendly-e-reparo.md) (schema e protocolo de
reparo), [ADR-0075](../adr/0075-diagnosticos-estruturados.md) (diagnóstico),
[ADR-0090](../adr/0090-lsp-escopo-e-hospedagem.md) (LSP consumidor).

## Regra de ouro

Fix não é heurística do editor. O produtor tem que ser a **fase que possui a prova
semântica**:

| Camada | Papel |
| --- | --- |
| Resolver | escopo, declaração, captura, mutabilidade |
| Checker | tipo, inferência, fluxo |
| Parser | erro sintático (quase nunca tem edição local inequívoca) |
| Loader | import/módulo (precisa provar pureza) |
| **LSP / CLI / MCP / agente** | **consumidor**: aplica/renderiza, não inventa `safe` |
| `lox fmt` | formatação, não é `fixes[]` |

Um fix só é `safe` quando o produtor consegue provar que a edição:

1. preserva comportamento (sem efeito colateral, sem remover exceção possível);
2. não muda resolução de nome (escopo/shadowing/captura);
3. não muda tipo nem API pública;
4. é atômica, determinística e idempotente;
5. passa no teste aplicar → reparsear → `--check` → executar antes/depois (I1).

Sem prova, o máximo é `unsafe`: útil como quickfix de editor, nunca aplicado pelo
`lox fix` nem por um agente sem confirmação.

## Modelo atual

`loxia_core/diagnostics/diagnostic.py`:

```text
Applicability = safe | unsafe
Edit(span, new_text)
Fix(applicability, message, edits[])
Diagnostic(..., fixes=(Fix, ...))
```

O envelope JSON expõe `diagnostics[].fixes[]`; `span` é half-open com `offset` em bytes
UTF-8. O schema é aditivo (v1): `fixes: []` quando não há candidato.

## Quem pode ser produtor

### `safe` (poucos e condicionais)

| Código | Fase | Condição para `safe` | Risco se ignorar |
| --- | --- | --- | --- |
| **W1002** import não usado | Resolver/Loader | módulo importado **puro** (sem statements executáveis no topo), remoção não muda resolução/shadowing | remover efeito colateral do módulo |
| **W1001** local não lido | Resolver | inicializador **puro** (literal/expressão sem chamada, sem `as` que possa falhar), sem captura e sem conflito | `val x = f()` removido apaga a chamada; `as` removido deixa de lançar |
| **E3004** anotação ausente | Checker | só com tipo **exato**, sem `<error>`/type var, e sem mudar API pública | anotar `Any`/tipo inferido errado muda a checagem |

Na prática, o primeiro `safe` realista é **W1001 com inicializador literal**. W1002 só
depois de uma garantia de pureza de módulo: hoje o loader inlina statements de módulo, então
"import não usado" **não** é automaticamente seguro.

### `unsafe` (quickfix, nunca automático)

| Código | Fix possível | Por que não é safe |
| --- | --- | --- |
| **E3003** nome indefinido | trocar pelo `did you mean 'x'?` | pode ser uma variável nova, não um typo; sugestão fuzzy |
| **E2001** variável duplicada | remover/renomear a segunda | muda qual binding cada uso resolve |
| **E2002** atribuição a `val` | trocar `val`→`var` | muda captura/mutabilidade e comportamento |
| **E2009** campo imutável | trocar `val`→`var` no campo | muda API e semântica de captura |
| **E3016** campo não inicializado | adicionar `= <default>` | não há default único; `nil` pode não ser do tipo |
| **E3018** return path | adicionar `return` | valor e ponto de retorno são intenção do autor |
| **E3002** aridade | adicionar/remover argumento | não se sabe qual argumento falta/sobra |
| **E3015** override inválido | renomear método | pode ser override intencional com assinatura errada |

### Sem fix confiável

- `E3001`/`E3007` type mismatch/operandos: não há edição local que preserve a intenção.
- `E1001`–`E1007`: sintaxe; o formatter resolve espaçamento, não erro estrutural.
- `E4001` backend não suportado: não é erro do programa.
- `R1xxx`: runtime; depende de entrada/estado, não de edição de fonte.
- `C0001`: timeout; não é fonte.
- W1001 com inicializador não puro; W1002 sem pureza de módulo.

## Lote inicial recomendado

1. **W1001 `safe` literal**: só `val/var x = <literal puro>`; editar a declaração inteira
   (span da declaração), sem tocar em usos; se houver dúvida, não emitir fix.
2. **E3003 `unsafe`**: trocar o token pelo candidato de `help`; `isPreferred: false` no
   LSP; nunca auto-aplicar.
3. **W1002** depois de o loader expor “módulo sem efeitos” (ou restringir módulos a
   declarações); então `safe` para import removível.
4. **E2001/E2002/E2009** como `unsafe`, com teste de comportamento/captura.
5. **E3016/E3018/E3002/E3015** só depois de um desenho específico por código.

## Aplicação

- `lox fix` (futuro): aplica só `safe`, `--dry-run`/`--apply`, limite de 10 iterações,
  aplicação atômica por fix, detecção de conflito e `no-progress`.
- LSP `codeAction`: mostra `unsafe` como quickfix; `safe` pode ser `isPreferred`.
- MCP: expõe `fixes[]`; agente pode propor edits, mas `safe` só o compilador marca.
- Nunca: auto-aplicar `unsafe`, gerar fix a partir de mensagem/`help` sem estrutura,
  editar múltiplos arquivos sem mapa de módulos.

## Perguntas abertas

- Pureza de inicializador: literal apenas ou uma pequena álgebra (variável, unário,
  binário sem chamada)? Qual o conjunto que dá para provar barato?
- Módulos podem ter statements executáveis? Se sim, W1002 precisa de análise de efeitos;
  se não, o loader deve recusar e aí o fix fica trivial.
- W1001 deve remover a declaração ou renomear para `_`? Remover é mais limpo, mas só se o
  inicializador for puro.
- `fixes[]` fica no `Diagnostic` (sim, decisão atual) ou em um catálogo separado por
  código? O modelo atual evita uma segunda fonte.
- Fix multi-arquivo (renomear símbolo de módulo) fica fora até existir `lox fix` e
  `WorkspaceEdit` com mapa de módulos.
