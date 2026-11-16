# Validação: relatórios, exportações, empacotamento e documentação (Fase 9)

Data: 2026-11-15. Status: aguardando a sua aprovação.

Esta fase fecha o fluxo do projeto: o que o assistente calcula vira relatório, lista de materiais,
netlist para placa e arquivo de projeto, e o programa passa a ser distribuído como pacote para
Windows, com manual.

## O que foi feito

| Item da especificação | Onde | Situação |
|---|---|---|
| Relatório completo (4.9): especificação, memória de cálculo com equações, esquemático, BOM, gráficos, conclusões sobre limites | `reports/report.py`, `reports/sections.py`, templates | ✅ HTML e PDF |
| Relatório em PDF | `reports/pdf.py` (PyMuPDF; equações pelo mathtext do Matplotlib) | ✅ sem navegador nem GTK |
| HTML imprimível | CSS de impressão A4 e botão "Imprimir / salvar em PDF" | ✅ |
| Formas de onda no relatório | cálculo sobreposto à simulação no ngspice; Bode | ✅ |
| Limites de operação (2.5 e 4.1-7) | seção com parâmetro crítico por posição, folga de Tj, fator de carga e veredito | ✅ |
| BOM (4.8): esforço × nominal × margem, Tj, dissipador, link do datasheet, agrupamento, custo editável | `reports/bom.py`; aba "Lista de materiais" | ✅ |
| Exportação da BOM em CSV, XLSX e PDF | `/design/{id}/bom.csv|xlsx|pdf` | ✅ |
| Projetos (4.9): salvar, abrir, duplicar, versionar, formato aberto | `projects/store.py`, `api/projects.py`; barra de projeto | ✅ `.circuito.json` |
| Exportação para KiCad | `reports/kicad.py`; projeto e simulador | ✅ netlist `.net` (ver limitações) |
| Instalador local | `packaging/` (PyInstaller, pacote `.zip` com ngspice) | ✅ Windows x64 |
| Manual do usuário | `docs/manual/` (6 capítulos) | ✅ |
| Guia de extensão (topologias, categorias, componentes, bancadas) | `docs/guia-extensao.md` | ✅ |

### Decisões técnicas

- **PDF no servidor com PyMuPDF**, não WeasyPrint: o WeasyPrint precisa das bibliotecas GTK no
  Windows. As equações vão como imagem do mathtext; o que o mathtext não lê é impresso como fonte
  LaTeX (nada some). Alguns comandos do KaTeX são reescritos antes (`\ge` → `\geq`, `\sqrt2` →
  `\sqrt{2}`, `\Big|` → `|`). Na suíte, menos de 5 % das 323 equações dos 22 módulos caem no
  modo fonte; o teste falha se passar disso.
- **Projeto guarda entradas, não resultados.** Ao abrir, tudo é recalculado com o catálogo atual.
  Cada salvamento que muda algo é uma revisão; restaurar cria uma revisão nova. Importar um
  arquivo cujo id já existe gera um projeto novo, nunca sobrescreve.
- **KiCad pela netlist SPICE.** A conectividade do SPICE é a única completa. No projeto, só entram
  as posições da lista de materiais: subcircuitos (`XD1`) viram `D1` pelos nomes dos pinos do
  `.subckt` (`a k`, `c b e`, `d s g`, `a k g`), amperímetros de 0 V unem os nós que separam, e
  fontes, cargas e resistências de modelo ficam de fora, listadas no cabeçalho.
- **Custo** por código de peça; itens "a escolher" têm custo por posição (dois capacitores
  diferentes ainda sem código não compartilham preço).

## Defeitos encontrados e corrigidos durante a fase

- `design/analog.py` gerava `C_o_{calc}` (subscrito duplo) na memória de cálculo dos conversores:
  o KaTeX também não lia. Agora `C_{o,calc}`.
- Nomes de arquivo com acento no cabeçalho HTTP quebravam o download do projeto; agora no padrão
  RFC 6266 (nome ASCII + `filename*=UTF-8''…`).
- Os exportadores de netlist KiCad perdiam os diodos dos módulos (subcircuitos) e separavam nós
  ligados por amperímetros: corrigido e testado com a netlist real do DM-RET1.

## Resultados dos testes

| Teste | O que verifica | Resultado |
|---|---|---|
| `test_design.py` (BOM) | margens, Tj, link do datasheet, custo total, XLSX (cabeçalhos, total, aba de verificações), PDF, agrupamento | ✅ |
| `test_design.py` (relatório) | HTML com formas de onda (ngspice), limites, BOM rica, botão de impressão; **PDF para os 22 módulos** com memória e limites; equações em modo fonte < 5 % | ✅ |
| `test_projects_api.py` | criação com especificação validada e completa, revisão só quando muda, restauração, duplicação, exclusão, exportação/importação, versão de formato, reabrir e projetar | ✅ 6 |
| `test_kicad.py` + API | parênteses balanceados, pinos do diodo, filtro pela BOM, travessão em `D1–D4`, subcircuitos pelo nome dos pinos, amperímetros, aviso de pinagem | ✅ 5 |
| Verificação na tela | salvar projeto, custo, revisão com nota, restaurar, aba de materiais, menu de exportação, PDF de 7 páginas conferido visualmente | ✅ |
| Pacote Windows | executável testado sem o ngspice da máquina (ver "Empacotamento") | ✅ |

## Empacotamento

`packaging/build_windows.ps1` compila a interface, monta a pasta do ngspice (executável, DLL,
modelos de código e as duas DLLs que faltam no pacote da DLL) e gera com o PyInstaller
`packaging/dist/Circuitos/Circuitos.exe` e o `.zip` para distribuir. O `LEIA-ME.txt` e o manual
vão junto.

Construção nesta máquina (Windows 11, 2026-11-15): pacote de 173 MB (323 MB descompactado). Teste
do executável com uma pasta de dados vazia, outra porta e **sem** as variáveis do ngspice desta
máquina (para usar só o que vai no pacote):

| Verificação | Resultado |
|---|---|
| Interface servida em `/` | ✅ 200 |
| Catálogo importado na primeira partida | ✅ todas as categorias |
| Conferência do DM-RET1 no ngspice (DLL do pacote) | ✅ erro de 0,0002 % na tensão média |
| Relatório PDF com simulação | ✅ 308 kB |
| Simulação livre em processo separado (fila de tarefas) | ✅ concluída |

## Limitações conhecidas

- **KiCad**: só a netlist (`.net`); o esquemático `.kicad_sch` não é gerado (exigiria símbolos e
  posicionamento próprios do KiCad). As footprints são sugestões; a pinagem de transistores e
  tiristores precisa ser conferida.
- **PDF**: tabelas longas quebram entre páginas sem repetir o cabeçalho; equações que o mathtext
  não lê saem como LaTeX.
- **Instalador**: pacote `.zip` sem assinatura digital (alguns antivírus pedem liberação); não há
  instalador com atalho no menu Iniciar nem versão para Linux/macOS (no Linux, o código-fonte ou o
  Docker continuam valendo).
- **Fator de carga** nos limites de operação supõe esforços de corrente proporcionais à carga.

## Pendências herdadas (suas)

1. D9 (chave da API da Anthropic). 2. DS-EXT (baixar os PDFs dos fabricantes). 3. AS
`opnl_limitador` no Windows. 4. PDFs da onsemi com bytes novos.
