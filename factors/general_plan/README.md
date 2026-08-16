# general_plan — o plano de pesquisa 13F, implementado

Implementação executável do `plano_pesquisa_13F.pdf`: um fator principal com
história econômica limpa, um segundo eixo condicionante, três nulos declarados,
relógio point-in-time orientado a eventos e uma bateria de falsificação. Roda
inteiro com `python run_all.py` sobre a base 13F curada do projeto (58M
posições, 2013Q2–2026Q1) e os painéis Yahoo já cacheados.

## A tese, em duas frases

Quando gestores **concentrados e ativos** aumentam simultaneamente sua exposição
ativa a uma ação, dois mecanismos independentes empurram o retorno esperado para
cima: o relaxamento da restrição de venda a descoberto no sentido de Miller
(mais participantes precificados = menos otimismo residual no preço,
Chen-Hong-Stein 2002) e a agregação de informação privada, que na literatura de
best ideas concentra-se nas posições de maior tilt (Cohen-Polk-Silli 2010). O
sinal é deliberadamente cross-sectional e restrito a um subuniverso endógeno de
gestores, porque o portfólio institucional **agregado** é essencialmente o
portfólio de mercado (Lewellen 2011) e não pode conter informação.

## O que está implementado

| papel | fator | onde |
|---|---|---|
| principal | **ΔACWB** — variação da breadth ativa ponderada por convicção, com correção de drift de preço | `signals.dacwb` |
| segundo eixo | **Days-ADV** — dias de volume para liquidar a posição institucional (crowding com capacidade) | `signals.days_adv` |
| nulos declarados | **ΔIO**, **ΔNumInst**, **PSO** | `signals.nulls` |

Os nulos rodam pelo **mesmo** pipeline de transformação e pelo mesmo motor de
backtest que o fator principal — ou a comparação não significa nada. A previsão
da literatura (Chincarini-Lazo-Paz-Moneta) é que nenhum gere alfa; reproduzir
esse nulo é a validação mais barata disponível de que o pipeline funciona.

## As cinco decisões de desenho e suas defesas

**1. Relógio por `filed_date`, nunca D+45 fixo.** A base curada carrega a data
de arquivamento real de cada versão de cada filing. `snapshot_as_of(p, d)`
materializa o que era público em `d`: versões com `filed_date ≤ d`, RESTATEMENT
substitui, NEW HOLDINGS soma (confidencialidade expirada é aditiva por
definição). O grid **D+30/45/60** é o experimento do plano §5.1: alfa só em
D+60 implica os atrasados (hedge funds — reforça a tese de skill); alfa já em
D+30 implica os passivos rápidos (contradiz). D+45 fixo assumiria conhecer ~17%
dos filings que ainda não existiam — concentrados exatamente nos gestores
interessantes.

**2. Universo endógeno de gestores (§2.6), sem fonte externa.** Cada corte tem
uma razão econômica: 15–200 posições (menos → não é gestor de ações; mais →
quasi-indexer, Bushee 2001); HHI normalizado acima da mediana (benchmark hugger
não carrega convicção); turnover 4-tri acima do p33 (posições dedicadas de
longo prazo não prevêem retorno, Yan-Zhang 2009); AUM ≥ $250M; histórico ≥ 8
trimestres. Todos os limiares são computados **na data de decisão**, nunca na
amostra cheia — o lookahead de normalização do plano §5.1.

**3. Correção de drift no ΔACWB — o passo que separa o fator de momentum.** Se
o gestor não fez nada e a ação subiu 40%, o peso dela subiu sozinho. O sinal
usa `aw_hold = w_prev·(1+r_ação)/(1+r_carteira) − w_mkt` como contrafactual de
não-negociação. A eficácia é **medida**, não afirmada: no diagnóstico, a
correlação de posto com momentum 12-1 cai de ~+0,15 (sem correção) para ~−0,09
(com correção). É a resposta pronta para a pergunta que a banca faz em trinta
segundos.

