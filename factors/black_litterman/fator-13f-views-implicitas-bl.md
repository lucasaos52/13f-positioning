# Posição como visão implícita

**Nota de desenho — fator de posicionamento 13F**
*Otimização reversa, Black-Litterman e encolhimento empirical Bayes*

---

**Tese em uma frase.** Todo fator de 13F é cego a risco. Uma posição de 3% não é uma crença: 3% num nome de vol 20% e 3% num de vol 70% são convicções completamente diferentes, e a condição de primeira ordem de Markowitz diz exatamente por quanto.

## 1. O problema com peso como medida de convicção

O sinal padrão de posicionamento é peso, ou variação de peso. Peso é uma medida de **dólares**, não de **crença**. Dois gestores com a mesma posição percentual em nomes de perfis de risco opostos estão fazendo apostas de magnitudes muito diferentes, e nenhuma métrica baseada em peso consegue distinguir isso.

A pergunta certa não é "quanto dinheiro esse gestor colocou aqui", e sim: **o que ele teria que acreditar para que essa carteira fosse ótima?** Essa pergunta tem resposta fechada, canônica e de uma linha.

## 2. A ferramenta: otimização reversa

Toda carteira é a solução de *algum* problema de média-variância. Invertendo a condição de primeira ordem:

$$q_i \;=\; \lambda\,\Sigma\, w_i^{a}$$

onde $w_i^a$ é o vetor de pesos **ativos** do gestor $i$, $\Sigma$ a matriz de covariância e $\lambda$ a aversão a risco. O vetor $q_i$ é o conjunto de **retornos esperados implícitos** do gestor — as *views* que racionalizam a carteira observada.

Isto é exatamente o mecanismo que Black-Litterman (1992) usa para extrair retornos de equilíbrio a partir do portfólio de mercado. A diferença é o objeto de aplicação: aqui a inversão é feita **por gestor**, para recuperar a view de cada um, em vez de uma vez só sobre o mercado.

Como $\Sigma w$ é o vetor de contribuições marginais ao risco, a leitura econômica é imediata:

> **O fator mede onde os gestores estão gastando orçamento de risco, não onde estão gastando dólares.**

Duas simplificações caem de graça e eliminam parâmetros que precisariam ser defendidos:

- Usar peso **ativo** em vez de peso bruto faz o prior de equilíbrio se cancelar sozinho: exposição ativa zero implica view implícita zero. Não é necessário construir o vetor $\Pi$ de equilíbrio do BL — o desvio já *é* a view.
- $\lambda$ desaparece na padronização transversal. É um escalar positivo comum a todos os nomes daquele gestor; após o z-score na seção cruzada, não sobra nada dele. Um hiperparâmetro a menos.

## 3. A decomposição é exata e automática

Com um modelo de risco fatorial canônico, $\Sigma = BFB' + D$, a expressão se separa sem nenhum trabalho adicional:

