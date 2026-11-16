# Ohmnia

Sistema de projeto de circuitos eletrônicos.

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
    O pacote da DLL da versão 47 não traz `sndfile.dll` e `samplerate.dll`: copie-as da pasta
    `bin` do pacote do executável para a pasta da DLL.
- Tesseract com os idiomas `eng` e `por` (opcional, para OCR de datasheets digitalizados).
  Windows: `winget install tesseract-ocr.tesseract`; Linux: `sudo apt install tesseract-ocr`.
  Se a pasta `tessdata` não estiver no lugar padrão, defina `CIRCUITOS_TESSDATA`.
- Extração de datasheets com modelo de linguagem (opcional): `uv sync --extra llm` e uma
  credencial da API da Anthropic (`ANTHROPIC_API_KEY` ou `ant auth login`).

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
| `CIRCUITOS_DATA_DIR` | Pasta de dados local (padrão `~/.circuitos`): banco `catalog.db` e datasheets baixados |
| `CIRCUITOS_DB_URL` | URL SQLAlchemy do banco de componentes (padrão `sqlite:///<DATA_DIR>/catalog.db`) |
| `CIRCUITOS_CATALOG_DIR` | Pasta dos YAML importados na partida (padrão `data/components`) |
| `CIRCUITOS_TESSDATA` | Pasta dos idiomas do Tesseract para OCR (padrão: procurada nos locais usuais) |

## Banco de componentes

Os componentes ficam em `data/components/<categoria>/*.yaml`, transcritos dos datasheets
oficiais com fabricante, documento, revisão e página de cada valor. Na partida, o servidor
importa esses arquivos para o banco local. Os PDFs não são versionados: o sistema guarda a URL
e o SHA-256 e baixa o arquivo do site do fabricante na primeira vez que a página é aberta.

Fluxo de revisão, na tela **Componentes**:

1. Abra um componente. Clicar num parâmetro mostra a página citada do datasheet ao lado.
2. Compare valor e condições de teste e marque **Confere** ou **Não confere**.
3. Com os parâmetros obrigatórios conferidos, informe seu nome e clique em
   **Liberar para seleção automática**. Só componentes liberados entram na seleção.
4. **Baixar YAML revisado** exporta o arquivo com as marcações, para guardar no repositório.

Testes que conferem cada valor na página citada (precisam de acesso aos sites dos fabricantes):
`cd backend && uv run pytest -m datasheet`.
