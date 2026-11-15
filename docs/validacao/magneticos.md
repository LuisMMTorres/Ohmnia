# Validação: projeto de magnéticos (SV-MAG, Fase 6)

Data: 2026-11-15. Status: aguardando a sua aprovação; os dados dos núcleos aguardam a sua conferência.

O serviço `backend/src/circuitos/magnetics/` projeta indutores, indutores acoplados (flyback) e
transformadores sobre os núcleos do catálogo. Ele é chamado pelos módulos `DM-CC`, `DM-CCI` e
`DM-INV` no passo final do projeto (depois da escolha dos semicondutores); o resultado entra na
memória de cálculo, no resumo, nas perdas e na lista de materiais.

## Método

Referências: McLyman, *Transformer and Inductor Design Handbook*, 4ª ed. (método do produto de
áreas, indutor com entreferro, elevação de temperatura); Erickson & Maksimović, 2ª ed., cap. 13
(perdas no núcleo), 14 (indutores) e 15 (transformadores).

1. **Espiras.** Indutor e flyback: N = ⌈L·I_pk/(B_max·A_e)⌉. Transformador: N1 = ⌈λ/(ΔB_max·A_e)⌉,
   com λ os volt-segundos de meio ciclo e ΔB_max = 2B_max (push-pull, pontes) ou B_max (forward).
   Depois do mínimo o serviço procura N1 entre o mínimo e 4·N_min + 40 e fica com a perda total
   menor (cobre + núcleo).
2. **Entreferro** (indutor e flyback): l_g = μ0 N² A_e/L − l_e/μ_i (espraiamento desprezado).
3. **Janela:** Σ N·A_cu ≤ Ku·W_a (Ku = 0,4 por padrão). W_a sempre vem das cotas do desenho do
   núcleo, para comparar todos na mesma base; o comprimento médio da espira vem do carretel quando
   há carretel no catálogo, senão das mesmas cotas.
4. **Fio:** densidade de corrente J (4 A/mm² por padrão), fios em paralelo mais finos que 2δ na
   frequência de chaveamento, por isso R_ca ≈ R_cc; ρ do cobre a 100 °C.
5. **Perdas no núcleo:** forma de Steinmetz Pv = k f^α B̂^β ajustada aos pontos tabelados do
   material (3C96: três pontos, k, α e β exatos; 3C94: dois pontos na mesma frequência, só β) e
   ancorada na perda máxima do próprio núcleo no ponto do datasheet (100 kHz, 200 mT, 100 °C). A
   estimativa é, portanto, um máximo.
6. **Elevação de temperatura:** ΔT = 450·(P/A_t)^0,826 (P em W, A_t em cm², convecção natural), com
   A_t a área externa do núcleo montado; o projeto rejeita o núcleo se ΔT passar do limite (40 K por
   padrão).
7. **Escolha:** o menor núcleo (por A_p = W_a·A_e) que atende a tudo. Só entram núcleos, materiais e
   carretéis liberados (regra 5); se nenhum atende, o aviso lista o motivo de cada um.

## Catálogo usado

| Item | Fonte |
|---|---|
| Núcleos E 16/8/5 a E 65/32/27 e ETD 29 a ETD 54 (Ferroxcube) | folha de cada núcleo (Ae, le, Ve, AL sem entreferro, cotas, perda máx. por conjunto, Bsat mín.) |
| Materiais 3C94 e 3C96 (Ferroxcube) | especificação do material, 2008-09-01 (pontos de Pv a 100 °C) |
| Carretéis EE 30/15/7, 42/21/15, 42/21/20 (Thornton) | folha do núcleo NEE, página de acessórios (janela e comprimento médio da espira) |

A Ferroxcube não dá a janela do carretel; a Thornton dá, mas o material IP12R não tem tabela de
perdas (só gráfico), por isso os núcleos Thornton não entram no catálogo, só os carretéis.

## Testes

`backend/tests/unit/magnetics/test_magnetics.py` (9 testes): bitolas AWG nos pontos de definição,
resistividade e profundidade de penetração, fio em paralelo, ajuste de Steinmetz reproduzindo os
pontos do material, geometria do E 30/15/7, coerência do indutor (N, l_g, B_pk, janela), espiras do
transformador minimizando a perda, núcleo não liberado nunca escolhido e mensagem de especificação
impossível. A indutância e a relação de espiras resultantes entram na simulação dos conversores
(`AS-*` de `DM-CC` e `DM-CCI`, ver [potencia-chaveada.md](potencia-chaveada.md)).

## Limitações

- Só ferrite: indutores de 60 Hz (filtro do inversor) não cabem em nenhum núcleo; o aviso diz isso.
- Entreferro sem correção de espraiamento; l_g calculado pode ficar um pouco maior que o necessário.
- Perdas de proximidade e efeito pelicular desprezados (fio fino em paralelo); indutância de dispersão
  não calculada (os transformadores da simulação têm K = 1).
- A temperatura de 100 °C dos pontos do material vale como referência; não há correção de Pv com a
  temperatura.
