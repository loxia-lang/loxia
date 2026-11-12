# ADR-0020 — Assinaturas explícitas e funções declaradas depois

- **Status:** accepted
- **Data:** 2026-11-12
- **Decisores:** Cássio + agente (DSH)
- **Relacionados:** [ADR-0010](0010-tipagem-estatica.md),
  [ADR-0014](0014-identidade-e-invariantes.md), [`../../TODO.md`](../../TODO.md) §2,
  [`../../TIPOS.md`](../../TIPOS.md) §7,
  [`../spec/semantica.md`](../spec/semantica.md)
- **Implementação:** [`src/checker.py`](../../src/checker.py),
  [`tests/test_checker.py`](../../tests/test_checker.py)

## Contexto

O `TODO.md` descrevia o T3 como “parâmetro sem anotação vira `TyVar` e unifica a cada
chamada”. A discussão com o autor da linguagem mostrou que o ideal é o contrário:
**parâmetros e retorno continuam assinados**; a assinatura é contrato, não algo que o
checker adivinha. Inferir parâmetros sem generalização (T4) fica monomórfico e dependente
da ordem das chamadas, e ainda dificulta o codegen.

Ao testar o checker atual, apareceram dois problemas práticos:

```lox
fn par(n: Int) -> Bool {
  if (n == 0) { return true; }
  return impar(n - 1);        # erro: Undefined variable 'impar'
}
fn impar(n: Int) -> Bool {
  if (n == 0) { return false; }
  return par(n - 1);
}
```

e uma mensagem confusa ao passar a classe em vez da instância:

```lox
fn recebe(a: Animal) -> String { return a.falar(); }
recebe(Animal);   # Expected Animal, found Animal.
```

## Decisão

1. **Anotações continuam obrigatórias** em todos os parâmetros e no retorno no modo
   `--check`; `init` continua sem retorno. O T3 literal (inferir parâmetro sem anotação)
   fica **adiado**; se um dia entrar, vem depois de generalização (T4) e com regras
   explícitas.
2. **Assinaturas de funções de topo são calculadas antes dos corpos.** O corpo de uma
   função pode chamar outra função declarada depois, inclusive recursão mútua. A
   assinatura é calculada uma vez e guardada por nó de AST; o corpo reutiliza essa
   assinatura.
3. **O código de topo continua na ordem dos statements.** Uma chamada solta antes da
   declaração (`print f(); fn f() ...`) ainda é erro de compilação e de runtime. A
   pré-declaração vale para corpos de função, que executam depois das declarações
   normalmente.
4. **Erros de chamada identificam o argumento**: `Argument 2: Expected String, found Int.`
   Quando uma classe é passada onde se espera uma instância, a mensagem é específica:
   `Expected an instance of Animal, found the class Animal.`
5. **Nada muda no runtime**: tipos continuam apagados; o tree-walk continua a
   especificação executável. Sem generics (`fn id[T]`), sem `TyVar`, sem unificação nesta
   etapa.

## Consequências

### Positivas

- Recursão mútua entre funções de topo passa a ser checável, que é o caso mais comum de
  “declaração para frente”.
- A assinatura é um contrato explícito e legível; o corpo pode ser checado sem depender da
  ordem das chamadas.
- Mensagens de chamada apontam o argumento culpado e distinguem classe de instância.
- Nenhuma sintaxe nova e nenhum custo no interpretador; o checker continua opt-in.

### Negativas / custos

- **Ordem de topo ainda importa** para statements soltos. A pré-declaração não hoista
  funções em runtime: se uma função for chamada antes da declaração da função que ela
  usa, o checker pode aceitar e o runtime falhar. É uma limitação de checagem estática,
  registrada para revisão quando o runtime ganhar hoisting (se ganhar).
- **Métodos e campos de classes declaradas depois** continuam sujeitos à ordem de visita
  da classe; só as assinaturas de funções de topo são antecipadas.
- Redeclarações de topo com o mesmo nome continuam ambíguas e seguem a ordem dos
  statements.
- Ainda não há tipo de função como anotação (`fn(Int) -> Int`), generics, nem inferência
  de parâmetro; ficam para T3b/T4.

## Alternativas consideradas

| Alternativa | Por que não agora |
| --- | --- |
| T3 literal: parâmetro sem anotação vira `TyVar` | Contraria o ideal de assinatura explícita; sem T4 fica monomórfico e dependente da ordem das chamadas; mensagens culpam o call site |
| Hoistar declarações de função no runtime | Mudaria a ordem de execução e o shadowing (`var f` antes/depois de `fn f`); decisão de linguagem maior |
| Manter tudo order-dependent e exigir declaração antes do uso | Recursão mútua é comum e o erro “Undefined variable” é ruim de diagnosticar |
| Resolver só chamadas dentro de funções, sem pré-declarar | É o que foi feito; a assinatura é antecipada, mas a ordem de topo continua valendo |
| Tipos de função + generics nesta etapa | Escopo maior; ficam para T3b, depois de validar a pré-declaração |

## Como verificar

- `tests/test_checker.py`:
  - `test_functions_can_call_functions_declared_later` (recursão mútua limpa);
  - `test_top_level_call_before_declaration_is_an_error` (ordem de topo preservada);
  - `test_call_error_reports_the_argument_position`;
  - `test_class_value_is_not_an_instance`.
- `make check` verde (ruff + mypy strict + pytest).

Critério para revisar: quando T3b (generics explícitos) ou T4 (generalização) entrarem; se
o runtime ganhar hoisting de funções; ou se a pré-declaração causar falso positivo em
código real.
