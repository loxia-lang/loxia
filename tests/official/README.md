# Suíte oficial do Crafting Interpreters (caps. 10–13)

Casos copiados do repositório oficial:

- <https://github.com/munificent/craftinginterpreters>
- commit `4a840f70f69c6ddd17cfef4f6964f8e1bcd8c3d4`
- diretórios: `function`, `closure`, `call`, `return`, `class`, `constructor`,
  `field`, `method`, `inheritance`, `super`, `this`
- os arquivos `.lox` são MIT; o `LICENSE` original está em [`LICENSE`](LICENSE).

Os arquivos são mantidos **como no original** (`fun`, comentários `//`, campos
dinâmicos). O runner [`../test_official_suite.py`](../test_official_suite.py) adapta na
hora:

1. `fun` → `fn` (nossa keyword);
2. comentários `//` → `#` (nossa sintaxe; `//` virou divisão);
3. `class B < A` → `class B(A)` (nossa sintaxe de herança do ADR-0008);
4. campos atribuídos com `this.x = ...` são declarados automaticamente como
   `var x = nil` no topo da classe, porque desde o ADR-0009 não existe campo dinâmico e
   todo campo precisa ser inicializado;
5. sete testes que dependem de **criar campo por fora** são `xfail` por divergência
   intencional do ADR-0009: `field/call_function_field.lox`,
   `field/call_nonfunction_field.lox`, `field/get_and_set_method.lox`, `field/many.lox`,
   `field/method_binds_this.lox`, `field/on_instance.lox` e
   `field/set_evaluation_order.lox`. `field/get_on_*`/`set_on_*` (que testam erro em
   primitivos) passam normalmente;
6. `inheritance/parenthesized_superclass.lox` testa a sintaxe antiga `< (Foo)` de
   propósito; é `xfail` (o teste equivalente na nossa sintaxe seria outro);
7. expectativas são traduzidas: `// expect:` → stdout, `// expect runtime error:` →
   stderr/exit 70, `// [line N] Error...` → erro de compilação/exit 65.

Resultado atual: **120 casos, 112 passando e 8 `xfail`**. Não é uma suíte de conformidade:
é uma rede extra para o interpretador, especialmente para funções, closures, classes,
herança, `super` e `this`. As diferenças estão no
[ADR-0009](../../docs/adr/0009-defaults-e-campos.md) e no
[ADR-0011](../../docs/adr/0011-fn-elif-ponto-e-virgula.md).

Rodar:

```bash
uv run pytest tests/test_official_suite.py -q
uv run pytest tests/test_official_suite.py -q -k inheritance
```
