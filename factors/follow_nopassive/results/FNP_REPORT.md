# follow_nopassive - seguir lideres copiados SEM a cauda passiva

A = elegibilidade original (15-500 pos, >=250M) | B = A menos filers com active share < 25% (lideres E seguidores E arestas).

- **excesso vs universo**: A -0.0362/tri (t=-1.59) | B -0.0364/tri (t=-1.60) | delta B-A -0.0002 (t=-1.08, 49 tri)
- **spread intra-flagged**: A -0.0082/tri (t=-2.50) | B -0.0089/tri (t=-2.56) | delta B-A -0.0007 (t=-1.21, 49 tri)
- passivos dentro da elegibilidade: 2 filers/tri; lideres usados A 96 vs B 96
## Veredito (49 tri)

A hipotese "o follow falhou por poluicao passiva" esta REFUTADA com o
numero mais limpo possivel: dentro da elegibilidade do copycat existem
apenas ~2 filers passivos por trimestre (o teto de 500 posicoes ja tinha
excluido os complexos), os lideres usados sao IDENTICOS (96 vs 96), e o
delta B-A e -0.02%/tri (t=-1.08). Seguir lideres copiados perde igual
nas duas versoes (ressaca intra-flagged t=-2.5, reconfirmando o
resultado original) - a falha do follow-the-money e do MECANISMO
(informacao ja no preco + eco de copiadores), nao do universo.