**4. Market cap real, não proxy circular.** `w_mkt` e a neutralização por
tamanho usam preço cru × shares outstanding históricas do Yahoo
(`get_shares_full`, cobertura ~2015+; retro-projeção pelo preço ajustado antes,
com a aproximação declarada — exata sob splits, errada pelo drift de
buyback/diluição ~1-3%/ano, aceitável para ranks). O substituto óbvio — peso no
agregado 13F — é parcialmente circular: sinal e "tamanho" compartilhariam o
numerador. A fração de instrumentos que cai no fallback é logada por trimestre.

**5. Pipeline de transformação idêntico para todos (§4.1).** Filtro de universo
ANTES de qualquer estatística → winsor 1/99 → log nas razões de cauda longa
(Days-ADV, PSO) → rank percentil → resíduo da regressão em log-mktcap → resíduo
contra momentum 12-1 e retorno do trimestre anterior (feedback trading,
Nofsinger-Sias 1999) → re-rank. Por data, cross-section, sem estatística
full-sample.

## Falsificação (§6.1) — rodada e reportada mesmo quando passa

- **Sinal embaralhado** (200 permutações dentro de cada data) → p-valor de
  permutação do spread, livre de suposições distribucionais;
- **Sinal adiantado** (sinal de t+1 "prevendo" t) → tem que falhar; se
  funcionar, há lookahead no painel;
- **Metades da amostra** → estabilidade e decaimento pós-publicação
  (McLean-Pontiff 2016);
- **Sobreposição com momentum** → a métrica da decisão 3;
- **Monotonicidade entre quintis** → spread grande com quintis do meio
  bagunçados = dois nomes carregando o resultado (§5.5).

Custos: escada de {5, 10, 20, 50} bps por lado sobre o turnover medido, mais o
número mais honesto — o **breakeven**: a quantos bps por lado o spread líquido
zera.

## O que foi deliberadamente cortado (e por quê — §7.2)

| cortado | justificativa |
|---|---|
| Posições em opções | sem delta/strike não há exposição econômica; a curadoria upstream já as rejeita (0 linhas put/call na base) |
| Neutralização setorial | não existe GICS/SIC point-in-time grátis; usar a classificação de hoje retroativamente é lookahead — próxima etapa via SIC do EDGAR |
| Book-to-market na ortogonalização | fundamentals grátis têm ~4-5 anos de histórico; exclusão declarada |
| Perna short implementada | borrow por nome não modelável com dado grátis; Q5−Q1 é métrica de pesquisa, long-only a implementável |
| Koijen-Yogo demand system | projeto de semanas; é o item 1 dos próximos passos |
| Carteiras sobrepostas | com formação e holding trimestrais não há o que sobrepor; o grid D+30/45/60 é o experimento de timing |

## Limitações que continuam de pé

- **Sobrevivência**: retornos Yahoo só de tickers vivos. O sinal é computado na
  cross-section 13F **inteira** e só a carteira é restrita — mas o retorno da
  perna short em nomes que faliram não existe no painel. CRSP resolve; é o
  gargalo número um do projeto inteiro (quarta aparição).
- ~50 trimestres = ~50 observações independentes por lag. Graus de liberdade
  pequenos; nada aqui sobrevive ao limiar t>3 de Harvey-Liu-Zhu sem replicação
  em outra amostra.
- Crosswalk CUSIP→ticker por nome de emissor (não CUSIP6 histórico com
  vigência), turnover intra-trimestre invisível (Puckett-Yan 2011).

## Rodar

```bash
python run_all.py --smoke   # 8 trimestres, lag 45, ~3 min
python run_all.py           # amostra cheia, D+30/45/60, ~40-60 min
python fetch_shares.py      # (uma vez) shares outstanding, resumível
```

Saídas em `results/`: `summary.csv`, `events_*.csv`, `conditional.csv` (ΔACWB
dentro de terços de Days-ADV — a tabela 5×3 do plano), `diagnostics.csv`,
`REPORT.md`.
