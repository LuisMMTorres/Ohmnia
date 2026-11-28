# Protoboard: selecionar, mover e apagar fios

Pedido (2026-11-28): clicar nos fios da protoboard para selecioná-los, movê-los, reposicioná-los e apagá-los.

## O que mudou

- **Selecionar**: um clique no fio (jumper) o destaca em laranja. A área de clique é mais larga que o desenho do fio, para não ser preciso acertar a linha fina. O painel da direita mostra as pontas (ex.: `2:j4 → 2:bn4`), a cor e o botão **Apagar fio (Delete)**.
- **Mover uma ponta**: com o fio selecionado aparecem duas bolinhas nas pontas; arraste uma delas para outro furo.
- **Arrastar o fio inteiro**: arraste o próprio fio; as duas pontas andam juntas, furo a furo, e podem ir para os barramentos ou para a outra placa.
- **Apagar**: tecla Delete (ou Backspace) ou o botão do painel.
- **Trocar a cor** do fio selecionado no painel.
- **Cabos dos instrumentos** (fonte simétrica, gerador, fonte de bancada): também são selecionáveis; arraste o cabo ou a garra para outro furo, ou use **Desconectar cabo (Delete)**.
- Enquanto arrasta, aparece a prévia tracejada; em vermelho quando o furo de destino já está ocupado (por perna, cabo ou outro fio) ou fora da placa. Soltar ali não muda nada.

## Ligações e simulação

O fio novo entra na montagem da protoboard (`breadboard.wires` / pernas do instrumento). A conferência com o esquemático roda de novo em seguida, e a bancada interativa em execução pede para reiniciar ("Circuito ou fiação alterados"), passando a usar a nova ligação.

## Testes

- `frontend/src/breadboard/wireEdit.test.ts` (6 testes): mover ponta, recusar furo ocupado, arrastar o fio inteiro (inclusive para a placa 2), recusar destino ocupado ou fora da placa, mover e desconectar cabo de instrumento, apagar só o fio escolhido.
- Conferido no navegador (Playwright) com o exemplo "Filtro RC passa-baixas": selecionar, mover ponta (`2:bn4 → 2:bn6`), arrastar o fio (`2:j4 → 2:j14`), Delete, mover o cabo do gerador (`2:j7 → 2:j11`), sem erros no console.

Capturas: `capturas/protoboard-editar-fios/` na pasta do projeto.

## Limitações

- Seleciona um fio por vez (sem seleção múltipla).
- Ao arrastar o fio inteiro ele mantém o formato; para mudar o formato, mova as pontas.
