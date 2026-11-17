# Validação: correções numéricas conhecidas

Data: 2026-11-16. Revisão do usuário pendente.

## Limitador com Zener (DM-OPNL)

Os casos `opnl_limitador` e `opnl_limitador_g2` foram reproduzidos no Windows com ngspice 47.
O erro era de convergência (`timestep too small` em `XD2.BD`), antes de qualquer comparação
analítico × simulação. O diodo comportamental tinha resistência de condução de 10 µΩ,
em série com o Zener e um nó quase flutuante quando bloqueado.

A correção divide igualmente a resistência de condução total do ramo entre os dois elementos
da netlist. O Zener equivalente mantém `VZ0 = VZ − IZT·rz`; a soma das resistências continua
`rz_original + 10 µΩ`. Portanto, o limiar `VF + VZ0` e a inclinação em condução são os mesmos.
Não são parâmetros novos de datasheet: é uma transformação numérica do mesmo ramo em série.
Os registros do catálogo e os demais circuitos com diodo mantêm seus modelos anteriores.

O caso G = 1 não chega a limitar (pico esperado de 5 V); G = 2 conduz pelos Zeners
(pico esperado de 5,32444178 V com as peças selecionadas no catálogo de testes).
A tolerância dos dois picos permanece em 1 %. Há regressões pelo caminho padrão da biblioteca
e pelo executável (`test_limiter_batch`, nos dois ganhos).

## Fundamental do inversor (PT-INV-MA)

O caso registrado `ma = 0,5664`, `mf = 51`, bipolar, falhava de forma determinística com
32.768 pontos: fundamental de 0,564622499, erro de 0,313824 %.
O erro vem da discretização dos instantes de comutação, não da relação ideal `V1 = ma·Vdc`.

Em um período há 2·mf bordas por perna. Cada borda pode deslocar-se até um intervalo da grade;
considerando o salto de tensão e a normalização da amplitude de Fourier, o limite conservador
para o erro absoluto é `8·mf/N` (também vale para a soma das duas pernas unipolares).
Com N = 524.288 e mf ≤ 51 esse limite é 0,0007782, abaixo da tolerância absoluta de 0,001.
O teste passou de `2**15` para `2**19` pontos e inclui o caso conhecido como exemplo explícito
do Hypothesis. As tolerâncias relativa de 0,2 % e absoluta de 0,001 foram preservadas.
Nesse caso, a fundamental refinada é 0,566429400 (erro de 0,005191 %).
Como conferência independente, a integração por trechos entre as bordas encontradas por busca
de raiz recupera 0,566400000000; também recupera ma nos extremos ma = 0,1, mf = 51 e
ma = 1, mf = 9. Isso separa o erro de amostragem da relação física testada.

## Verificação

- Reprodução anterior à correção: os dois limitadores abortaram por convergência; o exemplo
  explícito do inversor falhou com fundamental de 0,564622499.
- Regressões corrigidas: dois limitadores aprovados pela DLL; propriedade do inversor aprovada
  com o exemplo explícito e os 40 exemplos gerados pelo Hypothesis.
- Ensaio pelo executável: erro de 0,002321 % em G = 1 e 0,000502 % em G = 2, em ambos os picos.
- Ruff (lint e formatação), mypy estrito e os dois contratos de importação: aprovados.
- A tentativa de suíte completa foi interrompida após mais de 15 minutos no
  `test_as_drv_05_stepper_position_and_load_angle`. Duas leituras de pilha localizaram a
  execução dentro da DLL do ngspice, chamada pela co-simulação do motor de passo.
  Nenhum arquivo de acionamentos ou co-simulação foi alterado nesta correção.
- A segunda rodada aprovou os 315 testes selecionados de comparação analítico × ngspice,
  referências e propriedades. A inicialização do primeiro cliente de API ficou bloqueada
  na criação de um socket local do Windows dentro do sandbox; essa rodada foi interrompida.
- Os testes unitários e de API restantes foram executados fora do sandbox, em quatro processos
  isolados (`pytest-xdist`, instalado somente no ambiente de teste): **644 aprovados, 1 pulado,
  nenhuma falha**, em 13 min 34 s. Cobertura dessa rodada unitária: **90,83 %**, acima dos 80 %
  exigidos (não é a cobertura de uma suíte integral).
- Total entre as rodadas concluídas: **959 testes aprovados e 1 pulado**. Permanecem excluídos
  `test_as_drv_05_stepper_position_and_load_angle` e o exemplo integrado
  `test_e7_stepper_reaches_each_position`, que usa o mesmo subsistema. O primeiro também foi
  tentado isoladamente fora do sandbox, sem cobertura, e excedeu o limite de 120 s.
  Esses dois testes não são considerados aprovados e precisam de investigação separada.

Os testes de datasheet com rede estão excluídos por configuração do projeto;
nenhum PDF do catálogo nem banco de dados do usuário é alterado por esta validação.

Para reproduzir (ngspice configurado conforme o README):

```bash
cd backend
uv run pytest tests/analytic_vs_sim/test_as_fase5.py -k limitador
uv run pytest tests/property/test_phase6_properties.py -k inv_ma_linear
uv run pytest tests/analytic_vs_sim tests/golden tests/property \
  --deselect=tests/analytic_vs_sim/test_as_drives.py::test_as_drv_05_stepper_position_and_load_angle
uv run pytest tests/unit --cov --cov-fail-under=80 \
  --deselect=tests/unit/cosim/test_examples.py::test_e7_stepper_reaches_each_position
```

Os dois últimos comandos são uma validação dividida com exclusões explícitas, não substituem
a suíte completa sem exclusões. No Windows, o TestClient precisa de sockets locais disponíveis.
