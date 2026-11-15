// GERADO por editors/build_grammar.py --write; não edite à mão.
// Consumido por Shiki (site de docs e viewer do harness), que usa o mesmo
// JSON do VS Code. A grammar é indentada por `name` = id, então o shim
// renomeia para `loxia` e adiciona o alias `lx`.
import grammar from '../vscode/syntaxes/loxia.tmLanguage.json' with { type: 'json' }

export default [
  { ...grammar, name: 'loxia', displayName: 'Loxia', aliases: ['lx'] },
]
