# Ideias mortas — o que foi testado e não sobreviveu

Um arquivo de ideias mortas é o que impede uma casa de research de redescobrir o mesmo
beco sem saída a cada seis meses. Vale tanto quanto o de ideias vivas, e é mais honesto:
quem só guarda o que deu certo está construindo um viés de seleção próprio.

Regra: **toda estratégia rodada entra aqui ou no relatório de resultados.** Nunca
desaparece. O ledger completo de tentativas, com parâmetros, fica em
`protocol/trials.duckdb`.

---

## O que qualquer estratégia precisa bater

O **null certo** não é zero, nem o CDI sozinho: é comprar todo o universo líquido em peso
igual e segurar. Medido em 200 meses (2010–2026), com custo, filtro de R$500 mil/dia de
liquidez e retorno total:

| | retorno líquido | acima do CDI | Sharpe (vs CDI) | max drawdown | giro |
|---|---|---|---|---|---|
| **benchmark equal-weight** | **+22,4% a.a.** | **+12,5 p.p.** | **0,57** | −36,9% | 4%/mês |

Essa é a barra. Qualquer resultado abaixo dela é pior do que não ter feito nada.

---

## 1. Reversão de 1 mês — MORTA

**Testada em** 10/09/2026. Sinal: comprar os 20 papéis que mais caíram no mês anterior.

| | resultado |
|---|---|
| retorno líquido | +8,3% a.a. |
| **acima do CDI** | **−1,6 p.p.** |
| Sharpe (vs CDI) | 0,16 |
| max drawdown | **−75,7%** |
| giro | 81% ao mês |
| custo anual | 4,1% |
| custo que quebra | **3,0×** |

**Por que morreu, e é instrutivo.** O retorno bruto era +12,8% — já perdia do benchmark.
Depois do custo, perde do CDI. Três causas, todas mensuráveis na nossa base:

1. **Giro de 81% ao mês.** É a estratégia de giro mais alto que existe, por construção.
   Custa 4,1% ao ano de spread, e o custo que quebra é 3,0× — ou seja, basta o spread ser
   três vezes o medido num momento de estresse (o que acontece exatamente quando você
   precisa sair) para o resultado virar negativo.
2. **Drawdown de 75,7%** contra 36,9% do benchmark. Comprar o que caiu é comprar risco
   crescente, e numa crise isso se acumula.
3. **Parte do "retorno" é bid-ask bounce, não retorno.** O preço de fechamento alterna
   entre a ponta de compra e a de venda por acaso, e isso *parece* reversão sem que
   ninguém consiga capturá-la. É por isso que o motor cobra o spread do próprio papel: sem
   isso, essa estratégia pareceria funcionar.

**O que não foi testado**, e poderia mudar o veredito: reversão em janelas mais curtas
(semanal, diária) com dado intradiário, e reversão condicionada a fluxo forçado — que é
território do Codex e exige identificar o vendedor pressionado, não só a queda.

---

## 2. Momento 12-1 — VIVA, mas não bate o benchmark ajustado por risco

**Testada em** 10/09/2026. Sinal: retorno acumulado de 12 meses, pulando o mês mais
recente.

| | momento | benchmark |
|---|---|---|
| retorno líquido | **+26,0%** | +22,4% |
| acima do CDI | **+16,1 p.p.** | +12,5 p.p. |
| **Sharpe (vs CDI)** | **0,55** | **0,57** |
| max drawdown | −42,1% | −36,9% |
| giro | 27%/mês | 4%/mês |
| custo que quebra | 19,4× | ∞ |

**Rende mais e arrisca mais, na mesma proporção.** Ganha 3,6 pontos de retorno, paga com
10,5 pontos de volatilidade a mais e 5 pontos de drawdown — e o Sharpe fica empatado, um
centésimo abaixo. Em 200 meses essa diferença não é distinguível de ruído.

**Não está morta**, e a razão é o custo que quebra: 19,4×. A margem sobre o custo é
larguíssima, o que significa que o problema não é execução — é que a seleção não agrega
sobre comprar tudo. Sobrevive como candidata a componente de uma combinação, não como
estratégia isolada.

---

## 3. Armagedom defensivo — entrega o que promete, e só isso

**Testada em** 10/09/2026. Sinal: menor beta de queda (covariância com o mercado apenas
nos meses em que o mercado caiu), com volatilidade como desempate.

| | defensivo | benchmark |
|---|---|---|
| retorno líquido | +10,8% | +22,4% |
| acima do CDI | **+1,0 p.p.** | +12,5 p.p. |
| Sharpe (vs CDI) | 0,14 | 0,57 |
| **max drawdown** | **−21,6%** | −36,9% |

**Cumpre exatamente o contrato: 15 pontos a menos de drawdown.** E cobra por isso quase
todo o prêmio de risco — sobra 1 ponto acima do CDI, que dentro do erro amostral é zero.

**Como estratégia isolada, não se justifica**: quem quer o CDI compra o CDI, sem drawdown
de 21%. **Como componente**, é outra conversa: uma parcela defensiva reduz o drawdown do
conjunto, e é isso que ela foi construída para fazer.

**A limitação que não pode ser esquecida:** isto não é hedge. Numa ruptura de verdade a
correlação vai a um e a proteção encolhe justamente quando é mais necessária. Proteção de
cauda de verdade exige opção ou posição vendida, e a base não tem nem uma nem outra —
opção está fora do escopo e aluguel por papel exige o arquivo BTB da B3.

---

## Nota de método sobre estes três resultados

São **três tentativas**, com parâmetros escolhidos pela convenção da literatura e não por
busca. Isso importa: não houve otimização, então não há inflação por teste múltiplo aqui.
No momento em que alguém começar a varrer variações de janela, número de papéis ou filtro
de liquidez, o `custo_que_quebra` e o Sharpe param de significar o que significam agora, e
a correção por número de tentativas passa a ser obrigatória — o ledger em
`protocol/trials.duckdb` existe para tornar essa contagem possível.

**O tamanho efetivo da amostra também é menor do que parece.** São 200 meses, mas com
holding médio de poucos meses e um mercado que teve dois ou três regimes no período, o
número de apostas verdadeiramente independentes está mais perto de algumas dezenas do que
de duzentas.
