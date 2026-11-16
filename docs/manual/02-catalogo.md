# 2. Catálogo, revisão e importação de datasheets

## Buscar componentes

Na aba **Componentes**, filtre por categoria, texto (part number, fabricante, família) e situação
de revisão. Os filtros por parâmetro usam o valor **garantido** do datasheet:

- `VRRM>=600 V` compara o mínimo ou, para limites absolutos, o próprio limite máximo;
- `trr<=75 ns` compara o máximo (ou o típico, quando é o único publicado).

Separe vários filtros por `;`.

## Revisar e liberar

Clique num componente para abrir a revisão: a tabela de parâmetros à esquerda e o PDF à direita.
Ao clicar num parâmetro, a página citada abre e, quando a importação registrou a posição, a linha
de origem aparece destacada.

1. Compare valor, unidade e condições de ensaio com o datasheet.
2. Marque **Confere** (ou **Não confere**, que devolve o valor para "a verificar").
3. Quando todos os obrigatórios estiverem conferidos, informe seu nome e clique em
   **Liberar para seleção automática**.

Só componentes liberados entram na escolha automática do assistente de projeto. Você ainda pode
travar à mão um componente não liberado; ele aparece no projeto marcado "NÃO REVISADO".

### Revisar uma categoria inteira

O botão **Revisar categoria** fica na busca (escolha antes a categoria no filtro) e no topo da tela
de cada componente. Ele revisa de uma vez todos os componentes pendentes daquela categoria:

1. Uma prévia lista cada componente, quantos valores serão marcados como conferidos e se ele
   ficará liberado ou com pendência. Nada é gravado nessa etapa.
2. Marque "Conferi os valores destes componentes com os datasheets", informe seu nome e confirme.

Regras:

- Só são marcados os parâmetros e atributos que citam a página do documento. Os que não citam
  ficam como estavam e aparecem como "sem página".
- Um componente só é liberado se não sobrar pendência, como um obrigatório ausente ou sem página.
  Os outros ficam "em revisão", com as pendências listadas.
- Componentes já liberados ou rejeitados não mudam.
- A liberação registra "seu nome (revisão da categoria)", para distinguir da revisão item a item.

## Importar um datasheet em PDF

Aba **Importar datasheet** → **Escolher PDF…**

1. O texto é lido (com OCR nas páginas sem texto, se o Tesseract estiver instalado).
2. O sistema sugere a categoria e propõe valores. Cada linha mostra a origem (regras, modelo de
   linguagem ou manual), a confiança e notas de cada inferência ("sem cabeçalho Mín./Típ./Máx.:
   valor único tomado como máximo, confira").
3. Clique numa linha para ver o trecho destacado no PDF. Corrija valores, unidade, desmarque o que
   não serve e use **+ valor manual** para o que faltou.
4. Preencha fabricante, part number e encapsulamento; **Importar e abrir a revisão**.

O componente nasce **em revisão**, com os valores **extraídos**. A revisão (seção anterior) é que
libera.

**Modelo de linguagem (opcional).** Com o pacote `anthropic` instalado e uma chave da API, a caixa
"Usar modelo de linguagem" envia o PDF à API da Anthropic. Toda proposta precisa citar página e
trecho literal; o sistema confere o trecho e os números no texto do PDF e descarta o que não
confere (lista "propostas descartadas", com o motivo).

## Curvas digitalizadas

Na revisão, aba **Curvas**:

1. **Calibrar eixos**: clique em duas marcas do eixo X e duas do eixo Y e digite os valores. Escolha
   escala linear ou logarítmica para cada eixo.
2. **Área do gráfico**: clique em dois cantos opostos.
3. Pegue a curva:
   - **Traços vetoriais**: a maioria dos datasheets desenha os gráficos como vetores; escolha o
     traço pela cor. Os pontos são exatos.
   - **Seguir cor**: para páginas digitalizadas; clique sobre a curva.
   - **Cliques**: marque pontos à mão (precisão de um pixel de tela).
4. Informe grandezas, unidades e condições (ex.: `Tj = 25 °C; VCE = 5 V`) e salve.

## Modelos SPICE

Aba **Modelos SPICE**:

- **Modelo do fabricante**: cole ou abra o `.lib`/`.mod`. Cada `.model`/`.subckt` é carregado no
  ngspice antes de ser guardado ("roda no ngspice" ou o registro do erro).
- **Ajustar ao datasheet**: diodo (curva IF×VF), TBJ (hFE×IC e, se houver, VBE×IC) e MOSFET nível 1
  (curva de transferência, ou VGS(th) e gfs). O erro é medido simulando o modelo final no ngspice
  nos pontos da curva; o relatório mostra a origem de cada parâmetro e as premissas.
