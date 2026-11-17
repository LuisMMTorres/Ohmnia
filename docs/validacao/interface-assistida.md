# Validação: interface assistida — primeira entrega

Data: 2026-11-17. Status: testado pelo usuário e aprovado para envio ao GitHub.
Branch: `codex/ui-assisted-workspace`.

## Referência e escopo

O usuário escolheu a segunda proposta de interface (**Bancada assistida**) após a análise do
STM32CubeProgrammer instalado. A aplicação adota navegação superior azul-escura, nomes ao lado
dos ícones, destaque discreto da área ativa, painéis claros e uma sequência explícita de trabalho.

Esta entrega aplica a estrutura visual às cinco áreas e implementa o fluxo assistido do
**Simulador**. As demais páginas mantêm seus controles e organização funcional existentes.

## Comportamento entregue

- A página inicial abre o Simulador. URLs com as áreas existentes continuam funcionando.
- Estado do servidor/ngspice no cabeçalho, com texto além da indicação de cor.
- Etapas **Circuito**, **Configurar análise** e **Resultados** alternam o painel visível.
  Configuração e resultados aparecem ao lado do esquemático, sem rolagem da página; os campos
  permanecem montados e conservam suas entradas. Em telas estreitas, o painel ocupa a largura disponível.
- Resultados indisponíveis antes do primeiro envio; ao simular, a área mostra andamento,
  resultados reais ou o erro retornado. Antes disso, exibe uma orientação sem gráficos fictícios.
- Biblioteca de componentes recolhida inicialmente e aberta por **Adicionar componente**.
  Ferramentas de seleção, fio, rótulos e pontas de prova permanecem disponíveis.
- Seleção de peças pelo desenho ou por uma lista no painel de propriedades.
- Atalho **Ir para a área de trabalho**, navegação Voltar/Avançar e ícone da aplicação no navegador.
- Cores adaptadas ao tema do sistema e organização em uma coluna em telas menores.
- Enquadramento automático ao redimensionar o canvas ou abrir/recolher a biblioteca, mantendo
  o circuito visível. Edição, arraste e zoom não provocam reenquadramento por si só.

## Verificação

- TypeScript e build Vite: aprovados.
- ESLint e Prettier: aprovados.
- Vitest: 39 testes aprovados.
- Navegador: 13 cenários de simulação aprovados, incluindo o divisor desenhado do zero.
- Fluxo assistido, foco de teclado, seleção de componentes, navegação e adaptação a 390 px: aprovados.

O teste de navegador usa um servidor e banco temporários separados dos dados do usuário.
Ele verifica as etapas, foco de teclado, seleção pela lista, biblioteca recolhível e largura
de 390 px, além dos cenários completos anteriores: RC/Bode, ponte/FFT, Monte Carlo,
pior caso, STEP, ruído, emissor comum, importação SPICE e desenho de um divisor do zero.

Durante a verificação, o cenário de desenho precisou trazer o canvas para a área visível antes
dos cliques por coordenadas e garantir que a barra de etapas não encobrisse o ponto escolhido.
Foi corrigido no teste, mantendo a conferência de 2,5 V no divisor desenhado. A inspeção visual
também encontrou o circuito fora da vista ao estreitar a janela: o editor agora observa mudanças
de tamanho e reenquadra o desenho. O ícone da aplicação passou a ser servido para eliminar a
requisição automática a um favicon inexistente.

## Como executar e conferir

Com as dependências e o ngspice configurados conforme o README:

```bash
cd frontend
npm run build
cd ../backend
uv run python -m circuitos
```

Abra `http://127.0.0.1:8000/#simulator`. No computador já configurado, o lançador local
`var/Iniciar-Ohmnia.cmd` também inicia a aplicação; ele não faz parte do repositório.

Para repetir os testes da interface: `npm run lint`, `npm run format:check`, `npm test` e
`npm run build`, dentro de `frontend/`. O fluxo completo de navegador continua em
`frontend/e2e/simulador.e2e.cjs` e pode ser iniciado por `scripts/e2e.sh`, com Playwright instalado.
No Windows, `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` pode apontar para um Chrome/Chromium já instalado.

## Limites e próximo passo

- Esta é a primeira entrega do padrão visual: o assistente de Projeto, catálogo, importação e
  bancadas ainda não possuem suas próprias etapas guiadas.
- A adaptação a telas pequenas mantém os controles acessíveis; a edição detalhada de circuitos
  continua mais adequada a teclado, mouse e uma tela maior.
- O build mantém o aviso já existente sobre o tamanho do pacote JavaScript. Divisão do pacote
  por área pode ser uma melhoria posterior.
- Próximo passo: avaliar espaçamento, legibilidade e disposição dos painéis no uso real antes
  de estender o fluxo assistido às outras áreas.

## Ajuste: nomes dos nós e seleção de sinais

- Controle **Exibir nomes dos nós** no Simulador. Anotações automáticas usam os nomes reais
  da netlist, sem alterar as conexões; são atualizadas após editar o desenho.
- Rótulos elétricos manuais permanecem visíveis. Circuitos incompletos exibem a razão pela qual
  o mapeamento não está disponível, sem reutilizar nomes de uma versão anterior.
- Resultados limitados às probes da execução e expressões adicionadas pelo usuário. Os seletores
  de FFT, XY e estatística usam o mesmo filtro. Não há seleção automática de todos os nós.
- Nenhuma mudança no cálculo elétrico do ngspice.
- A análise de ruído conserva seus resultados próprios de saída e referência (`onoise`/`inoise`),
  definidos pela configuração da análise, sem oferecer todos os nós internos.
- Teste de navegador ampliado para conferir o controle de nomes e a lista exata de probes do RC.

## Ajuste: abertura do navegador

O lançador `python -m circuitos` abre o navegador após a inicialização da aplicação e a abertura
da porta HTTP, substituindo o temporizador fixo de 1,5 s. `--no-browser` mantém o navegador fechado.
Dois testes do lançador aprovados: inicialização atrasada com requisição HTTP no momento da abertura
e inicialização sem abertura automática. Ruff aprovado nos arquivos alterados do lançador.