$$q_i \;=\; \lambda B\underbrace{FB'w_i^a}_{\text{views de fator}} \;+\; \lambda\underbrace{D\,w_i^a}_{\text{views de nome}}$$

Não há projeção, regressão auxiliar nem ortogonalização. A separação entre *aposta de estilo* e *aposta de empresa* **já está na álgebra do modelo de risco**. Descartando o primeiro termo:

$$q^{\text{idio}}_{i,n} \;=\; \sigma^2_{\varepsilon,n}\; w^{a}_{i,n}$$

Peso ativo multiplicado pela variância idiossincrática. Um produto elemento a elemento.

A simplicidade do resultado é a virtude, não um problema: não é um palpite sobre como ponderar peso por risco, é o que a decomposição canônica entrega, e cada passo até ali é defensável linha a linha numa sessão técnica.

## 4. O agregador: empirical Bayes em vez de lista curada

Black-Litterman exige uma matriz de confiança $\Omega$ sobre as views. Esse slot é precisamente onde a noção de *smart money* deve entrar — e é onde a prática de mercado costuma errar, rankeando gestores por alfa passado e ficando com o decil superior.

James-Stein (1961) mostra por que isso está errado: estimativas amostrais extremas são majoritariamente ruído, e o estimador de menor erro quadrático médio **encolhe** em direção à média. Então estima-se o alfa *holdings-based* de cada gestor (estilo DGTW, point-in-time) e aplica-se:

$$\tilde{a}_i \;=\; \frac{\tau^2}{\tau^2 + s_i^2}\,\hat{a}_i \;+\; \frac{s_i^2}{\tau^2 + s_i^2}\,\bar{a},
\qquad
\hat\tau^2 \;=\; \mathrm{Var}(\hat a) - \overline{s^2}$$

$\tau^2$ sai por método dos momentos da própria seção cruzada de gestores — é estimado, não calibrado. As consequências práticas são as que importam:

- Gestor com 3 trimestres de histórico tem $s_i^2$ grande e é encolhido para perto de zero automaticamente.
- Gestor com 40 trimestres retém quase todo o seu alfa estimado.
- **O filtro de histórico mínimo deixa de existir.** O encolhimento *é* o filtro, e ele é ótimo em vez de arbitrário. Não há lista de gestores escolhida a mão para defender.

O fator final agrega as views ponderadas por confiança:

$$f_n \;=\; \sum_i \tilde{a}_i\; q^{\text{idio}}_{i,n}$$

padronizado na seção cruzada a cada data de rebalanceamento.

## 5. A corrida aninhada

Os passos geram quatro sinais encaixados, e a previsão é melhora monotônica do IC ao longo da cadeia:

| Modelo | O que adiciona |
|---|---|
| 1. Peso ativo cru | linha de base — o sinal padrão da literatura |
| 2. $q = \lambda\Sigma w^a$ | escala por risco |
| 3. $q^{\text{idio}}$ | remove views de fator |
| 4. $\tilde{a}_i \cdot q^{\text{idio}}$ | pondera por skill encolhido |

Cada passo é uma hipótese testada isoladamente, não uma escolha de desenho assumida. Se o modelo 1 empata com o modelo 4, entrega-se o modelo 1 e escreve-se isso no memo — o resultado honesto é que o ajuste de risco não adicionava informação.

## 6. Higiene de validação

Esta é a metade do exercício que costuma decidir a avaliação, e aqui as ferramentas canônicas de ML entram com função definida:

- **Walk-forward com purge e embargo** (López de Prado). Não é decoração: a defasagem de 45 dias somada ao painel *ragged* cria sobreposição real entre treino e teste, e purge/embargo é a forma padrão de eliminá-la.
- **Deflated Sharpe ratio** (Bailey e López de Prado). Serão testadas várias variantes; reportar Sharpe cru depois de múltiplas tentativas é o erro clássico de seleção.
- **Fama-MacBeth com erros Newey-West.** O sinal é trimestral lido mensalmente, então a autocorrelação dos resíduos é mecânica e conhecida de antemão.
- **Atribuição de performance** contra FF5 mais momento, para verificar se o alfa sobrevive aos fatores que a etapa 3 já deveria ter removido. Se não sobreviver, a decomposição falhou e isso é informação.

## 7. Escopo e disciplina point-in-time

| Dimensão | Corte | Defesa |
|---|---|---|
| Janela | 2013 Q2 – 2025 Q4 | Primeiro trimestre com XML obrigatório. Preferir 50 trimestres limpos a 80 sujos de parsing de HTML. |
| Gestores | Todos os filers discricionários acima de limiar mecânico de tamanho | Sem filtro de skill: o encolhimento EB resolve endogenamente. |
| Ações | Common equity EUA, ≥ US$ 500 mi, preço ≥ US$ 5 | 13F é long-only; microcaps adicionam ruído de mapeamento e custo de execução. |
| Modelo de risco | Fatorial padrão, estimado apenas com dados até $t$ | $\Sigma$ é insumo point-in-time, não um objeto de fim de amostra. |
| Rebalanceamento | Mensal, decis, custo round-trip explícito | O sinal é trimestral mas a chegada é contínua. |

Pontos de disciplina que precisam estar corretos:

- **Acceptance timestamp** do EDGAR, nunca *period of report*. Painel ragged, sem preenchimento retroativo.
- **Amendments (13F-HR/A)** valem a partir da aceitação da emenda, jamais retroativamente sobre o trimestre original.
- **$\Sigma$ e o modelo de risco** estimados com janela terminando em $t$. Usar covariância de amostra completa é lookahead silencioso e é o erro mais fácil de cometer neste desenho específico.
- **$\hat{a}_i$ e $\tau^2$** calculados apenas com retornos realizados até $t$. O encolhimento é ele próprio um objeto point-in-time e precisa ser recomputado a cada corte.
- **Tratamento confidencial** e mapeamento CUSIP feitos point-in-time, com reuso de CUSIP tratado explicitamente.

## 8. Alternativas canônicas consideradas e descartadas

- **Fatoração de matriz com feedback implícito** (Hu, Koren e Volinsky, 2008; ALS). A matriz gestor×ação é literalmente o problema do Netflix Prize, e "ação com score latente alto que o gestor ainda não detém" é uma previsão de compra. Tentador e defensável — descartado porque o objeto previsto é demanda futura, não retorno, e fechar esse loop bem não cabe no prazo.
- **Gradient boosting sobre features derivadas de 13F.** Honesto e provavelmente competitivo, mas indefensável numa sessão técnica de 60 minutos onde a pergunta é "por que essa feature carrega informação". Vale como benchmark de teto no apêndice, não como entrega principal.
- **Filtro de Kalman sobre skill latente.** Mais elegante que empirical Bayes se o skill varia no tempo, mas exige assumir uma dinâmica de transição que não é defensável com observação trimestral.

## 9. Onde isto pode falhar

- **Tilt de volatilidade disfarçado.** O risco número um: $q^{\text{idio}} \propto \sigma^2_\varepsilon\, w^a$ dá peso maior a nomes de alta vol idiossincrática por construção. Rodar a correlação do fator com vol idio **antes** de qualquer backtest; se for alta, neutralizar e verificar se sobra sinal.
- **Erro de estimação em $\Sigma$ multiplica tudo.** O fator inteiro é linear na covariância. Rodar com dois modelos de risco distintos e reportar a dispersão dos resultados, não o melhor dos dois.
- **A CPO assume otimizador irrestrito.** Gestores têm limites de mandato, restrições de liquidez e bandas de tracking error. A violação é maior justamente nos nomes pequenos, onde a posição é limitada por capacidade e não por convicção — o que enviesa $q$ exatamente onde o alfa costuma estar.
- **Alfa holdings-based tem viés próprio.** O encolhimento corrige ruído, não viés. Se a medida de skill for sistematicamente enviesada, o EB não salva.
- **Visão parcial da carteira.** Sem short, derivativos ou ativos fora dos EUA, o peso ativo é uma sombra da exposição econômica real. Limitação do dado, não do método, mas precisa estar escrita.

---

*Referências de apoio: Black e Litterman (1992); Sharpe (1974), otimização reversa; James e Stein (1961); Efron e Morris (1975); Daniel, Grinblatt, Titman e Wermers (1997); Bailey e López de Prado (2014); López de Prado (2018).*
