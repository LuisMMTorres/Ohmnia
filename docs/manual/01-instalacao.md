# 1. Instalação e primeiros passos

## Pacote pronto para Windows (recomendado para alunos e laboratório)

1. Descompacte `Ohmnia-<versão>-windows-x64.zip` em qualquer pasta.
2. Dê dois cliques em `Ohmnia.exe`. O navegador abre em <http://127.0.0.1:8000/>.
3. A janela preta é o servidor: ela mostra o registro e, ao ser fechada, encerra o programa.

O pacote já traz o ngspice e o catálogo de componentes. Não é preciso instalar Python nem
Node.js. Para OCR de datasheets digitalizados, instale também o Tesseract
(`winget install tesseract-ocr.tesseract`).

Para usar outra porta: `Ohmnia.exe --port 8001`. Para não abrir o navegador sozinho:
`Ohmnia.exe --no-browser`.

## A partir do código-fonte (Windows ou Linux)

Requisitos: Python 3.12+ com [uv](https://docs.astral.sh/uv/), Node.js 20+ e ngspice. No Windows,
defina `CIRCUITOS_NGSPICE_EXE` e `CIRCUITOS_NGSPICE_LIB` (detalhes no `README.md`).

```bash
cd frontend && npm ci && npm run build && cd ..
cd backend && uv sync && uv run python -m circuitos
```

Para gerar o pacote do Windows: `powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1`
(resultado em `packaging\dist`).

## Onde ficam os seus dados

Na pasta `.circuitos` do usuário (`C:\Users\<nome>\.circuitos` ou `~/.circuitos`):

| Arquivo | Conteúdo |
|---|---|
| `catalog.db` | catálogo com as suas revisões, projetos salvos, importações de datasheet |
| `datasheets\` | PDFs baixados dos fabricantes ou enviados por você, pelo hash SHA-256 |

Cópia de segurança = copiar essa pasta. Atualizar o programa não apaga nada: o catálogo do
repositório só substitui um componente quando a revisão dele no arquivo YAML aumenta.

## As abas

| Aba | Para quê |
|---|---|
| Componentes | catálogo, busca por parâmetro, revisão e liberação, curvas e modelos SPICE |
| Importar datasheet | criar componente a partir do PDF do fabricante |
| Bancada de dispositivos | curvas características de um dispositivo isolado |
| Projeto | assistente: requisitos → esforços → componentes reais → margens → simulação → relatório |
| Simulador | editor de esquemático livre com todas as análises do ngspice |
