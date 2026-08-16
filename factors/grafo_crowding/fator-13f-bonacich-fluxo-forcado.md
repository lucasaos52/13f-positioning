# Vulnerabilidade de Bonacich na rede de propriedade institucional

**Nota de desenho — fator de posicionamento 13F**
*Prevendo fluxo forçado, não informação*

---

**Tese em uma frase.** Parar de tentar extrair informação de 13F e passar a prever *fluxo forçado*. Informação morre com a defasagem de 45 dias; pressão mecânica de venda não morre — ela ainda vai acontecer, e depois reverte.

## 1. O argumento que sustenta tudo

> **A defasagem de 45 dias é fatal para sinal informacional e inofensiva para sinal de fluxo.**

Se um gestor sabe algo sobre a empresa, isso já está no preço quando o filing é lido. Essa é a razão pela qual estratégias de *copycat* decaem tão rápido depois da divulgação. Mas se um gestor **precisa** vender — resgate, desalavancagem, corte de mandato de risco — a liquidação leva de dois a quatro trimestres para se completar, porque executar depressa é caro e o gestor sabe disso. Nesse caso não se está correndo contra o mercado: está-se lendo um cronograma de execução que ainda vai acontecer.

E pressão mecânica **reverte**. Coval e Stafford (2007) documentam reversão de *fire sale* ao longo de aproximadamente dezoito meses. É aí que está o dinheiro, e ele está na perna comprada: adquirir barato aquilo que foi vendido por motivo não-informacional. O trade não é arbitrado justamente porque quem naturalmente o faria está dentro da mesma rede, sofrendo o mesmo choque.

## 2. Três objetos, e só um deles é original

### 2.1 O choque — de onde vem a venda forçada

Esta é a parte que quase ninguém faz. Fluxo de fundo normalmente vem de CRSP ou Morningstar, que cobrem fundos mútuos e ignoram o resto. Mas o estresse pode ser inferido **de dentro do próprio 13F**, sem nenhuma base externa:

$$
\text{fluxo}_{i,t}
\;=\;
\underbrace{\frac{V_{i,t}}{V_{i,t-1}}}_{\text{crescimento do AUM reportado}}
\;-\;
\underbrace{\bigl(1 + R^{\text{port}}_{i,t}\bigr)}_{\text{retorno da carteira do trimestre anterior}}
$$

O retorno da carteira, $R^{\text{port}}_{i,t}$, é calculado com os holdings que o próprio gestor reportou em $t-1$ — portanto é um objeto *point-in-time* construído inteiramente com dados já em mãos. A diferença entre o crescimento observado do AUM e o crescimento que a carteira sozinha teria produzido é, por definição, entrada ou saída de capital.

O ganho prático é grande: isso estende a medida de estresse a **hedge funds** — exatamente os agentes alavancados e frágeis para quem não existe base comercial de fluxo. Define-se então o estresse do gestor combinando fluxo negativo com má performance recente, já que a relação fluxo–performance é convexa e bem documentada: quem cai capta resgate, e quem capta resgate vende.

### 2.2 A rede — como a pressão se propaga

Seja $A \in \mathbb{R}^{M\times N}$ a matriz gestor×ação de propriedade **discricionária**: peso ativo, não peso bruto, de modo que fundos de índice entrem na rede com aresta próxima de zero e não precisem ser filtrados a mão. A projeção no lado das ações,

$$G = A'A,$$

liga duas ações na proporção em que compartilham detentores. Normalizada por linha (ou simetricamente por grau), gera $\tilde{G}$: o canal por onde a pressão viaja de um nome para o vizinho.

### 2.3 O amortecedor — quem absorve o choque

Dividir a pressão pelo volume médio diário. Pressão idêntica em dois nomes de liquidez diferente não é pressão idêntica — é a mesma ordem contra dois livros de tamanhos distintos, e o preço reage de forma proporcionalmente diferente. Sem esse passo o fator vira, na prática, um *proxy* de tamanho.

## 3. A matemática: uma série geométrica

Vulnerabilidade de primeira ordem é apenas $s = A'(\text{estresse})$: quanta venda direta chega em cada nome. Isso é míope. Se um detentor da ação $n$ também detém nomes de *outros* gestores estressados, ele sofre contágio de segunda ordem e vende $n$ junto. A propagação completa é a soma de todas as ordens:

$$
v \;=\; s + \delta\tilde{G}s + \delta^{2}\tilde{G}^{2}s + \cdots
\;=\; \bigl(I - \delta\tilde{G}\bigr)^{-1}s
$$

Isto é exatamente a **centralidade de Katz–Bonacich**, e a escolha não é estética. Ballester, Calvó-Armengol e Zenou (2006) mostram que essa centralidade é o *equilíbrio de Nash* de um jogo com externalidades locais — ou seja, ela tem microfundação fechada. Não é uma métrica retirada de um catálogo de teoria de redes porque soava sofisticada; é a solução de um problema de agentes que reagem uns aos outros. Essa distinção é a resposta correta quando a banca perguntar "por que Bonacich e não PageRank".

Três consequências caem de graça:

