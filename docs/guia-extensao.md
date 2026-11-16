# Guia de extensão

Como acrescentar topologias de projeto, categorias e componentes, e manter as regras do projeto
(`CLAUDE.md`). Antes de começar: `scripts/check.sh` deve passar.

## 1. Nova topologia de projeto (plug-in)

Cada topologia é um pacote em `backend/src/circuitos/design/plugins/<id>/`, sem mudança no núcleo.
Use um módulo pequeno como modelo (`plugins/zen/module.py`).

```text
plugins/meu/
  __init__.py      # from .module import MeuModule, MeuSpec
  module.py        # especificação, equações, circuito, esquemático, BOM
```

### 1.1 A especificação

Uma classe Pydantic com valores padrão razoáveis e limites (`Field(ge=…, le=…)`). Grandezas com
unidade usam `QuantityModel` (`{"value", "unit"}`); a interface gera o formulário e os controles
deslizantes a partir do esquema JSON.

### 1.2 A classe do módulo

Atributos: `id` (ex.: `"DM-MEU"`), `family`, `title`, `spec_schema`. Opcionais para a interface e o
relatório: `labels`, `spec_labels`, `enum_labels`, `lab` (itens do roteiro), `questions`,
`practice`, `safety`.

Métodos (contrato `TopologyModule` em `design/engine.py`):

| Método | Faz |
|---|---|
| `roles(spec)` | posições que recebem componente do catálogo (designador, categoria, quantidade) |
| `required_ratings(role)` | parâmetros que o componente precisa ter para ser candidato |
| `analyse(spec, devices)` | equações: devolve `Analysis` com a memória (`CalcLog`), esforços, resumo, perdas, avisos e formas de onda |
| `build_circuit(spec, devices, summary)` | netlist SPICE, pontas de prova e `SimCheck` (grandeza, métrica, tolerância e justificativa) |
| `ambient(spec)`, `interface_resistance(spec)` | dados do modelo térmico |
| `schematic(spec, result, title)` | SVG do esquemático |
| `bom_extra(spec, result)` | linhas de passivos e itens a especificar (`reports/common.py`) |

O motor (`design/engine.py`) faz o resto: seleção com derating, recálculo com os parâmetros reais
até convergir, temperatura de junção e dissipador, margens.

### 1.3 Regras para as equações

- Toda grandeza carrega unidade (`pint`); magnitudes nuas só dentro de funções `@magnitudes`.
- Cada valor calculado entra na memória com `record(...)`: LaTeX, entradas, premissas e
  `BibRef` (livro, edição, capítulo, equação). Não chute número de equação: deixe
  `verified=False` até conferir no livro.
- Use as mesmas equações de dispositivo que o ngspice (`design/devmodels.py`) quando o resultado
  for conferido por simulação.

### 1.4 Registrar e testar

1. Acrescente a instância em `design/registry.py` (`MODULES`).
2. Testes obrigatórios:
   - `tests/golden/test_gt_<id>.py`: pelo menos três exemplos resolvidos de livro ou nota de
     aplicação, com a fonte e a tolerância no docstring;
   - `tests/analytic_vs_sim/`: o mesmo caso conferido no ngspice (`@pytest.mark.ngspice`);
   - `tests/property/`: conservação de energia, limites físicos.
3. `docs/validacao/<modulo>.md` com a tabela de casos, erros e limitações, para revisão.

O relatório (HTML e PDF), a lista de materiais, a netlist KiCad e os projetos salvos funcionam
para o novo módulo sem código adicional.

## 2. Nova categoria de componente

1. Esquema em `backend/src/circuitos/components/schemas/<categoria>.yaml`: parâmetros com unidade,
   tipo (`max_rating`, `characteristic`, `thermal`, `geometry`), condições de ensaio exigidas e a
   lista `required` (o que precisa estar conferido para liberar). `extends` herda de outra
   categoria.
2. Se o datasheet imprime os símbolos de outro jeito, acrescente as grafias em
   `datasheets/aliases.yaml` (usado pela importação de PDF).
3. Rótulo e destaques na interface: `CATEGORY_LABEL` em `frontend/src/pages/CatalogPage.tsx` e
   `_HIGHLIGHT` em `api/catalog.py`.

## 3. Novos componentes

- **Pela interface**: aba Importar datasheet (fica no banco local, em revisão).
- **No repositório** (para todos os usuários): um YAML em `data/components/<categoria>/`, com
  `datasheets` (URL, documento, revisão, SHA-256) e cada parâmetro com `source` (página e
  localização). Famílias que compartilham um datasheet usam `parts:` e `per_part:`. Para
  substituir um registro já importado, aumente `catalog_revision`.
- Nunca preencha valores de memória: sem certeza, `status: a_verificar`. O teste DS
  (`pytest -m datasheet`) baixa os PDFs e confere valores contra o texto.

## 4. Nova bancada de dispositivo

Modelo em `backend/src/circuitos/devices/` (funções com unidade, mesmas equações do SPICE),
endpoint em `api/devices.py` e página em `frontend/src/pages/`. Teste AS comparando a curva com o
ngspice.

## 5. Verificação

```bash
scripts/check.sh            # lint, tipos, contratos, testes (cobertura ≥ 80 %), build
scripts/e2e.sh              # navegador (Playwright)
uv run pytest -m datasheet  # datasheets reais (rede)
```
