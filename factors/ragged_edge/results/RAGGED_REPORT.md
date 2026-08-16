# ragged_edge - entrada por-nome no dia da informacao vs batch D+45

extra = retorno em excesso acumulado do book corrente DENTRO da janela de filing (o que o batch deixa na mesa ficando em caixa ate D+45). Pre-registro: long_extra > 0, short_extra < 0.

- **LONG (new_conviction ragged)**: bruto +0.0022/tri (t=+0.77); liquido de churn +0.0005/tri (t=+0.18) = +0.21%/aa
- **SHORT (distress ragged)**: -0.0008/tri (t=-0.22) - esperado NEGATIVO (ganho do short = +0.31%/aa); media 730 nomes short, 229 distressed/tri
- 50 trimestres
## Veredito (50 tri)

MORTO com utilidade: as duas pernas tem a direcao pre-registrada mas
magnitude de arredondamento (long +0.21%/aa liquido t=0.18; short
+0.31%/aa t=-0.22). A entrada por-nome no dia da informacao NAO adiciona
sobre o batch D+45 - o drift intra-janela do Miori, no nosso universo e
com residualizacao, e pequeno demais para pagar o churn.

VALOR DE DEFESA: responde com numero a pergunta "por que esperar D+45?"
- porque o custo de nao esperar foi medido: ~0.2%/aa, indistinguivel de
zero. O relogio batch do combo e aproximadamente otimo.
