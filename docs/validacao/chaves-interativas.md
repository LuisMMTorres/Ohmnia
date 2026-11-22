# Chaves e botões acionados com um clique

## O que mudou

- **Clique no botão para apertar ou soltar.** No esquemático, a parte de cima do símbolo
  (o atuador) dos botões NA, NF, táctil de 4 terminais e do botão/chave manual responde ao
  clique: apertado, a barra de contato encosta (NA) ou se afasta (NF) e o atuador fica laranja.
  Na protoboard, o clique é na tampa da chave táctil. O painel de propriedades mostra o estado e
  um botão **Apertar/Soltar**.
- **A simulação roda de novo sozinha** a cada clique (se o circuito já tem uma análise), sem
  sair da tela do circuito. LEDs, lâmpadas e motores passam a refletir a nova posição. Uma
  simulação ainda em andamento é cancelada quando chega um novo clique.
- **LED aceso também na protoboard**, com o mesmo brilho calculado do esquemático.
- **Estado padrão = solto (`0`).** Antes, o padrão do parâmetro *Estado* era o perfil
  `0 0 0.001 0 0.00101 1`, que **aperta o botão em 1 ms**. Numa transitória de 100 ms o botão
  ficava fechado em 99 % do tempo e o LED aparecia aceso, que era o defeito relatado. O perfil
  no tempo continua aceito (ex.: para ver o transitório do acionamento); o clique o troca por
  um valor constante (`1` apertado, `0` solto).

O estado é o mesmo parâmetro `state` que a netlist já usava (fonte comportamental que comanda
uma chave `S` do ngspice). O modelo elétrico não mudou.

## Conferência

| Caso (V1 = 10 V, R2 = 330 Ω, R1 = 1 kΩ, R3 = 10 kΩ, LED genérico V_F = 2 V, NPN genérico) | I(LED1) |
|---|---|
| Padrão antigo (aperta em 1 ms), média da 2ª metade de 100 ms | 24,1 mA (LED aceso: o defeito) |
| Botão solto (padrão novo ou clique) | < 1 µA em toda a simulação |
| Botão apertado (clique) | > 15 mA em toda a simulação |

Teste: `backend/tests/unit/cosim/test_devices_ngspice.py::test_button_switches_led_through_transistor`
(ngspice). Front: `frontend/src/schematic/switches.test.ts`.

Capturas: `capturas-chaves-interativas/1-solto.png`, `2-apertado.png` (esquemático) e
`3-protoboard.png`.

## Limitações

- O clique fixa o botão na posição (como segurar o dedo nele); não há "aperta e solta sozinho".
  Para um pulso, use o perfil no tempo no parâmetro *Estado*.
- A chave controlada por tensão (`switch`) não é manual e não responde ao clique.
- Na protoboard, o botão/chave manual de painel (22 mm, desenhado fora da placa) ainda não
  responde ao clique; use o esquemático ou o painel de propriedades.
- Circuitos salvos com o padrão antigo e sem valor em *Estado* passam a começar soltos.
