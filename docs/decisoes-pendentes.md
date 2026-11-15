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
