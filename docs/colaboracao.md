# Como trabalhar em dupla no Ohmnia

O código vive em <https://github.com/LuisMMTorres/Ohmnia>. A `main` é a versão de referência:
ninguém edita direto nela. Cada mudança vai numa branch, vira um pull request (PR) e o outro
revisa e mescla.

## 1. Preparar a máquina (uma vez)

Instale no Windows:

- [Git for Windows](https://git-scm.com/download/win)
- Python 3.12 ou superior e [uv](https://docs.astral.sh/uv/) (`winget install astral-sh.uv`)
- Node.js 20 ou superior (`winget install OpenJS.NodeJS.LTS`)
- ngspice 47 (veja "Requisitos" no [README](../README.md); defina `CIRCUITOS_NGSPICE_LIB`)

Configure seu nome no Git (aparece nos commits):

```powershell
git config --global user.name "Seu Nome"
git config --global user.email "seu-email@exemplo.com"
```

Quem não é dono do repositório precisa ser adicionado como colaborador:
**Settings → Collaborators → Add people** no GitHub (feito pelo dono).

## 2. Obter o código

Máquina nova:

```powershell
cd D:\projetos
git clone https://github.com/LuisMMTorres/Ohmnia.git
cd Ohmnia
```

Pasta que já existia antes do GitHub (ex.: `sistema-circuitos` do Lauro): ligue-a ao GitHub e
alinhe a `main` local com a do GitHub. Antes, rode `git status`: se houver arquivos modificados
que você quer guardar, faça um commit numa branch primeiro.

```powershell
cd D:\Downloads_net\Claude\sistema-circuitos
git remote add origin https://github.com/LuisMMTorres/Ohmnia.git   # se disser que já existe, siga
git fetch origin
git checkout main
git reset --hard origin/main
git branch -u origin/main
```

## 3. Rodar o sistema

```powershell
cd frontend; npm ci; npm run build; cd ..
cd backend; uv sync; uv run python -m circuitos
```

O navegador abre em <http://127.0.0.1:8000/>. Depois de puxar mudanças que mexem na interface
(`frontend/`) ou nas dependências (`pyproject.toml`, `package.json`), rode de novo
`npm ci; npm run build` e `uv sync`.

## 4. O ciclo de cada mudança

```powershell
git checkout main
git pull                                  # traz o que o outro mesclou
git checkout -b fix/nome-curto            # uma branch por assunto
# ... edite, rode, teste ...
cd backend; uv run pytest tests/unit; cd ..
git add -A
git commit -m "Explica o que mudou"
git push -u origin fix/nome-curto
```

O GitHub mostra o botão **Compare & pull request**. Abra o PR, descreva o que mudou e como
testou, e peça a revisão do outro. Quem revisa usa **Files changed** para comentar e
**Merge pull request** quando estiver bom. Depois do merge, os dois fazem `git checkout main` e
`git pull`.

Prefixos de branch: `feat/` para algo novo, `fix/` para correção, `docs/` para documentação.

## 5. Regras simples para não pisar no pé do outro

- Sempre `git pull` na `main` antes de criar uma branch.
- PRs pequenos, um assunto por vez; avise o outro quando for mexer num arquivo grande
  (ex.: `schematic/netlist.py`, telas em `frontend/src/pages/`).
- Conflito no PR: `git checkout sua-branch`, `git pull origin main`, resolva os arquivos
  marcados, `git add`, `git commit`, `git push`.
- Não versionar dados locais: o banco e os datasheets ficam em `~/.circuitos`, fora do repositório.
  Componentes revisados vão para o repositório como YAML em `data/components/`.
- Antes de pedir revisão de algo numérico, rode os testes da área
  (`uv run pytest tests/analytic_vs_sim -k <assunto>`).

## 6. Usando o Claude ou o Codex

Os dois funcionam pelo mesmo fluxo: peça a mudança, ele cria a branch e abre o PR, e o outro
revisa. O arquivo `CLAUDE.md` na raiz descreve as convenções do projeto para os assistentes.
