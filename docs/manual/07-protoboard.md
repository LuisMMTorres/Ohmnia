# Protoboard: o mesmo circuito montado como na bancada

Todo circuito tem duas vistas: o **esquemático 2D** (símbolos) e a **protoboard** (as peças reais,
pelo encapsulamento, montadas na bancada com duas placas de 830 pontos). As duas são o mesmo circuito: a montagem
fica guardada dentro do arquivo do circuito e é conferida contra o esquemático a cada mudança.

## A placa

A bancada tem duas placas de 830 pontos e barras verticais de alimentação independentes.
O zoom inicial é **100%**. A segunda placa usa nomes como `2:a12`; as barras verticais usam
`vp1`…`vp40` e `vn1`…`vn40`. Para unir as placas ou alimentá-las, acrescente fios explícitos.

O botão **Colocar** insere o dispositivo completo. Instrumentos externos entram com terminais
desconectados; selecione cada terminal no painel para ligá-lo a um furo. O painel também permite
ajustar as pernas das peças já colocadas. A conferência aponta ligações faltantes e conflitos.

Adicione o osciloscópio em **Adicionar instrumento**. Uma miniatura aparece junto às fontes.
Clique no borne **+** do canal e depois no furo de medição; repita no borne **−** para escolher
a referência. Cabos coloridos mostram as conexões. As duas ponteiras precisam estar ligadas
para gerar a medição do canal. O painel do instrumento mostra os furos e permite desconectar.
Simule após mudar as ligações; a leitura acompanha os condutores e jumpers da montagem.


- 63 linhas numeradas. Em cada linha, os furos **a a e** estão ligados entre si, e os furos **f a
  j** também; a canaleta do meio separa as duas metades (é ali que o circuito integrado encaixa).
- Dois pares de barramentos, em cima e embaixo, com a polaridade impressa (+ vermelho, − azul).
  Cada barramento corre a placa inteira; marque "barramentos cortados ao meio" se a sua placa for
  das que têm o barramento interrompido no centro.
- Passe o mouse sobre um furo: os furos ligados a ele acendem em verde.

## No simulador

1. Desenhe o circuito no **Esquemático 2D** (ou abra um exemplo).
2. Clique em **Protoboard**.
3. **Montar automaticamente** coloca as peças e os fios e já confere. Ou monte à mão: na lista de
   peças, clique em **Colocar** para inserir a peça inteira. Depois arraste-a ou ajuste os furos
   pelo painel de terminais. Fontes, instrumentos e placas de controle ficam fora da protoboard,
   com seus terminais inicialmente desconectados.
4. **Fio (W)**: clique no primeiro furo e no segundo. A cor é só para organizar.
5. Arraste uma peça para movê-la; arraste a perna de um resistor ou diodo para dobrá-la.
   Del retira a peça ou o fio selecionado.

A **Conferência com o esquemático** roda sozinha e aponta:

| Aviso | O que significa |
|---|---|
| Falta ligação | pernas que o esquemático liga e a protoboard não |
| Ligação a mais | nós diferentes ligados na protoboard (curto) |
| Pernas trocadas | duas pernas da mesma peça uma no lugar da outra (ex.: coletor e emissor) |
| Não montado | peça do esquemático que não está na placa |
| Furo em conflito | duas pernas ou fios no mesmo furo |

Clique num aviso para ver os furos marcados em vermelho na placa. **Roteiro de montagem** lista
os passos na ordem da bancada (integrados, transistores, demais peças, fios, instrumentos), com
o código de cores de cada resistor; serve de roteiro de prática.

## Pinagem: de onde vem cada perna

Ao selecionar um componente, aparece o **encapsulamento real** ao lado do símbolo, com cada perna
rotulada e a origem da pinagem:

- **Pinagem do datasheet**: peça do catálogo com a pinagem transcrita do datasheet (documento,
  página e local). Enquanto você não revisar, aparece como "extraído".
- **Genérico**: peça genérica do simulador. As pernas estão rotuladas pela função (C, B, E...), mas
  **não** é a pinagem de uma peça real: escolha a peça do catálogo ou confira o datasheet antes de
  montar. Transistores com o mesmo nome têm pinagens diferentes entre fabricantes (o P2N2222A da
  onsemi é C-B-E; outros 2N2222A são E-B-C).
- **Sem pinagem**: peça do catálogo cuja pinagem ainda não foi transcrita. Ela aparece na placa
  sem rótulos e fica **fora da conferência**: o sistema não supõe pinagem.

Os circuitos integrados têm pinos de alimentação (V+, V−) que o símbolo do esquemático não mostra
(a tensão está nos parâmetros do amp-op). Na protoboard eles vão a uma **fonte simétrica de
bancada** implícita (ALIM), que a montagem automática coloca e a conferência cobra.

## No projeto guiado

A aba **Protoboard** do projeto mostra o circuito projetado montado com as peças escolhidas,
conferido e com o roteiro. Os amperímetros da simulação viram fio, o macromodelo do amp-op vira o
integrado com a alimentação do projeto. **Abrir no simulador** leva o circuito e a montagem para o
simulador livre.

Módulos cuja simulação usa modelos sem peça física (regulador linear comportamental, chaves
ideais do amplificador classe D e do acionamento) avisam isso em vez de inventar uma montagem;
monte-os no simulador livre com as peças reais.
