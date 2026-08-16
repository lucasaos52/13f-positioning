# copycat_pop - triagem do pop pos-filing (closes diarios)

- 182097 eventos-ticker | 49 trimestres

## TESE (lideres copiados)

- day0 (anuncio, nao-tradavel): +0.0027 (t=+4.53)
- excesso +1d: +0.0005 (t=+1.68)
- excesso +3d: +0.0009 (t=+1.58)
- excesso +5d: +0.0014 (t=+1.63)
- excesso +10d: +0.0040 (t=+4.92)
- placebo B (janela -5d) +3d: +0.0019 (t=+3.13)
- placebo B (janela -5d) +5d: +0.0033 (t=+4.60)

## placebo A (sem seguidores)

- day0 (anuncio, nao-tradavel): +0.0033 (t=+5.90)
- excesso +1d: +0.0008 (t=+2.33)
- excesso +3d: +0.0011 (t=+1.45)
- excesso +5d: +0.0022 (t=+2.11)
- excesso +10d: +0.0047 (t=+5.07)
- placebo B (janela -5d) +3d: +0.0018 (t=+2.79)
- placebo B (janela -5d) +5d: +0.0036 (t=+3.82)

## gradiente pre-registrado: sa_adv (shadow AUM do lider / ADV do papel)

- +1d tercil alto - baixo: -0.0005 (t=-1.58) | terciles: +0.0008 / +0.0005 / +0.0003
- +3d tercil alto - baixo: -0.0005 (t=-0.78) | terciles: +0.0012 / +0.0010 / +0.0007
- +5d tercil alto - baixo: +0.0001 (t=+0.12) | terciles: +0.0012 / +0.0018 / +0.0014
## Veredito (49 tri, 182k eventos-ticker)

MORTO pela regra pre-registrada #2, com autopsia limpa em tres cortes:

1. SEM ESPECIFICIDADE DE COPYCAT: o placebo A (gestores sem seguidores) e
   igual ou MAIOR que a tese em todos os horizontes (+5d: +0.22% vs +0.14%).
   O que quer que os nomes facam apos o filing, nao depende de haver
   capital seguidor esperando.
2. SEM TIMING DE DISCLOSURE: o placebo B (mesma janela, 5 pregoes ANTES do
   filing) e positivo e forte (+0.33% em +5d, t=4.6) - o drift comeca antes
   de a informacao virar publica. Nao e reacao a divulgacao; e drift
   generico de posicao institucional nova (a compra em si se espalha por
   semanas e ja vem com momentum).
3. GRADIENTE FLAT: shadow_AUM/ADV nao escala o efeito (t entre -1.6 e
   +0.1) - a predicao central da tese copycat falha.

day0 (anuncio): +0.27% t=4.5 na tese, mas +0.33% no placebo A - nem o
salto do dia do filing e especifico de ser copiado.

CONCLUSAO PARA O BACKLOG: o "pop de 1-5 dias" documentado na era 2015 nao
existe nos nossos dados 2013-2026 na granularidade de closes diarios - ou
foi comprimido para intraday (EDGAR e raspado em tempo real ha anos) ou
nunca foi separavel do drift generico de nomes recem-comprados. A ressaca
trimestral (t=-2.53) continua sendo o unico efeito copycat real no preco -
e ela ja esta monetizada no campeao via FILTRO, que e onde o grafo paga.
Backlog do motor diario para copycat: FECHADO com causa e placebos.