- **$\delta$ não é hiperparâmetro livre.** É a propensão a repassar pressão: a fração de um choque que se converte em venda nos nomes vizinhos. Isso é **estimável** no painel, regredindo venda observada em nome vizinho sobre choque na origem. Reportar o intervalo de confiança de $\delta$, e não um valor calibrado à mão, é metade da defesa deste desenho.
- **$\lambda_1(\tilde{G})$ é um índice sistêmico grátis.** A série converge se e somente se $\delta < 1/\lambda_1$. O autovalor dominante da rede de propriedade é, literalmente, a distância até a instabilidade de contágio. Plotado de 2013 a 2025, é um resultado que existe independentemente de o fator dar retorno.
- **Nunca formar a inversa.** $G$ é esparsa; resolve-se $(I-\delta\tilde{G})v = s$ por Neumann truncada em três ou quatro termos — uns poucos produtos matriz–vetor esparsos. Além de barato, o truncamento é interpretável: cada termo é uma ordem de contágio, e vale reportar quanto cada ordem contribui.

## 4. O teste que separa sinal de história

Este é o ponto que distingue esta tese de *toda* estratégia informacional baseada em 13F:

| Interpretação | Movimento inicial | O que acontece depois |
|---|---|---|
| **Pressão** (a tese) | queda no nome | **reverte** em 2–6 trimestres |
| **Informação** (a alternativa) | queda no nome | **persiste**: o gestor tinha razão |

Se as quedas previstas por $v$ **persistirem**, não se encontrou fire sale — encontrou-se *smart money* vendendo por bom motivo, e a tese está errada. Isso vai escrito no memo com essas palavras. A perna comprada, que aposta na reversão do que foi vendido sem informação, é onde mora o retorno e é a menos disputada.

Dois testes de apoio, ambos capazes de matar o desenho:

- **Placebo de ordem.** Comparar $v$ contra o $s$ de primeira ordem. Se as ordens superiores não adicionam nada ao IC, a rede era enfeite — e o honesto é dizer isso, entregando o fator simples. Essa comparação também é a defesa contra a acusação de que a complexidade foi decorativa.
- **Decomposição por liquidez.** O efeito precisa ser monotonicamente mais forte nos nomes de ADV baixo. Se não for, o que se mediu não é impacto de preço por fluxo; é outra coisa usando a mesma roupa.

## 5. Escopo e disciplina point-in-time

| Dimensão | Corte | Defesa |
|---|---|---|
| Janela | 2013 Q2 – 2025 Q4 | Primeiro trimestre com XML obrigatório; inclui 2018, 2020 e 2022 — três episódios de estresse reais. |
| Gestores | Filers discricionários com ≥ 20 posições e dois trimestres consecutivos | O fluxo inferido exige $t-1$. O filtro importa *de verdade* aqui, ao contrário dos outros desenhos. |
| Ações | Common equity EUA, ≥ US$ 500 mi | O efeito vive nos nomes ilíquidos, mas microcap torna o custo proibitivo. Corte pelo que é executável. |
| $\delta$ | Estimado no painel, com IC reportado | Parâmetro econômico, não de ajuste. Robustez em $\delta \in [0{,}1;\,0{,}5]$. |
| Rebalanceamento | Mensal; alfa reportado **líquido** por decil de liquidez | Reportar alfa bruto num fator concentrado em ilíquidos seria desonesto. |

- *Acceptance timestamp* do EDGAR, nunca *period of report*. Painel ragged, sem preenchimento retroativo.
- Amendments (13F-HR/A) valem a partir da aceitação **da emenda**. Crítico aqui: uma emenda que corrige o AUM altera o fluxo inferido, e aplicá-la para trás fabricaria estresse que ninguém observou na época.
- $R^{\text{port}}$ calculado com retorno de preço ajustado por desdobramento e cisão. Usar retorno total contamina o fluxo inferido com dividendos.
- Tratamento confidencial distorce $V_{i,t}$ diretamente: a liberação posterior aparece como captação inexistente. Sinalizar e reportar com e sem esses pares.
- $\tilde{G}_t$ e $\delta$ estimados apenas com filings disponíveis em $t$ — a própria rede é um objeto point-in-time.

## 6. Linhagem honesta

O desenho conversa com Coval e Stafford (2007), Greenwood e Thesmar (2011), Lou (2012) e Antón e Polk (2014). Vale listar exatamente o que é novo, nesta ordem: **(i)** o gatilho de estresse é inferido do próprio 13F, o que estende a análise a hedge funds em vez de restringi-la a fundos mútuos com base de fluxo comercial; **(ii)** propagação de ordem superior com $\delta$ estimado, em vez de fragilidade de primeira ordem; **(iii)** a reversão tratada como *critério de falsificação*, não como resultado esperado.

## 7. Onde isto pode falhar

- **$G$ densa demais.** Se quase todo mundo detém quase tudo, $v$ vira um proxy de capitalização com passos extras. Primeiro teste a rodar, antes de qualquer backtest: correlação de $v$ com tamanho e com liquidez. Se for alta, o resto não importa.
- **Fluxo inferido é ruidoso.** Gestores com posições fora dos EUA, derivativos ou short têm $V_{i,t}$ que não reflete o AUM real, e o resíduo vira lixo em vez de fluxo. Por isso o filtro de gestor é substantivo neste desenho.
- **Custo come o alfa.** O efeito se concentra onde a execução é cara. O backtest precisa mostrar retorno líquido por decil de liquidez; se só o decil mais ilíquido paga, a conclusão honesta é que a estratégia tem capacidade baixa — e isso é uma resposta legítima, desde que dita.
- **Endogeneidade do estresse.** Gestores que sofrem resgate podem ser sistematicamente ruins, e seus nomes podem cair por mérito. O controle é comparar nomes vendidos por gestores estressados contra os mesmos nomes vendidos por gestores não estressados, no mesmo trimestre.
