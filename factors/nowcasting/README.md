# nowcasting — o plano II, implementado com o que existe de graça

Implementação executável do `plano_nowcasting_13F.pdf` sobre a base 13F curada
(58M posições, datas de arquivamento reais por versão) e os painéis Yahoo.
`python run_nowcast.py` roda o estudo inteiro e escreve `results/REPORT.md`.

## A tese do plano, e o que ela implica aqui

Os dois números que definem o projeto: **níveis são triviais** (persistência
NDCG 0,889 vs 0,913 do melhor ML — o deep learning ganha 2,4 pontos de uma
heurística de uma linha) e **variações são quase imprevisíveis** (o melhor
proxy diário do mundo, inventário emprestável comercial, explica 13,8% da
variância do ΔIO trimestral). Logo: o alvo é a **variação**, o baseline
obrigatório é a **persistência**, e a métrica honesta é medida contra o Δ —
nunca contra o nível, onde qualquer calculadora de retornos exibe R² de 99%.

## O recorte — o que dava para fazer com dado público

A ordem de mérito do plano (§3.10) é liderada por três linhas que exigem dados
comerciais. Dizê-lo é melhor que fingir o contrário (§8 do próprio plano):

| linha | por que está fechada |
|---|---|
| Inventário emprestável (3.1, fit máximo) | exige S&P Global/DataLend. **A via preferida caso haja acesso** — documentada, não fingida |
| FIT de Lou (3.2) | exige TNA mensal de fundos (CRSP MF/Morningstar). N-PORT público daria trimestral com 60d — pior que o próprio 13F |
| ETFs exatos (3.2b) | holdings diárias de ETF são públicas *hoje*, mas não existe arquivo histórico gratuito para backtest |
| Order flow do tape (3.4) | R² 0,29% em mercado moderno — o plano mesmo o declara morto |
| Kalman completo (Camada 2) | escopo de semanas; as observações y1-y4 são as fontes fechadas acima. Fica o desenho e o sinal-âncora y5 |

O que **sobra é exatamente o miolo metodológico**: Camada 0, os baselines
aninhados, e a única observação de alta frequência que o próprio 13F fornece —
**a borda irregular**. Filers diferentes arquivam em dias diferentes; em D+30
já se conhece o ΔIO revelado por ~20% do painel. O plano chama isso de "sinal
âncora y5" e nós o promovemos a experimento central, porque é a única linha da
arquitetura inteira que não custa um dólar.

## Os seis experimentos e seus alvos de literatura

| # | experimento | alvo publicado | o que valida |
|---|---|---|---|
| X1 | R² do nível sob persistência | ~0,99 ("níveis triviais") | reproduzimos ≈0,96 — painel são |
| X2 | baselines no ΔIO (Modelos 0/1 do §6.2) | EMA não ajuda; hit 52-58% | EMA dá R² **negativo** — zero é difícil de bater, como previsto |
| X3 | âncora da borda irregular em D+15/30/45/60 | (novo — sem número publicado) | curva de acumulação: IC 0,07→0,13→0,82→0,87 |
| X4 | ΔIO revelado cedo prevê retorno? (PIT) | Christoffersen et al.: nada | nulo esperado e nulo medido |
| X5 | NDCG@10 persistência/EMA, painel mega vs ativo | 0,8891 / 0,8882 | heurísticas na mesma ordem; ativo < mega em persistência |
| X6 | Days-ADV tempo real vs defasado (E3) | (uso defensivo — GURU/ALFA 2015) | fração de nomes que migra >2 decis de crowding |

Nota de comparabilidade no X5: nosso NDCG é @10 com relevância = peso
verdadeiro; o benchmark usa node-affinity sobre o ranking completo. A
comparação válida é de **ordem** (heurísticas ~0,89-0,94, ML ganha pouco),
não de terceira casa decimal.

## Decisões de desenho

1. **Unidades de quantidade, sempre** (checklist §9): tudo em shares ou na
   razão IO = shares detidas / shares outstanding. Valor mistura preço e
   quantidade — é assim que nasce o R² espúrio de 99%. Bônus: com cada razão
   usando o SO **contemporâneo** da sua própria data, splits cancelam sem
   máquina de ajuste nenhuma.
2. **PIT dobrado do nowcasting** (§6.3): o alvo ΔIO(T) só existe quando os
   filings de T chegam — toda avaliação usa vantage T+75d; e a âncora usa
   exclusivamente filers com `filed_date ≤ d` real. Nenhuma feature usa o
   atraso realizado do trimestre corrente.
3. **IO > 150% é descartado com registro** — é glitch de shares outstanding
   (classe dupla, SO parcial), não posição real; winsorizar sem investigar é
   o atalho que o Plano I manda evitar.
4. **E1 testado e esperado nulo**: o retorno de antecipar a divulgação é a
   estratégia que o plano desaconselha ("premissa frágil"); medimos porque um
   nulo confirmado vale mais que uma promessa não testada.

## Limitações vivas

- Só sobreviventes têm retorno/SO (Yahoo); SO histórico começa ~out/2015 —
  X1-X4 efetivamente começam em 2016.
- O return gap (teto econômico, §3.8) exige retornos reportados por fundo e
  um mapa fundo↔filer — N-PORT resolveria; está no próximo passo, não aqui.
- ~40 trimestres = ~40 observações independentes nos testes trimestrais.
