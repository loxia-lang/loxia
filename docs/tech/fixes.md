# Fixes confiáveis: quem produz, o que é seguro e o que fica para depois

**Status:** `W1001`/`W1002` (`safe`); `E2001`/`E2002`/`E2009`/`E3002`/`E3003`/
`E3015`/`E3016`/`E3018` (`unsafe`); `E3004` (`safe` em função local/lambda, `unsafe` em
API pública); `loxia fix` (safe-only) e `codeAction` implementados (2026-11-16).
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
| `loxia fmt` | formatação, não é `fixes[]` |

Um fix só é `safe` quando o produtor consegue provar que a edição:

1. preserva comportamento (sem efeito colateral, sem remover exceção possível);
2. não muda resolução de nome (escopo/shadowing/captura);
3. não muda tipo nem API pública;
4. é atômica, determinística e idempotente;
5. passa no teste aplicar → reparsear → `--check` → executar antes/depois (I1).

Sem prova, o máximo é `unsafe`: útil como quickfix de editor, nunca aplicado pelo
`loxia fix` nem por um agente sem confirmação.

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
| **W1002** import não usado | Resolver/Loader | módulos só têm declarações (loader recusa statement executável) e imports **não são re-exportados**; sem uso em valor/tipo, remover a linha é seguro | remover import usado em tipo/valor ou re-exportado |
| **W1001** local não lido | Resolver | renomeia a declaração para `_unused_N` único (não remove); o inicializador continua executando | nome novo colidir ou mudar shadowing (mitigado pelo conjunto de nomes) |
| **E3004** anotação ausente | Checker | tipo **exato** de default literal ou de `return` literais iguais, em função local/lambda (não muda API pública); sem `<error>`/type var | anotar `Any`/tipo inferido errado muda a checagem |

Implementados: **W1001** (rename), **W1002** (remove import; pureza estrutural: o loader
só aceita declarações em módulo e imports não são re-exportados), **E3003**
(did-you-mean), **E2002** (`val`→`var` local), **E2009** (`val`→`var` campo) e **E3004**
(anotação exata; `safe` só em função local/lambda).
A pureza de módulo **já é garantida pelo loader**: não há como um import executar
statement no topo, então o risco residual é só uso/re-export, coberto pelo scan
conservador (valor + anotação de tipo).

### `unsafe` (quickfix, nunca automático)

| Código | Fix possível | Por que não é safe |
| --- | --- | --- |
| **E3003** nome indefinido | trocar pelo `did you mean 'x'?` | pode ser uma variável nova, não um typo; sugestão fuzzy |
| **E2001** variável duplicada | renomear a segunda + todos os usos (implementado) | muda qual binding cada uso resolve |
| **E2002** atribuição a `val` | trocar `val`→`var` (implementado) | muda captura/mutabilidade e comportamento |
| **E2009** campo imutável | trocar `val`→`var` no campo (implementado) | muda API e semântica de captura |
| **E3016** campo não inicializado | adicionar `= <default>` (implementado p/ primitivos/opcionais) | default é escolha; sem default único para classes |
| **E3018** return path | adicionar `return <default>` (implementado p/ primitivos/opcionais) | valor é intenção do autor |
| **E3002** aridade | remover argumentos extras (implementado; faltando não tem fix) | não se sabe qual argumento sobra |
| **E3015** override inválido | renomear método (implementado) | pode ser override intencional com assinatura errada |
| **E3004** anotação em API pública | anotar com o tipo exato (implementado) | adiciona tipo à assinatura pública; o autor pode querer outro tipo |

### Sem fix confiável

- `E3001`/`E3007` type mismatch/operandos: não há edição local que preserve a intenção.
- `E1001`–`E1007`: sintaxe; o formatter resolve espaçamento, não erro estrutural.
- `E4001` backend não suportado: não é erro do programa.
- `R1xxx`: runtime; depende de entrada/estado, não de edição de fonte.
- `C0001`: timeout; não é fonte.
- E2001 com usos fora do escopo ou colisão de nome: o fix só cobre o binding local e seus usos resolvidos.
- E3004 sem tipo exato (parâmetro sem default, campo sem inicializador, `return` não literal ou tipos discordantes): a anotação seria um chute.

## Lote inicial

1. ✅ **W1001 `safe`**: renomeia a declaração para `_unused_N` (preserva o inicializador).
2. ✅ **E3003 `unsafe`**: troca o token pelo candidato de `help`; `isPreferred: false`.
3. ✅ **W1002 `safe`**: remove a linha de import não usada; pureza estrutural do loader.
4. ✅ **E2002/E2009 `unsafe`**: troca `val`→`var` no local/campo; nunca auto-aplicado.
5. ✅ **E2001/E3016/E3018/E3002/E3015**: rename com usos, default primitivo, return
   default, remoção de argumentos extras e rename de método.
6. ✅ **E3004**: anota `safe` em função local/lambda e `unsafe` em API pública; só com
   default literal ou `return` literais iguais. Sem tipo exato, não emite fix.

## Aplicação

- `loxia fix` (implementado): aplica só `safe`, `--apply` (padrão dry-run), limite de 10 iterações,
  aplicação atômica por fix, detecção de conflito e `no-progress`.
- LSP `codeAction`: mostra `unsafe` como quickfix; `safe` pode ser `isPreferred`.
- MCP: expõe `fixes[]`; agente pode propor edits, mas `safe` só o compilador marca.
- Nunca: auto-aplicar `unsafe`, gerar fix a partir de mensagem/`help` sem estrutura,
  editar múltiplos arquivos sem mapa de módulos.

## Perguntas abertas

- Pureza de inicializador não é mais necessária para W1001: renomear preserva a execução.
- Módulos **não** têm statements executáveis (loader recusa); W1002 é estruturalmente seguro.
- `fixes[]` fica no `Diagnostic` (sim, decisão atual) ou em um catálogo separado por
  código? O modelo atual evita uma segunda fonte.
- Fix multi-arquivo (renomear símbolo de módulo) fica fora até existir `loxia fix` e
  `WorkspaceEdit` com mapa de módulos.
