# Editores — destaque de sintaxe da Loxia

Grammar **TextMate** (`syntaxes/loxia.tmLanguage.json`) + extensão de VS Code. O mesmo
arquivo serve Sublime Text, TextMate, VS Code e, quando a linguagem entrar no
[linguist](https://github.com/github-linguist/linguist), o `github.com` — ele exige uma
grammar TextMate vendorizada e 2.000+ arquivos `.lx` em repos públicos (ver `TODO.md` §14).

## Instalar no VS Code

**Jeito rápido (uma linha, sem instalar nada):**

```bash
code --extensionDevelopmentPath="$PWD/editors/vscode" .
```

O VS Code abre com a extensão carregada em modo desenvolvimento. Abra um `.lx` e o rodapé
direito deve mostrar **Loxia** (não "Plain Text") — dali em diante o tema colore.

**Jeito "instalada" (some do modo dev):**

```bash
ln -s "$PWD/editors/vscode" ~/.vscode/extensions/loxia-1.0.0
```

e recarregue a janela (`Developer: Reload Window` / `Ctrl+Shift+P`). Ou, dentro de
`editors/vscode`, aperte `F5` — o `.vscode/launch.json` já está lá e abre o *Extension
Development Host* com a extensão carregada.

### Não apareceu cor? Nesta ordem

1. **Rodapé diz "Plain Text"?** A extensão não foi carregada: o `.lx` não é reconhecido.
   Confira `~/.vscode/extensions | grep loxia` e recarregue a janela; `F5` **sem** o
   `launch.json` só abre o diálogo "Select environment" e não carrega nada.
2. **Rodapé diz "Loxia" mas está tudo cinza?** O arquivo está sendo lido como `loxia`, mas
   o tema não mapeia os scopes. `Ctrl+Shift+P` → **Developer: Inspect Editor Tokens and
   Scopes** e clique numa keyword: os scopes devem listar `keyword.control.loxia` etc. Se
   listar, é o tema (troque para Dark+ para testar); se não listar, é a grammar.
3. **`F5` reclama de "Select environment"?** Falta o `launch.json` — ele existe neste
   diretório desde a versão 1.0.0 do editor; garanta que você abriu `editors/vscode` como
   **workspace** (e não a raiz do repo).
4. **Abriu o `.lx` antes de instalar?** Feche e reabra o arquivo: o modo de linguagem é
   decidido ao abrir, não é reavaliado na hora.

## Sublime Text / TextMate

Copie `vscode/syntaxes/loxia.tmLanguage.json` para o pacote do editor (no Sublime, um
diretório em `Packages/`; no TextMate, `~/Library/Application Support/TextMate/Bundles`).

## A grammar é gerada — não edite o JSON

`editors/build_grammar.py` monta o JSON a partir de:

| Fonte | O que entra |
| --- | --- |
| `loxia_core/frontend/keywords.py` (`KEYWORDS`) | todos os 32 keywords, agrupados por scope |
| `loxia_core/frontend/token_type.py` (`TokenType`) | operadores (`**`, `??`, `?.`, `..`, `>>>`…) e pontuação |
| `loxia_core/execution/prelude.py` (`BUILTIN_NAMES`) | `Int`, `Result`, `RuntimeError`, `len`, `math`… |

```bash
make grammar       # uv run python editors/build_grammar.py --write
uv run python editors/build_grammar.py --check   # exit 1 se o JSON estiver defasado
```

`tests/test_editor_grammar.py` roda o `--check` no `make check`, então keyword/operador
novo sem `make grammar` quebra o build — o destaque não apodrece.

Categorizar keyword nova é decisão humana: `KEYWORD_GROUPS` em `build_grammar.py` tem que
cobrir `KEYWORDS` exatamente, e o gerador falha de propósito se sobrar ou faltar uma.

## Shiki (site de docs e viewer do harness)

`editors/shiki/loxia.mjs` entrega a **mesma** grammar (o mesmo JSON, sem cópia) no formato
que o Shiki consome — `LanguageRegistration[]` com `name: 'loxia'` e alias `lx`. Ele é
gerado junto com o JSON (`make grammar`), então não descola.

```js
import loxia from './editors/shiki/loxia.mjs'
// shiki: createHighlighterCoreSync({ langs: [loxia], ... }) → codeToTokens(..., { lang: 'loxia' })
```

### Viewer do DeepSeek Harness

O viewer usa o mesmo Shiki, mas com **allowlist explícita**: idioma fora da tabela renderiza
texto puro, e não existe hook de plugin para registrar gramática. Fazer `.lx` aparecer lá é
um patch de **3 pontos + 1 arquivo** no checkout do harness:

1. copie `editors/dsh/loxia.ts` para
   `packages/client/ui-primitives/loxia_core/markdown/grammars/loxia.ts` (autocontido, sem dependência
   deste repo);
2. `packages/util/code-language/loxia_core/index.ts`, na tabela `LANGUAGE_EXTENSIONS`:
   `loxia: ['lx'],`
3. `packages/client/ui-primitives/loxia_core/markdown/highlight.ts`:
   - no fim do `LAZY_GRAMMARS`: `['loxia', () => import('./grammars/loxia')],`
   - no `LANG_ALIASES`: `['loxia', 'loxia'], ['lx', 'loxia'],`

Depois recompilar/recarregar o harness (`make check` ou `pnpm -r test` no checkout dele). O
`loxia.ts` é gerado aqui por `make grammar`, então atualizar a grammar exige regerar e
recopiar — o drift entre os dois repos é manual de propósito: o harness não depende deste
repo (e este não depende do harness).

## Limitações declaradas

- **`/* */` aninhado** funciona até 3 níveis (`NESTING`); depois fecha no primeiro `*/`.
  É o mesmo hack que grammars de C/JS usam — o TextMate não tem recursão real.
- **Sem análise semântica**: `Foo` capitalizado vira `entity.name.type` mesmo quando é
  variável; campo depois de `.` não é refinado.
- **`//` é divisão**, não comentário (ADR-0012). Nenhuma regra de comentário pode usar
  `//` — há teste para isso.
- Destaque no `github.com` continua sem cor até a linguagem entrar no linguist; o
  `.gitattributes` da raiz mantém os `.lx` fora das estatísticas do repo
  (`linguist-detectable=false`) em vez de marcá-los como outra linguagem.
