# Validação: catálogo de dissipadores (D8)

Data: 2026-11-14. Status: valores transcritos (`extraido`), aguardando revisão por amostragem.

## Fonte

- HS Dissipadores, *Catálogo 2026-27*, revisão S - 260927, 166 páginas.
  URL: https://www.hsdissipadores.com.br/catalogo.pdf · SHA-256
  `17eb80c6e833216c52ecc64e59c1bc0b7f487c1e57c861f14e872f318b96f206`.
  O catálogo permite divulgação só na íntegra; o PDF não é versionado, apenas o link e o hash.
- A loja **Rei do Dissipador** (reidodissipador.com.br, indicada no próprio catálogo) é do mesmo
  fabricante e vende os mesmos perfis HS.
- **Eletrogate** só vende um dissipador adesivo para Raspberry Pi, sem resistência térmica
  publicada; não entrou.

## O que foi transcrito

Arquivo `data/components/heatsink/hs-dissipadores-perfis.yaml`, 137 perfis (pp. 21–165), cada um
com:

| Parâmetro | Origem |
|---|---|
| `Rth_sa` (K/W) em 101,6 mm e ΔT = 75 K | "Resistência Térmica: x ºC/W/4”" na página do perfil |
| `perimeter` (mm) | "Perímetro" na página do perfil |
| `mass_per_length` (kg/m) | "Peso Linear" na página do perfil |
| `length` = 101,6 mm | p. 2 (resistências calculadas para 4") |
| `dT_ref` = 75 K | p. 10 (correção da temperatura) |

- 44 perfis trazem "não temos este perfil em estoque": ficaram com ciclo de vida `nrnd` e nota; a
  escolha automática só usa esses se nenhum outro servir.
- 3 perfis (HS 12552, HS 17050, HS 17068) têm Rθ marcada com (*), "considerando apenas a área
  externa"; a nota foi copiada.
- O teste `DS-CATALOGO` conferiu cada valor na página citada do PDF baixado: 685 conferências
  (os três valores de cada perfil, mais comprimento e ΔT de referência repetidos em cada um),
  todas encontradas.

## Correção da elevação de temperatura

Tabela da p. 10, usada na escolha do dissipador (`thermal/heatsink.py`):

| ΔT dissipador–ambiente | 75 °C | 70 °C | 60 °C | 50 °C | 40 °C | 30 °C |
|---|---|---|---|---|---|---|
| Fator sobre Rθsa | 1,000 | 1,017 | 1,057 | 1,106 | 1,170 | 1,257 |

Abaixo de 30 °C o fator fica em 1,257 (fim da tabela). A correção por altitude (p. 12) e as
curvas com ventilação forçada não foram usadas.

## Limitações

- Só o comprimento do catálogo (101,6 mm): o fabricante diz que Rθ não escala linearmente com
  o comprimento e pede consulta para outros cortes.
- Largura e altura do perfil não foram transcritas (estão só nos desenhos).
- Os perfis modificados (pp. 152–165) entram como perfis independentes, com a Rθ da própria página.

## O que conferir

- [ ] Amostra de perfis na tela de revisão (Rθ, perímetro, massa) e liberação dos que usa.
