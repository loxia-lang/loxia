# ADR-0101 — Licença dual MIT/Apache-2.0 e política de contribuição

- **Status:** accepted (implementação parcial: DCO/CONTRIBUTING na abertura do repo)
- **Data:** 2026-11-17
- **Decisores:** Cassio Dalla (dono do projeto) e agente
- **Relacionados:** [ADR-0078](0078-nome-loxia-extensao-lx.md),
  [ADR-0014](0014-identidade-e-invariantes.md), [`../../TODO.md`](../../TODO.md) §14.1

## Contexto

O projeto nasceu sob MIT (`LICENSE`, Copyright 2026 Cassio Dalla). A abertura do
repositório (§14.1) exige uma licença que sirva a três públicos ao mesmo tempo:

- quem só quer usar o interpretador sem cerimônia;
- quem embute o runtime do backend nativo em um binário e não quer obrigação de NOTICE;
- empresas e projetos que exigem uma concessão explícita de patentes antes de adotar uma
  linguagem.

MIT é permissiva e compatível com GPLv2, mas é silenciosa sobre patentes e marcas.
Apache-2.0 tem concessão explícita de patentes, cláusula de marca (§6) e termos de
contribuição, mas é incompatível com GPLv2 e exige NOTICE — atrito para quem embute o
runtime. O histórico é de um autor só, então a relicença é barata **agora**; depois de
contribuições externas, exigiria consentimento de todo mundo.

A suíte oficial do livro em `tests/official/` é MIT (`tests/official/LICENSE`);
`tests/official/` mantém a licença original e não é relicenciado.

## Decisão

1. **Licença outbound:** `MIT OR Apache-2.0`, à escolha de quem usa. O repositório
   distribui `LICENSE-MIT`, `LICENSE-APACHE` e `NOTICE`; o metadado PEP 639 do
   `pyproject.toml` declara `license = "MIT OR Apache-2.0"` e
   `license-files = ["LICENSE-MIT", "LICENSE-APACHE"]`.
2. **Contribuições:** *inbound = outbound*. Quem contribui licencia sob as duas licenças,
   sem termos adicionais, e certifica o **Developer Certificate of Origin 1.1** com
   `git commit -s` (DCO; sem CLA).
3. **Terceiros:** `tests/official/` permanece MIT, com o `LICENSE` original e atribuição
   no `NOTICE`. O runtime C do projeto é próprio; a `libgc` é linkada no build e não é
   embutida no wheel.
4. **Sem licença separada para docs por enquanto.** `docs/`, ADRs e o README seguem a
   licença do projeto; uma licença de documentação (ex.: CC-BY-4.0) pode ser um ADR futuro,
   se houver demanda de reuso.
5. **Sem CLA.** A opção de relicenciar para uma licença não aberta não é preservada: isso
   exigiria consentimento dos contribuidores. Se essa necessidade aparecer, o caminho é um
   ADR novo, não uma mudança silenciosa.

## Consequências

### Positivas

- Quem quer simplicidade escolhe MIT; quem quer patent grant e termos formais escolhe
  Apache-2.0. O projeto não fecha nenhuma das portas.
- Compatibilidade com GPLv2 via MIT, que Apache-2.0 sozinha não oferece.
- A cláusula §6 do Apache deixa claro que a licença não concede direitos de marca; o nome
  Loxia e o logo continuam protegidos por uma política de marca separada.
- O metadado do PyPI passa a declarar a licença (antes não declarava nada).

### Negativas / custos

- Dois arquivos de licença e um NOTICE para manter; a escolha “MIT ou Apache” precisa ser
  explicada no README.
- Quem usa Apache-2.0 precisa preservar o NOTICE ao distribuir o trabalho.
- DCO adiciona fricção a contribuidores (assinatura no commit).
- Sem CLA, relicenciar no futuro fica caro ou impossível sem consentimento.

### Neutras

- A licença não muda o comportamento da linguagem nem o I1–I4.
- As tags e releases antigas continuam sob MIT; a licença dual vale do commit de adoção em
  diante.

## Alternativas consideradas

| Alternativa | Por que não |
| --- | --- |
| Continuar MIT | Menor custo, mas sem patent grant e sem cláusula de marca; não endereça o público corporativo. |
| Apache-2.0 sozinha | Mais simples que dual, mas incompatível com GPLv2 e NOTICE obrigatório para quem embute o runtime. |
| MPL-2.0 | Copyleft por arquivo + patent grant; atrito para embutir o runtime e para adoção por empresas. |
| GPL/LGPL com exceção de linking | Inviabiliza adoção de uma linguagem nova; o custo jurídico não paga. |
| CLA + licença dual | Preserva relicenciamento, mas afasta contribuidores; DCO é o padrão para projeto pequeno. |

## Como verificar

- `LICENSE-MIT`, `LICENSE-APACHE` e `NOTICE` existem na raiz e entram no sdist/wheel.
- `pyproject.toml` declara `MIT OR Apache-2.0` e os dois `license-files`.
- `README.md` tem a seção “License” com a escolha e o texto de inbound=outbound.
- `tests/test_license.py` policia os arquivos, o metadado e a seção do README.
- `tests/official/LICENSE` continua MIT e o `NOTICE` atribui a suíte ao Robert Nystrom.
- O `CONTRIBUTING.md` (PR de comunidade) documenta o DCO e o `git commit -s`.

## Referências

- [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)
- [MIT License](https://opensource.org/license/mit)
- [SPDX: MIT OR Apache-2.0](https://spdx.org/licenses/MIT.html)
- [Rust: licensing](https://rust-lang.org/policies/licenses/) — precedente do dual MIT/Apache
- [DCO 1.1](https://developercertificate.org/)
