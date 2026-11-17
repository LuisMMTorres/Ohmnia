# 3. Projeto guiado: do requisito ao relatório

O menu de acesso é **Análise de Projetos**. Use **Abrir…** para carregar um projeto existente
e **Salvar como…** para criar uma cópia independente antes de modificá-lo.

**Editar circuito do projeto** abre uma versão livre do circuito, permitindo adicionar,
retirar e trocar componentes. **Salvar** ou **Salvar como…** guarda essa versão junto com a
revisão do projeto. Ao reabrir, o circuito editado é recuperado. Os cálculos analíticos do
módulo continuam associados aos requisitos originais; simule o circuito livre para avaliá-lo.

**Enviar ao esquemático** e **Enviar à protoboard** transferem o circuito editado, quando houver,
ou preparam o circuito do projeto atual e abrem a vista escolhida no Simulador.

## Fluxo

1. Escolha o **módulo de projeto** (retificadores, fontes, amplificadores, ampops, filtros,
   conversores, inversores, gradadores, comando e proteção…).
2. Informe a especificação e a carga. Os controles deslizantes refazem o projeto a cada mudança:
   use-os para ver até onde a topologia e os componentes aguentam.
3. Escolha o **critério de derating** ("didático" ou "industrial"; critérios de projeto, não
   normas).
4. Leia as abas:
   - **Resultados**: grandezas principais e avisos;
   - **Componentes e margens**: componente escolhido por posição, cada verificação
     (esforço × nominal, fator exigido, margem) e a temperatura de junção; aqui você **trava** um
     componente à mão;
   - **Lista de materiais**: a verificação crítica de cada linha, Tj, link do datasheet e custo
     unitário (opcional);
   - **Formas de onda**: cálculo e, ao clicar em simular, a simulação no ngspice;
   - **Esquemático** e **Memória de cálculo** (cada equação com premissas e referência).

## Projetos

A barra no topo do painel guarda o projeto:

- **Salvar como…** cria o projeto; **Salvar** grava uma nova **revisão** (só quando algo mudou)
  com uma nota opcional;
- **Histórico** lista as revisões; escolher uma restaura aquele conteúdo como revisão nova (nada é
  perdido);
- **Duplicar**, **Abrir…**, **Baixar arquivo** e **Importar arquivo**.

O arquivo `.circuito.json` é aberto (JSON legível) e guarda só as entradas: módulo, especificação,
critério, componentes travados e custos. Os resultados são sempre recalculados ao abrir, então um
projeto antigo reflete o catálogo e as correções atuais.

## Exportar

Menu **Exportar…**:

| Opção | Conteúdo |
|---|---|
| Relatório (PDF) | especificação, esquemático, resultados, formas de onda (cálculo e ngspice), margens, limites de operação, lista de materiais, conferência com a simulação, memória de cálculo, roteiro de prática |
| Relatório (HTML, imprimível) | o mesmo, com as equações em KaTeX; o botão "Imprimir / salvar em PDF" usa o navegador |
| Lista de materiais (XLSX, PDF, CSV) | linhas agrupadas, esforço × nominal, margem, Tj, dissipador, custo, link do datasheet; a planilha tem uma aba com todas as verificações |
| Netlist SPICE | o circuito simulado |
| Netlist KiCad (.net) | os componentes da lista de materiais com as conexões, para o Pcbnew (Arquivo → Importar → Netlist) |

**Sobre a netlist KiCad.** Fontes, cargas e elementos do modelo (resistência de enrolamento,
amperímetros de 0 V) ficam de fora e são listados no cabeçalho. As footprints são sugestões pelo
encapsulamento do catálogo; a ordem dos terminais de transistores e tiristores deve ser
confirmada no datasheet antes do layout.

## Limites de operação

A seção "Limites de operação" do relatório diz, em texto, qual parâmetro está mais perto do
limite em cada posição, a folga de temperatura e, para esforços de corrente, até quantas vezes a
corrente de carga pode crescer antes de esgotar a margem (estimativa que supõe esforços de
corrente proporcionais à carga).
