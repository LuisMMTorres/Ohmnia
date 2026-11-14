# Sistema de Projeto de Circuitos Eletrônicos

Projeto, dimensionamento, seleção de componentes reais e simulação de circuitos de Eletrônica
Analógica e Eletrônica de Potência. Aplicação local: um servidor Python roda no seu computador e
a interface abre no navegador.

Planejamento: [docs/escopo.md](docs/escopo.md), [docs/arquitetura.md](docs/arquitetura.md),
[docs/modelo-de-dados.md](docs/modelo-de-dados.md). Andamento: [docs/roadmap.md](docs/roadmap.md).

## Requisitos

- Python 3.12 ou superior e [uv](https://docs.astral.sh/uv/)
- Node.js 20 ou superior (apenas para compilar a interface)
- ngspice
  - **Linux (Debian/Ubuntu):** `sudo apt install ngspice libngspice0`
  - **Windows:** baixe o pacote do ngspice para Windows em <https://ngspice.sourceforge.io/download.html>.
    Use a versão com a DLL (`ngspice.dll`) e defina a variável de ambiente
    `CIRCUITOS_NGSPICE_LIB` com o caminho completo da DLL. Se preferir o executável,
    defina `CIRCUITOS_NGSPICE_EXE` com o caminho de `ngspice.exe`.

## Como executar

```bash
cd frontend && npm ci && npm run build && cd ..
cd backend && uv sync && uv run python -m circuitos
```

O navegador abre em <http://127.0.0.1:8000/>. Para desenvolver a interface com recarga
automática, rode `npm run dev` em `frontend/` (porta 5173, com proxy para o servidor).

Com Docker: `docker compose up --build` e acesse <http://localhost:8000/>.

## Verificação de qualidade

```bash
scripts/check.sh            # lint, tipos, contratos de importação, testes e build
scripts/check.sh backend    # só Python
scripts/check.sh frontend   # só interface
```

## Variáveis de ambiente

| Variável | Uso |
|---|---|
| `CIRCUITOS_NGSPICE_LIB` | Caminho da biblioteca compartilhada do ngspice |
| `CIRCUITOS_NGSPICE_EXE` | Caminho do executável do ngspice (modo batch) |
| `CIRCUITOS_SIM_WORKERS` | Simulações simultâneas (padrão 2) |
| `CIRCUITOS_FRONTEND_DIST` | Pasta da interface compilada (padrão `frontend/dist`) |
