# Suíte oficial do Crafting Interpreters (caps. 10–13)

Casos copiados do repositório oficial:

- <https://github.com/munificent/craftinginterpreters>
- commit `4a840f70f69c6ddd17cfef4f6964f8e1bcd8c3d4`
- diretórios: `function`, `closure`, `call`, `return`, `class`, `constructor`,
  `field`, `method`, `inheritance`, `super`, `this`
- os arquivos `.lx` são MIT; o `LICENSE` original está em [`LICENSE`](LICENSE).

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
   intencional do ADR-0009: `field/call_function_field.lx`,
   `field/call_nonfunction_field.lx`, `field/get_and_set_method.lx`, `field/many.lx`,
   `field/method_binds_this.lx`, `field/on_instance.lx` e
   `field/set_evaluation_order.lx`. `field/get_on_*`/`set_on_*` (que testam erro em
   primitivos) passam normalmente;
6. `inheritance/parenthesized_superclass.lx` testa a sintaxe antiga `< (Foo)` de
   propósito; é `xfail` (o teste equivalente na nossa sintaxe seria outro);
7. expectativas são traduzidas: `// expect:` → stdout, `// expect runtime error:` →
   stderr/exit 70, `// [line N] Error...` → erro de compilação/exit 65;
8. `clock` foi removido da 1.0 ([ADR-0026](../../docs/adr/0026-freeze-1.0.md)); em
   `function/print.lx`, ele é trocado por `len`, que também imprime `<native fn>`.
9. para o `--check`, [`../official_annotations.py`](../official_annotations.py) aplica uma
   camada dinâmica (`Any`) sobre a fonte adaptada — os `.lx` originais continuam
   intactos. [`../test_official_check.py`](../test_official_check.py) cobre os **59
   positivos**; os 56 negativos esperam erro (e não são anotáveis) e os 7 `xfail` de campo
   dinâmico + `parenthesized_superclass` ficam fora.

Resultado atual: **120 casos, 112 passando e 8 `xfail`**; **59 positivos passam no
`--check`**. Não é uma suíte de conformidade: é uma rede extra para o interpretador,
especialmente para funções, closures, classes, herança, `super` e `this`. As diferenças
estão no [ADR-0009](../../docs/adr/0009-defaults-e-campos.md) e no
[ADR-0011](../../docs/adr/0011-fn-elif-ponto-e-virgula.md).

Rodar:

```bash
uv run pytest tests/test_official_suite.py -q
uv run pytest tests/test_official_suite.py -q -k inheritance
```
