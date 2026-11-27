---
name: lox-git-flow
description: Fluxo de branches da Loxia — main como release, dev como integração, feature→dev por squash, release dev→main e hotfix.
whenToUse: Antes de criar branch, abrir PR, mergear, cortar release ou resolver conflito de fluxo.
---

# Fluxo de branches e PRs (Loxia)

Use esta skill antes de criar branch, abrir PR, mergear ou cortar release. As regras
remotas são aplicadas por **rulesets** do GitHub; não confie só na convenção.

## Modelo

| Branch | Papel | Regra |
| --- | --- | --- |
| `main` | release, default | protegida: sem deletion/force-push, PR obrigatório, `CI success` |
| `dev` | integração longeva | protegida: sem deletion/force-push, PR obrigatório, `CI success` |
| `feat/*`, `fix/*`, `docs/*`, `test/*`, `chore/*` | trabalho | nasce de `dev`, morre no merge |

- **Nunca** commite direto em `main` ou `dev`; exceção só de emergência com bypass de admin,
  e registre no PR/issue.
- **Nunca** mergeie `dev` com `--delete-branch`: `dev` é permanente.
- O repositório está com **auto-delete de branch desligado** (`delete_branch_on_merge=false`).
  Apague a branch de feature manualmente (`git push origin --delete feat/x`) ou use
  `gh pr merge --squash --delete-branch` no PR da feature.
- Issues fecham no PR da feature (`Closes #N`), não no PR de release.

## Feature / fix

```bash
git switch dev
git pull --ff-only
git switch -c feat/minha-coisa
# ... commits com -s ...
git push -u origin feat/minha-coisa
gh pr create --base dev --head feat/minha-coisa \
  --title "feat(scope): ..." --body "Closes #N."
```

- Feature PR entra em `dev` com **squash**; o título do PR vira o commit e precisa passar
  em `tools/check_pr_title.py`.
- Espere `CI success`; só então `gh pr merge --squash --delete-branch`.
- Se o PR for seu e não houver revisor, o ruleset permite 0 aprovações, mas os checks são
  obrigatórios.

## Release

```bash
git switch dev
git pull --ff-only
gh pr create --base main --head dev --title "release: vX.Y.Z"
# checks verdes; merge commit (não delete dev)
gh pr merge --merge
```

- `main` só recebe `dev` (ou hotfix excepcional).
- Depois do merge, sincronize: `git switch dev && git fetch && git merge --ff-only origin/main`.
- Tag/release saem de `main` pelo workflow de release, nunca de `dev`.

## Hotfix excepcional

1. `git switch main && git pull --ff-only && git switch -c fix/nome`.
2. PR `fix/nome` → `main`, merge, tag.
3. Sincronize `main` de volta em `dev` (`git switch dev; git merge --no-ff origin/main`) ou
   abra PR `main` → `dev` se o ruleset exigir PR.

## Antes de abrir/mergear

```bash
make check            # gate completo; CI roda o backend
make docs-build       # se mexeu em docs/site
uv run python tools/check_pr_title.py "feat(scope): ..."
```

- Assine os commits (`git commit -s`); DCO é obrigatório.
- Um PR = uma mudança lógica; teste de regressão no mesmo PR.
- Não use bypass de admin para “resolver” check vermelho.
