# Crosswalk audit - CUSIP reassignment e ticker recycling

- 108826 instrumentos, 52 trimestres

## TESTE A - reassignment de CUSIP (exodo/nascimento falsos)

- eventos detectados (mesmo cusip6, morte->nascimento, gap<=2 tri, >= 5 holders): **1574** em 51 trimestres (~123.5/ano)
- holder-slots envolvidos (saidas FALSAS): 17,763 total = ~348/tri
- fluxo VERDADEIRO de saidas (amostrado): ~160,272 saidas/tri
- **taxa de contaminacao das saidas: 0.22%**
- valor mediano por evento: $2M; maiores:
| c6     | old          | new          | switch_q   |   holders_old |   val_bi | tk_old   | tk_new   |
|:-------|:-------------|:-------------|:-----------|--------------:|---------:|:---------|:---------|
| 44934N | 44934N207    | 44934N108    | 2024-03-31 |            28 |     2.07 |          |          |
| 44934N | 44934N207    | 44934N116    | 2024-03-31 |            28 |     2.07 |          | IBAC     |
| G5494J | BBG00GVR8YQ9 | BBG00GVR8YR8 | 2022-12-31 |             7 |     0.76 |          |          |
| 233331 | 233331842    | BBG001S5QN88 | 2022-09-30 |            34 |     0.74 |          |          |
| 443510 | 443510102    | 443510607    | 2015-09-30 |            35 |     0.63 |          | HUBB     |
| 842587 | 842587602    | BBG001S5W777 | 2022-06-30 |            43 |     0.62 |          |          |
| 842587 | 842587602    | BBG000BT9DW0 | 2022-06-30 |            43 |     0.62 |          |          |
| 65339F | 65339F861    | 65339F820    | 2016-06-30 |            14 |     0.52 |          |          |

## TESTE B - ticker com historico Yahoo comecando DEPOIS do instrumento (suspeitos de recycling/mismatch)

- suspeitos (lag > 100 dias): 176 de 3927 mapeados (4.5%); com valor >= $100M: 114
- NOTA: janelas sem preco sao excluidas pelo filtro px>=1 na decisao - o dano real e so quando o instrumento VELHO e negociado com precos do ticker NOVO; casos: 
| instrument_id   | ticker   | inst_first_q   | px_first   |   lag_days |   h_last |
|:----------------|:---------|:---------------|:-----------|-----------:|---------:|
| 19058X207       | COSO     | 2018-03-31     | 2025-05-08 |       2595 |       39 |
| 81730H109       | S        | 2016-09-30     | 2021-06-30 |       1734 |      275 |
| 260557103       | DOW      | 2015-03-31     | 2019-03-20 |       1450 |      911 |
| 82835P103       | SVM      | 2013-06-30     | 2017-05-15 |       1415 |      104 |
| 683344105       | ONTO     | 2016-03-31     | 2019-10-28 |       1306 |      334 |
| 04271T100       | ARRY     | 2017-03-31     | 2020-10-15 |       1294 |      140 |
| 52736R102       | LEVI     | 2016-03-31     | 2019-03-21 |       1085 |      160 |
| 039653100       | ACA      | 2016-03-31     | 2018-11-05 |        949 |      213 |
| 76118Y104       | REZI     | 2016-03-31     | 2018-10-29 |        942 |      279 |
| 019770106       | ALLO     | 2016-03-31     | 2018-10-11 |        924 |      116 |