# Manual do usuário

Ohmnia: projeto, dimensionamento com componentes reais de datasheet e
simulação (ngspice) de circuitos de Eletrônica Analógica e de Potência.

1. [Instalação e primeiros passos](01-instalacao.md)
2. [Catálogo, revisão e importação de datasheets](02-catalogo.md)
3. [Projeto guiado: do requisito ao relatório](03-projeto.md)
4. [Simulador livre](04-simulador.md)
5. [Bancada de dispositivos](05-bancada.md)
6. [Perguntas frequentes e solução de problemas](06-problemas.md)

Para quem vai acrescentar topologias, categorias de componentes ou bancadas:
[guia de extensão](../guia-extensao.md).

## Três regras que o sistema não deixa quebrar

- **Nenhum valor de componente sem fonte.** Todo parâmetro do catálogo tem documento, página e
  trecho. Valor sem certeza fica "a verificar".
- **Nada entra na seleção automática sem a sua revisão.** Componente importado ou recém-cadastrado
  fica "em revisão" até você conferir cada parâmetro obrigatório e liberar.
- **Cálculo e simulação têm de concordar.** Cada projeto é conferido no ngspice; diferença acima da
  tolerância aparece como divergência, nunca é escondida.
