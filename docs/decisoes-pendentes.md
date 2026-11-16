# Decisões pendentes do usuário (Fase 0)

Cada item traz uma recomendação. Responder "de acordo" com a recomendação já basta para seguir.

## D1. Onde fica o código — **DECIDIDO (2026-11-14): pasta do projeto** (`/mnt/project-files/sistema-circuitos`), sem GitHub. Git local para histórico; CI substituída por script `scripts/check.sh` (lint, tipos, testes) rodado antes de cada entrega.

- **Recomendado:** repositório no GitHub (criado pelo usuário; eu o conecto ao projeto). Viabiliza a CI exigida na Fase 1 (Linux e Windows) e o fluxo de PR por funcionalidade.
- Alternativas: pasta compartilhada do projeto (sem CI) ou uma pasta no computador do usuário.

## D2. Forma de uso — **DECIDIDO (2026-11-14): aplicação local que abre no navegador.**

- **Recomendado:** aplicação local que abre no navegador (back-end Python + interface web), com instalador na Fase 9. Mesma base serve para laboratório multiusuário.
- Alternativa: aplicativo desktop (Tauri/Electron) desde o início. Custo maior de empacotamento enquanto a interface muda.

## D3. Uso individual ou de turma — **DECIDIDO (2026-11-14): uso individual.** Apenas SQLite; sem contas de usuário nem servidor multiusuário. O acesso a dados fica atrás do SQLAlchemy, então o PostgreSQL continua possível no futuro sem reescrita.

- **Recomendado:** SQLite (individual) como padrão, PostgreSQL suportado desde a Fase 1 para uma futura instalação no laboratório.
- Pergunta: haverá alunos usando simultaneamente num servidor do IFMA? Se sim, contas de usuário e permissões (professor revisa componentes, aluno só usa) entram no escopo da Fase 2.

## D4. Derating padrão — **DECIDIDO (2026-11-14):** o usuário não segue norma nem manual de empresa. Os perfis abaixo viram os padrões do sistema, rotulados na interface e no relatório como "critério de projeto, não normativo", e são editáveis por projeto.

Proposta de três perfis, editáveis por projeto. **Valores a confirmar pelo usuário** (são critérios de prática de projeto, não de datasheet):

| Categoria / grandeza | Didático | Industrial |
|---|---|---|
| Diodo/tiristor: VRRM ÷ tensão reversa máxima aplicada | ≥ 1,5 | ≥ 2,0 |
| Diodo/tiristor: IF(AV) ÷ corrente média | ≥ 1,2 | ≥ 1,5 |
| Semicondutor: Tj,máx − Tj calculada | ≥ 15 K | ≥ 25 K |
| MOSFET/IGBT: VDS(VCE) ÷ tensão máxima aplicada | ≥ 1,3 | ≥ 1,5 |
| Capacitor eletrolítico: tensão nominal ÷ tensão máxima | ≥ 1,2 | ≥ 1,5 |
| Capacitor eletrolítico: ripple nominal ÷ ripple eficaz (corrigido por temperatura e frequência) | ≥ 1,0 | ≥ 1,3 |
| Resistor: potência nominal ÷ potência dissipada | ≥ 1,5 | ≥ 2,0 |
| Indutor: Isat ÷ corrente de pico | ≥ 1,2 | ≥ 1,3 |

Pergunta: segue alguma referência formal de derating (norma ou manual de empresa) que deva ser o perfil "industrial"?

## D5. Símbolos do esquemático

- **Recomendado:** IEC 60617 como padrão (alinhado à ABNT), com ANSI/IEEE 315 selecionável, já que parte da bibliografia (Boylestad, Hart) usa símbolos ANSI.

## D6. Casos de referência (golden tests) — **EM CONFERÊNCIA (2026-11-14)**

- O usuário pediu que eu sugerisse os exemplos. Sete casos propostos em [validacao/casos-referencia-propostos.md](validacao/casos-referencia-propostos.md), já como teste `GT-RET-P1..P7`. Aguardam conferência dos números ou a indicação do exemplo equivalente do livro.
- Fase 4: mais oito casos (P8–P15, polarização, pequenos sinais, ceifadores, grampeador e multiplicador), teste `GT-P8..P15`, mesma situação.

