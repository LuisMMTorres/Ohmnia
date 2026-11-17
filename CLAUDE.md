# CLAUDE.md — convenções do projeto

Sistema de projeto, dimensionamento, seleção de componentes reais e simulação de circuitos de Eletrônica Analógica e Eletrônica de Potência. Especificação completa: `docs/escopo.md`, `docs/arquitetura.md`, `docs/modelo-de-dados.md`. Status: `docs/roadmap.md`.

## Regras inegociáveis

1. **Nunca inventar parâmetros de componentes.** Todo valor no banco tem fonte (fabricante, documento, revisão, página/tabela). Sem certeza → `status: a_verificar` ou campo vazio. Não preencher datasheet de memória, nem em testes, nem em exemplos.
2. **Toda grandeza carrega unidade.** `pint.Quantity` no núcleo; `{"value", "unit"}` na API. Magnitudes nuas só dentro de funções `@magnitudes(...)`.
3. **Todo resultado é auditável.** Funções de cálculo retornam `Calculated[T]` com `CalcStep` (LaTeX, entradas, premissas, referência bibliográfica com livro, edição, capítulo e equação).
4. **Analítico e simulação devem concordar.** Divergência acima da tolerância vira aviso no resultado e falha no teste, nunca é escondida.
5. **Componente não revisado nunca entra em seleção automática.**
6. Trabalhar por fases; parar e pedir aprovação do usuário ao fim de cada fase.

## Idioma

- Interface, relatórios, documentação em `docs/`: **português do Brasil**, SI, notação de engenharia, vírgula decimal.
- Código, identificadores, mensagens de commit, nomes de branch: **inglês**.
- Termos técnicos consagrados mantêm a grafia usual (VRRM, RDS(on), Tj, trr).

## Código

- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, pint, NumPy, SciPy.
- `ruff` para lint e formatação; `mypy --strict` em `core/`, `design/`, `selection/`, `thermal/`, `magnetics/`, `simulation/`.
- O núcleo de domínio não importa `fastapi` (verificado por `import-linter`).
- Novas topologias: plug-in em `backend/src/circuitos/design/plugins/<id>/` implementando `DesignModule`; nada muda no núcleo.
- Citar a referência no código de cada equação: `# Hart, Power Electronics, 1st ed., ch. 3, eq. 3.x` (confirmar com o livro; não chutar número de equação).
- Front-end: React + TypeScript strict + Vite, ESLint, Prettier, uPlot, KaTeX.

## Testes

- Núcleo de cálculo em **TDD**; cobertura ≥ 80 % no núcleo.
- Pastas: `tests/unit`, `tests/golden` (GT-), `tests/analytic_vs_sim` (AS-), `tests/datasheet` (DS-), `tests/property` (PT-).
- Todo *golden test* registra a fonte (livro, edição, exemplo, página) e a tolerância no docstring.
- Testes que dependem do ngspice usam o marcador `@pytest.mark.ngspice`.
- Ao corrigir uma falha, rodar só o teste que falhou; suíte completa uma vez antes de pedir revisão.

## Dados

- Banco inicial em `data/components/<categoria>/<part>.yaml`, revisável em PR.
- Cada PR que adiciona componente informa os datasheets usados (link e revisão).
- PDFs armazenados por SHA-256; nunca versionar PDFs de terceiros no repositório se a licença não permitir (guardar só URL e hash).

## Git

- Sempre criar e trabalhar em uma branch antes de alterar arquivos; nunca implementar diretamente em `main`. Integrar as mudanças por Pull Request após revisão.
- Uma funcionalidade por branch: `feat/<area>-<descricao>`, `fix/...`, `docs/...`.
- Commits pequenos e descritivos, em inglês, no imperativo.
- Atualizar `docs/roadmap.md` no mesmo PR que muda o status de um item.

## Ao fim de cada fase

Entregar: resumo do que foi feito, como executar, resultado dos testes, limitações conhecidas, próximo passo e `docs/validacao/<modulo>.md` para revisão do usuário.
