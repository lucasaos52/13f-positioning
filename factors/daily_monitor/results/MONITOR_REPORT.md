# daily_monitor - os tres monitores da varredura

Spec de stress: v1 final (z(-DD)+z(PainBreadth), corte absoluto 2.0, defendida por ablacao). Books do combo reconstruidos PIT por trimestre (long top-50 new_conv resid; short top-50 distress supply).

## M1a - longs do combo detidos por gestores HOT

- delta 5d (tercil alto - baixo de hot-ownership/ADV): +0.0020 (t=+0.79, 22 tri) - negativo = o monitor identifica longs em risco

## M1b - alarme de squeeze nos shorts

- pos-alarme 5d: alarmados -0.0121 vs calmos -0.0012 (delta t=-2.60, 20 tri) - positivo nos alarmados = cobrir no alarme e a acao

## M2 - indice diario de deleveraging (AggStress)

- 1227 dias | corr(AggStress, vol de mercado 10d FUTURA) = +0.14 | corr com retorno 10d futuro = -0.00
- episodios no top-1% do indice (trimestres com mais dias): 2020Q4 (9d), 2020Q3 (3d)
- conditioner no combo-proxy: base Sharpe +0.49 / maxDD -17.1%  ->  gross 50% acima do p80 expanding: Sharpe +0.55 / maxDD -14.8%

## M3 - cover na exaustao vs segurar o short o tri inteiro

- PnL short: full +0.0132/tri vs timed -0.0020/tri (delta -0.0152, t=-1.52)
- borrow poupado: +0.07%/tri | fracao coberta antes do fim: 82%
- barra do monitor: nao perder PnL (delta >= 0 apos somar borrow) - e reducao de custo, nao alpha
## Veredito (full, 20-22 tri)

- M1a (aviso nos longs): MORTO - delta +0.20% (t=+0.79), sinal errado.
  Hot-ownership nao identifica longs que vao apanhar; nao vira regra.
- M1b (alarme de squeeze): INVERTIDO E UTIL - short alarmado (spike +7%/
  5d com volume 2x) cai -1.21% nos 5d seguintes vs -0.12% dos calmos
  (delta t=-2.60). O spike REVERTE: a acao correta e NAO cobrir em panico
  (se algo, manter/adicionar). Vira regra anti-panico da perna short.
- M2 (indice de deleveraging): UTIL COMO CONDICIONADOR - corr +0.14 com
  vol futura de mercado; episodios top-1% caem em 2020 sem rotulo; gross
  50% acima do p80 expanding melhora o combo-proxy: Sharpe 0.49->0.55 e
  maxDD -17.1%->-14.8%. Modesto e na direcao certa - exatamente o papel
  que a lei do projeto reserva a estado (condicionador de risco, nunca
  sinal). CSV diario em agg_stress_daily.csv para o grafico sistemico.
- M3 (cover na exaustao): MORTO - cobrir cedo perde -1.52%/tri (t=-1.52)
  e poupa so 7bps de borrow. Consistente com TODA a evidencia: a pressao
  nao exaure, continua - segurar o short o trimestre inteiro e certo.