## D7. Revisão dos componentes do banco inicial — **ADOTADA A RECOMENDAÇÃO (2026-11-14), sem objeção do usuário:** eu cadastro como `extraido` com página; o usuário libera (`revisado`) pela tela de revisão, por amostragem.

- Eu baixo os datasheets oficiais e preencho os YAML com página de cada valor, status `extraido`.
- **Pergunta:** quem libera (`revisado`)? Recomendação: o usuário revisa por amostragem um lote por categoria na Fase 2, e o restante fica liberado após conferência dupla automática (dois datasheets/fabricantes concordando, quando houver segunda fonte).

## D8. Catálogos de dissipadores e núcleos — **DECIDIDA (2026-11-14)**

- Fabricantes indicados pelo usuário: HS Dissipadores, Rei dos Dissipadores e Eletrogate.
- HS Dissipadores: catálogo 2026-27 (rev. S) transcrito, 137 perfis (`data/components/heatsink/hs-dissipadores-perfis.yaml`). A loja Rei do Dissipador (reidodissipador.com.br) é do mesmo fabricante e vende os mesmos perfis HS.
- Eletrogate: só tem um dissipador adesivo para Raspberry Pi, sem resistência térmica publicada; não entra no catálogo.
- Núcleos magnéticos: nenhum dos três vende; fica para a Fase 6 (conversores), com nova consulta.
- DIAC: adiado a pedido do usuário.

## D9. Extração de datasheets com LLM (Fase 8)

- Opcional, por chave de API da Anthropic configurada localmente. Confirmar se o IFMA tem como prover a chave ou se o fluxo manual (sem LLM) é suficiente.
- Implementado na Fase 8 como opcional (`uv sync --extra llm` + credencial). O PDF só é enviado quando a caixa é marcada na importação. Toda proposta do modelo precisa citar página e trecho; o sistema confere o trecho e os números no texto do PDF e descarta o que não confere. Sem chave, regras + digitação manual cobrem o fluxo inteiro. **Decisão ainda sua:** haverá chave?

## D10. Licença do software

- **Recomendado:** licença aberta (MIT ou GPL-3.0), compatível com ngspice e adequada para uso por outras instituições. Confirmar preferência ou se o projeto será fechado.

## D11. Vista de protoboard (pedido do usuário em 2026-11-15, após a Fase 9)

Cada circuito deve poder ser projetado em duas vistas: o esquemático 2D (simbologia) e a montagem
como numa protoboard (componente real, pelo encapsulamento). Decidido pelo usuário:

- **Onde:** no simulador livre (montagem manual) e no assistente de projeto (montagem gerada do
  circuito projetado, também usada no roteiro de prática).
- **Vínculo:** as duas vistas são o mesmo circuito. O que for ligado na protoboard é comparado com
  o esquemático; o sistema aponta ligação faltando, sobrando ou trocada.
- **Encapsulamentos:** desenhados pelo sistema em SVG a partir das dimensões (DO-41, TO-92, TO-220,
  DIP-8, resistor com faixas de cor, eletrolítico…). A **pinagem de cada peça vem do datasheet, com
  fonte**, como os demais parâmetros (regra 1): sem pinagem conferida, a peça aparece na
  protoboard com aviso e não entra na conferência automática.
- Planejado como Fase 10 (ver roadmap).

## D12. Instrumentação industrial, microcontroladores e CLP (pedido do usuário em 2026-11-15) **DECIDIDA (2026-11-16)**

O usuário quer, além de simular e projetar circuitos de eletrônica, simular circuitos de
eletrônica junto com circuitos de instrumentação e CLP. Os 150 datasheets de instrumentação e CLP
que ele listou já estão na fila de importação (`data/datasheet-queue.yaml`, grupos 26 a 36:
RTD e termopar, CLP e IHM, sensores de proximidade, fotoelétricos, força e carga, nível,
pressão, vazão, encoders, atuadores e válvulas, transmissores e condicionadores), marcados
"ainda sem esquema de categoria", porque o catálogo não tem como representá-los.

A decidir com o usuário antes de planejar a fase:

- **O que é "simular CLP":** lógica ladder ou IEC 61131-3 (ST, FBD) executada em ciclo de
  varredura e acoplada ao circuito elétrico (entradas digitais e analógicas lidas do circuito,
  saídas acionando relé, transistor ou contator), ou apenas o comportamento elétrico das entradas
  e saídas do CLP (níveis, impedância, 4 a 20 mA, 0 a 10 V).
