# stopout - drawdown sintetico, stress e reversao tatica

ETFs removidos dos books (lista auditada do ETF_strat). Universo estrutural: 15-500 posicoes, >=250M, persistencia>=50%, active share>=40%.

## GATE H1 - stress sintetico preve venda forcada no filing seguinte?

- taxa de forced-sale: stressed 0.122 vs calm 0.067 (delta t=+1.62, 19 tri; media 188 gestores stressed/tri)
- sell breadth: 0.356 vs 0.323 (t=+1.12)
- fluxo implicito: -0.0058 vs +0.0162 (t=-1.69)

## Eventos taticos (CAR em excesso vs mercado, cluster/tri)

### H5 LONG exaustao (tese) (5402 eventos)
- CAR +1d: +0.0003 (t=+0.34)
- CAR +3d: -0.0002 (t=+0.13)
- CAR +5d: +0.0005 (t=+0.66)
- CAR +10d: +0.0016 (t=+0.68)

### placebo: mesmo crash, SEM dono stressed (5402 eventos)
- CAR +1d: -0.0006 (t=-0.58)
- CAR +3d: +0.0011 (t=+0.83)
- CAR +5d: -0.0017 (t=-0.15)
- CAR +10d: -0.0026 (t=-0.13)

### H4 continuacao (ainda caindo) (7196 eventos)
- CAR +1d: +0.0015 (t=+3.08)
- CAR +3d: +0.0013 (t=+1.17)
- CAR +5d: +0.0021 (t=+1.50)
- CAR +10d: +0.0075 (t=+2.09)

- **delta pareado tese - placebo (CAR5)**: +0.0025 (t=+0.95, 22 tri)

## PnL tatico (eventos H5, hold 5d, hedge de mercado, 10bps ida-e-volta)
- Sharpe (dias ativos): +0.12 | retorno +4.4%/aa nos dias ativos | 1302 dias ativos | media 20.7 posicoes/dia
## Veredito (19 tri de gate, 22 de eventos, 5.4k eventos-tese)

MORTO NO GATE, com um mecanismo que quase vive:

1. H1: o stress sintetico QUASE preve venda forcada - a taxa de
   forced-sale DOBRA (12.2% vs 6.7% dos calmos) e o fluxo implicito vira
   (-0.6% vs +1.6%), mas t=1.62/1.69 com 19 tri nao passa a barra. A
   direcao e consistente nos 3 eixos; a potencia nao chega. (A elegibi-
   lidade estrutural - active share, persistencia, cobertura - so produz
   universo >=150 gestores na metade recente da amostra.)
2. H5 (o alpha): a promessa do smoke regrediu a media - CAR5 +0.05%
   (t=0.66), delta tese-placebo +0.25% (t=0.95). O rebound pos-exaustao
   nao se distingue do mesmo crash sem dono stressed.
3. H4 saiu POSITIVO em +10d (t=2.09) - ate os nomes "ainda caindo" de
   dono stressed quicam em 10 dias tanto quanto os da tese: o que existe
   e bounce generico de crash, nao efeito de liquidacao.
4. PnL tatico liquido: Sharpe +0.12. Nada.

CONCLUSAO: refina a conclusao permanente do projeto - mesmo no relogio
DIARIO, com deteccao de exaustao e placebo pareado, o desconto mecanico
de fire-sale nao e separavel do bounce generico de crash. O stress
sintetico como INSTRUMENTO (quem vai vender) tem sinal real (taxa 2x) e
poderia ser re-testado com labels mais frequentes; como fonte de alpha
tatico, morre aqui. Coerente com Agarwal et al.: o efeito deles vive em
MEGA hedge funds visiveis com dados de performance externos - nossa
versao sintetica nao alcanca essa precisao.
