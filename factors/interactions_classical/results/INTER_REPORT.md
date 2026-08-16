# interactions_classical - 13F x caracteristica classica

5 interacoes pre-registradas (sinal, condicionador, tercil alvo, sinal esperado do delta). Estatistica-veredito: delta pareado spread(tercil alvo) - spread(incondicional), NW(4). Bonferroni 5 testes: confirmado |t|>=2.57 com sinal certo; sugestivo |t|>=1.96.

## new_conv x mktcap (limits to arbitrage: small)

- incondicional: +0.0178/tri (t=+3.78)
- terciles mktcap T0/T1/T2: +0.0233 / -0.0052 / +0.0292 (alvo: T0)
- **delta pareado**: +0.0055/tri (t=+1.34, esperado +) -> **NAO confirma** (50 tri)

## dbreadth x io (Nagel 2005: low-IO short constraints)

- incondicional: +0.0054/tri (t=+1.17)
- terciles io T0/T1/T2: -0.0021 / +0.0119 / +0.0023 (alvo: T0)
- **delta pareado**: -0.0075/tri (t=-1.42, esperado +) -> **NAO confirma** (50 tri)

## distress x adv (impact of forced selling: illiquid)

- incondicional: -0.0132/tri (t=-0.90)
- terciles adv T0/T1/T2: -0.0029 / -0.0043 / -0.0053 (alvo: T0)
- **delta pareado**: +0.0103/tri (t=+1.05, esperado -) -> **NAO confirma** (50 tri)

## pressure x vol (flow moves price where vol is high)

- incondicional: +0.0059/tri (t=+1.09)
- terciles vol T0/T1/T2: +0.0027 / +0.0009 / +0.0111 (alvo: T2)
- **delta pareado**: +0.0052/tri (t=+0.77, esperado +) -> **NAO confirma** (50 tri)

## exit_rate x mom (exodus in losers: continuation)

- incondicional: +0.0127/tri (t=+0.96)
- terciles mom T0/T1/T2: +0.0228 / +0.0036 / +0.0060 (alvo: T0)
- **delta pareado**: +0.0101/tri (t=+2.02, esperado -) -> **NAO confirma** (50 tri)


# Identificacao do E4 (EXPLORATORIO, motivado pos-resultado)

Pergunta: o efeito de vol e size/iliquidez disfarcada? Se pressure x ADV/mktcap replicar o gradiente e vol_resid nao, era liquidez; se vol_resid segurar, e incerteza de valuation.

## pressure x adv (illiquid tercile)

- incondicional: +0.0060/tri (t=+1.11)
- terciles adv T0/T1/T2: +0.0030 / +0.0047 / +0.0081 (alvo: T0)
- **delta pareado**: -0.0030/tri (t=-0.50, esperado +) -> **exploratorio - sem claim formal** (50 tri)

## pressure x mktcap (small tercile)

- incondicional: +0.0059/tri (t=+1.08)
- terciles mktcap T0/T1/T2: +0.0024 / +0.0031 / -0.0018 (alvo: T0)
- **delta pareado**: -0.0035/tri (t=-0.61, esperado +) -> **exploratorio - sem claim formal** (50 tri)

## pressure x vol_resid (vol orthogonal to size/ADV)

- incondicional: +0.0059/tri (t=+1.08)
- terciles vol_resid T0/T1/T2: +0.0004 / +0.0021 / +0.0172 (alvo: T2)
- **delta pareado**: +0.0113/tri (t=+2.07, esperado +) -> **exploratorio - sem claim formal** (50 tri)

## pressure_o x vol (pressure orth. to mom/strev/retq)

- incondicional: +0.0070/tri (t=+1.37)
- terciles vol T0/T1/T2: +0.0034 / +0.0009 / +0.0047 (alvo: T2)
- **delta pareado**: -0.0022/tri (t=-0.34, esperado +) -> **exploratorio - sem claim formal** (50 tri)

## pressure_o x vol_resid (double-orthogonal version)

- incondicional: +0.0067/tri (t=+1.27)
- terciles vol_resid T0/T1/T2: +0.0000 / +0.0041 / +0.0155 (alvo: T2)
- **delta pareado**: +0.0088/tri (t=+1.64, esperado +) -> **exploratorio - sem claim formal** (50 tri)


## Contaminacao de pressure por retornos passados
- corr(pressure, mom 12-1) media: -0.012
- corr(pressure, retorno do tri do fluxo): +0.008
- se altas, o sort de pressure e parcialmente um sort de momentum - dai a necessidade do pressure_o