- **Modelos de sensores e transmissores:** curva de Pt100 e termopar por norma (IEC 60751,
  IEC 60584), sensor como fonte comandada no ngspice, laço de 4 a 20 mA com carga e tensão de
  alimentação; sensores de catálogo entram só com valores do datasheet (regra 1).
- **Esquema de categoria** para sensor, transmissor, atuador e CLP, com os parâmetros que a
  seleção e a simulação precisam.
- **Ordem:** proposta é tratar depois da Fase 10 (protoboard), como Fase 11.

**Decisão do usuário (2026-11-16).** A integração entre microcontroladores, eletrônica e CLP é
essencial para o sistema. Escolhas:

- **ESP32 e Arduino:** programa no estilo Arduino (`setup()`/`loop()`, `analogRead`,
  `digitalWrite`, `analogWrite` em PWM, `delay`, `millis`, `Serial`) interpretado pelo sistema e
  co-simulado com o ngspice: o ADC lê tensões do circuito e os pinos acionam o circuito. Não roda
  o firmware compilado.
- **CLP:** ladder e texto estruturado (IEC 61131-3) em ciclo de varredura, com entradas digitais
  24 V, analógicas 4 a 20 mA e 0 a 10 V e saídas a relé ou transistor ligadas ao circuito.
- **Ordem:** terminar a Fase 10 (protoboard) e fazer a integração como Fase 11.
- **Projetos de exemplo**, com sensores do catálogo (importados com fonte, regra 1):
  1. medidor de energia com ESP32 (ZMPT101B para tensão, SCT-013 ou ACS712 para corrente,
     condicionamento com amp-op, tensão e corrente RMS, potência e fator de potência);
  2. controle PWM com Arduino (sensor lido pelo Arduino, carga acionada por MOSFET ou driver em
     malha fechada);
  3. laço de 4 a 20 mA no CLP (Pt100 e transmissor na entrada analógica, ladder com histerese
     acionando relé ou contator);
  4. ESP32 e CLP integrados (o ESP32 mede e condiciona o sensor e entrega 0 a 10 V ou 4 a 20 mA ao
     CLP, que decide e aciona o atuador).
- Os 40 links de sensores de corrente, tensão e energia enviados no mesmo dia estão na fila
  (grupo 37). ACS712 e INA219 já têm PDF válido na pasta local do usuário; SCT-013 e ZMPT101B não
  têm PDF acessível (link quebrado nas duas listas) e precisam ser baixados pelo navegador antes
  do exemplo 1.

**Pedido complementar (2026-11-16):** exemplos que integrem inversores de frequência, CLP,
microcontroladores, motores e bombas. Os 30 manuais e catálogos de acionamentos enviados no mesmo
dia (inversores CFW e MW500 e soft-starters SSW da WEG, soft-starters Siemens, Schneider, ABB e
Rockwell, motores de passo StepperOnline, Oriental Motor e Kalatec) estão na fila (grupo 38); só
8 abrem o PDF, e os 16 links da WEG dão 404 (endereços inexistentes). Exemplos propostos para a
Fase 11, sujeitos ao seu ajuste:

5. **Bombeamento com pressão constante:** transmissor de pressão 4 a 20 mA na entrada analógica
   do CLP, PID no CLP, referência 0 a 10 V ao inversor de frequência (controle V/f), motor de
   indução trifásico com bomba centrífuga (carga com conjugado quadrático); ESP32 como supervisão
   (lê corrente e pressão e mostra no Serial).
6. **Partida de motor:** CLP comanda partida direta, por soft-starter e por inversor; o sistema
   compara corrente de partida, conjugado e tempo de aceleração.
7. **Posicionamento com motor de passo:** Arduino gera passo e direção para um driver de motor de
   passo; o CLP dá a ordem de ciclo e recebe o fim de curso.

Para isso a Fase 11 também precisa de modelos de motor de indução (circuito equivalente com
parâmetros de placa ou do fabricante), de bomba (curva do fabricante), do inversor (comportamental:
rampa, V/f, limites) e do motor de passo, todos com valores de documento (regra 1).

