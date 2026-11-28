# Análise de Projetos: escolher qualquer componente da família

Pedido (2026-11-28): na aba Análise de Projetos, poder escolher qualquer componente da biblioteca daquela família de componentes.

## O que mudou

- A lista de cada posição (aba **Componentes e margens** e painel do **Esquemático**) traz agora **toda a família** do catálogo, não só a subcategoria da posição. Exemplo: onde o projeto pede um diodo de sinal (DM-OSC), aparecem também os retificadores, rápidos, Schottky e Zener (99 diodos em vez de 1).
- As peças vêm agrupadas, nesta ordem:
  1. **Recomendados**: liberados e dentro das margens, na ordem da escolha automática.
  2. **Atendem às especificações** (inclui peças ainda não revisadas, marcadas "não revisado").
  3. **Atendem, com margem menor que a do projeto** (passam do esforço, mas não do fator da política didática/industrial).
  4. **Não atendem às especificações**, com o motivo (ex.: "não suporta o esforço calculado: IC") ou "fora dos critérios de escolha deste projeto" (critério próprio do módulo, como tensão de alimentação do ampop ou Darlington/não Darlington).
  5. **Sem dados no datasheet para conferir** (falta a grandeza exigida, ex.: VRRM).
  6. **Outro tipo da família**: aparecem, mas ficam desabilitados, porque o circuito desenhado não os aceita (PNP numa posição NPN, canal P no lugar de canal N, TRIAC no lugar de SCR, diodo comum no lugar de Zener).
- Ao travar uma peça que não atende, a posição mostra um selo (não atende / margem menor / sem dados), a tabela de margens indica a violação e o resultado traz o aviso. Peça travada sem a grandeza exigida no datasheet gera o aviso "essas margens não foram conferidas".
- A regra 5 continua: a escolha **automática** só usa peças liberadas; as outras só entram se você travar à mão (com o aviso "não revisado").

## Onde fica no código

- `backend/src/circuitos/selection/select.py`: `fits_position` (quais subtipos se trocam; só a família `diode` é intercambiável, exceto posição Zener) e `assess` (mesmas margens do `rank`).
- `backend/src/circuitos/api/design.py`: `_options` monta a lista da família com `fit`, `reason`, `recommended`.
- `backend/src/circuitos/design/engine.py`: a trava usa `fits_position` (antes aceitava qualquer subtipo, inclusive polaridade errada); posição travada continua com a lista de recomendados; aviso `sem_dados_margem`.
- `frontend/src/pages/design/PartSelect.tsx` e `partOptions.ts`: a lista agrupada, usada nas duas telas.

## Testes

- `tests/unit/design/test_selection.py`: `fits_position` e `assess` (atende, margem menor, não atende, sem dados, fora dos critérios, incompatível).
- `tests/unit/api/test_design.py`: lista da família inteira (DM-OSC D1 com retificadores; DM-PA Q1 com PNP desabilitados), ordem dos grupos, trava de um retificador na posição de diodo de sinal aceita e de um PNP na posição NPN recusada.
- `frontend/src/pages/design/partOptions.test.ts`: agrupamento e texto das opções.

Capturas: `capturas/liberar-familia/` na pasta do projeto (DM-PA com o 2N3904 travado em Q1).

## Limitações

- Resistores, capacitores e indutores do projeto continuam como valores calculados (editáveis no esquemático); não são escolhidos do catálogo.
- "Fora dos critérios de escolha deste projeto" não detalha qual critério do módulo falhou.
- Famílias diferentes não se misturam (ex.: comparador numa posição de ampop).
