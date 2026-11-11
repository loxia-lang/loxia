---
name: lox-testing
description: Como escrever, rodar e organizar testes neste repositório — casos golden .lox com expectativas, exit codes do CLI e testes unitários em pytest.
whenToUse: Ao adicionar um teste, fazer a suíte passar, investigar uma falha ou transformar um bug em caso de regressão.
---

# Testes

## Comandos

```bash
make test                          # pytest (unit + golden)
uv run pytest -k block             # subconjunto
make case                          # runner golden sem pytest
uv run python -m tests.runner for  # um caso (filtro por substring)
```

## Caso golden (`tests/cases/*.lox`)

O próprio `.lox` carrega a expectativa em comentário:

```lox
print 1 + 2;                          # expect: 3
print naoexiste;
# expect runtime error: Undefined variable 'naoexiste'.
```

Marcadores aceitos (qualquer posição; a ordem das linhas `# expect:` é a ordem
esperada do stdout):

| Marcador | Efeito |
|---|---|
| `# expect: X` | linha de stdout esperada |
| `# expect runtime error: MSG` | stderr contém MSG; exit **70** |
| `# expect error: MSG` | erro de sintaxe/resolução; exit **65** |
| `# expect exit: N` | exit code explícito |

Exit codes do CLI: 65 sintaxe, 70 runtime, 66 arquivo não encontrado.
Se não houver marcador de erro, o teste exige stdout idêntico, stderr vazio e exit 0.

## Regra de ouro

Todo bug corrigido vira caso em `tests/cases/` **no mesmo commit**. Se o caso já
existia, ele falhou antes do fix — cite isso na mensagem de commit.

## Testes unitários (`tests/test_*.py`)

- Não existe mais estado global de erro: cada `Lox.run` cria seu `ErrorReporter`. Em
  teste, inspecione `lox.reporter` / `scanner.reporter` / `parser.reporter`.
- Scanner/parser: prefira helpers pequenos (`scan`, `parse`, `ast`) a duplicar setup.
- Interpreter: `run(source, capsys)` captura stdout/stderr; não use `print` no teste.
- Para AST, compare com `AstPrinter` — é o snapshot canônico da árvore.

## Armadilhas

- O runner procura `#` em **qualquer** posição da linha (expectativa no fim da
  linha, como no livro). Comentário com `#` dentro de string ainda funciona?
  Evite: pode ser confundido com expectativa.
- Números são `float`: `print 3;` sai `3` por causa do `stringify`, não porque é int.
- Teste de REPL usa `Parser(tokens, repl=True)`; sem isso o `;` é obrigatório.
- Não "conserte" a expectativa para o teste passar. Se o comportamento está errado,
  o código está errado.
