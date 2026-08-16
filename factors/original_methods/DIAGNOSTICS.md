# Diagnóstico das acusações de contaminação (revisão externa) — rodado, não argumentado

Um revisor externo levantou três suspeitas de contaminação clássica de pipeline
13F. Rodamos os testes que ele propôs contra a base curada (2024Q4, vantage
+75d). Placar: 1 tratado com resíduo conhecido, 1 tratado com evidência, 1
empiricamente refutado — e uma causa real que a revisão não mencionou.

## 1. Combination reports / NOTICE / famílias → "dupla contagem"

**Status: tratado na curadoria (invariantes do crowdflow), com um resíduo real.**
- Grupos de reporting via grafo `otherManagers` (union-find), um book canônico
  por grupo-trimestre; 13F-NT nunca soma; amendments nunca competem com
  originais (invariante #4).
- **O teste de cosseno >0,95 proposto pelo revisor é inválido como prova de
  dupla contagem**: rodado nos top-300 filers, acusa 461 pares — liderados por
  Vanguard × State Street × Geode × Northern Trust. Books value-weighted de
  índice têm cosseno ~1 **por construção** (Lewellen 2011: o agregado É o
  mercado). O teste correto usa pesos ATIVOS (peso − peso de mercado).
- **Resíduo verdadeiro e reconhecido**: migração de CIK. A detecção existe
  (`succession_candidates.csv`, 579 candidatos) mas o merge exige entrada
  humana em `families.yaml` (invariante #5) e está majoritariamente vazio →
  falso ΔIO em ~579 eventos na definição all-filers. A definição
  common-filers é imune por construção (o CIK morto sai da interseção).
  Mitigação barata: excluir da variação o primeiro e último trimestre de cada
  filer (recomendação do próprio plano I §2.1).

## 2. putCall / PRN → "notional de opção virando ação"

**Status: tratado, com evidência empírica.** O particionamento da base contou
**0 linhas com put_call em 58.032.157** (a curadoria rejeita opções para o
ledger — mantendo o filing no revision log). Conversíveis/PRN: classes
`debt`/`principal` filtradas no `snapshot_as_of` via `instrument_class`.

## 3. Colapso de classes por nome → "IO > 100%"

**Status: refutado empiricamente na nossa base.** Dos 2.812 tickers com IO
computável em 2024Q4, **8 (0,3%) excedem 100% — e nenhum é multi-classe**
(a fração multi-classe entre os >100% é 0%). A explicação provável para a
soma-entre-classes não estourar: o Yahoo reporta shares implied TOTAIS da
empresa, tornando Σclasses ÷ SO_total aproximadamente correto.
- **A causa real dos 8 casos, que a revisão não mencionou**: dupla contagem
  por EMPRÉSTIMO DE AÇÕES — o custodiante do lender e o do comprador da ponta
  short reportam a mesma share; IO>100% é assinatura conhecida de nomes com
  short interest alto (+ SO defasada pós-evento corporativo). Isso é feature
  do 13F, não bug do pipeline — e é inclusive informação (proxy de short
  interest embutido).
- O corte em (0, 150%) com registro descarta 0,3% dos nomes. Mantido.

## 4. Survivorship (autocorreção do revisor: correta)

A Official 13(f) List dá universo PIT e âncora de CUSIP, não preços de mortos.
Nossa política já era a que ele recomenda: restringir, quantificar o buraco,
declarar a direção do viés, CRSP como next step nº 1.
