# Quem faz o quê — divisão de trabalho no quantbr

Definido pelo João em 10/09/2026. Dois agentes trabalham neste repositório em paralelo.
Este arquivo existe para que cada um saiba o que **não** é seu, e para que ninguém
descubra a sobreposição depois de gastar um dia nela.

## O objetivo, para os dois

Uma casa de research quant para ações brasileiras, operada com **capital próprio e
pequeno**. Não é robô de trade: é pesquisa que termina em decisão de alocação. O que
distingue este projeto de um backtest de fim de semana é a recusa em aceitar resultado que
não sobreviva a custo, capacidade e teste múltiplo.

## Claude — base de dados e replicação de papers

**Fronte 1: a base.** É dono de `acoes_diario`, `emissor_mensal` e de todos os coletores
(`ingest/`, `master/`). Qualquer necessidade de dado novo passa por aqui — inclusive as do
Codex. Se uma estratégia precisa de um campo que não existe, quem constrói é o Claude.

**Fronte 2: o alicerce de estratégias.** Três famílias, que o João considera o mínimo de um
hedge fund:

| família | o que é | onde vive |
|---|---|---|
| **momento** | continuação de retorno passado (12-1, tempo-série) | `estrategias/` |
| **reversão** | correção de movimento recente | `estrategias/` |
| **armagedom** | proteção para cenário de ruptura — o que segura a carteira quando tudo cai junto | `estrategias/` |

**Fronte 3: replicar papers da SSRN.** O corpus já está na base (19.515 papers da SSRN,
20.676 do OpenAlex, triados). A tarefa é pegar paper por paper e testar no Brasil, com o
protocolo estatístico, e registrar tanto o que funciona quanto o que morre.

## Codex — estratégias alternativas

Território dele: **o que não cabe nas três famílias acima.** Small caps, mecanismos de
fluxo, situações especiais, empresas negligenciadas — o espaço onde instituição grande não
entra e onde o capital pequeno pode ter vantagem estrutural.

Já entregou `knowledge/small_caps/RELATORIO.md`: revisão de literatura sobre small caps e
estratégias acessíveis a capital próprio, com prioridades de pesquisa e a distinção entre
sinal economicamente interessante e sinal escalável.

O diretório `knowledge/` é dele. O Claude lê e não commita.

## A fronteira, em uma frase

**Claude faz o que é padrão e o que é infraestrutura; Codex faz o que é heterodoxo.** Se a
pergunta é "isso funciona no Brasil como funciona nos papers?", é Claude. Se é "existe algo
aqui que ninguém está olhando?", é Codex.

## O que os dois compartilham, e que ninguém pode quebrar sozinho

### Os números que restringem qualquer estratégia

Medidos na base em 10/09/2026 e válidos para os dois. Custo de ida e volta e capital que
cabe numa carteira de 20 papéis montada em 5 pregões:

| tamanho da empresa | custo ida-volta | capital que cabe | custo a 12 giros/ano |
|---|---|---|---|
| > R$ 10 bi | 0,20% | R$ 969 milhões | 2,36% |
| R$ 1–10 bi | 0,45% | R$ 85 milhões | 5,43% |
| **R$ 100 mi–1 bi** | **1,39%** | **R$ 1,76 milhão** | **16,73%** |
| < R$ 100 mi | 4,50% | R$ 110 mil | **54,05%** |

A leitura vale para as duas frentes: **o espaço onde instituição não entra existe, mas só
a giro baixo.** A faixa abaixo de R$ 100 milhões é armadilha dupla — comporta R$ 110 mil e
cobra 54% ao ano a giro mensal.

### A barra que o alicerce estabeleceu — REVISADA EM 11/09/2026

**Atenção: a barra de Sharpe 0,57 publicada em 10/09/2026 estava errada e foi retirada.**
Ela vinha de grupamentos não ajustados em papel de centavos, que entravam no painel mensal
como retorno de quatro dígitos (PDGR3 +4.170%, IRBR3 +2.938%, BHIA3 +2.007%). Quarenta e
três linhas em 31.915 carregavam o excesso sobre o CDI inteiro. O detalhe está no
`DIARIO.md`, entrada de 11/09 13:40, e em `REGISTRO.md` seção 6.

### O PISO DE LIQUIDEZ MUDOU PARA R$ 50 MIL — decisão do João, 15/09/2026

**Isto muda a barra e muda o universo.** O default do motor era R$ 500 mil de volume
mediano diário; passou a ser **R$ 50 mil**. O universo elegível vai de 146 para **192
empresas por mês**, e o custo médio do momento sobe de 2,1% para **5,0% ao ano**, porque a
cauda que entrou cobra spread de ida e volta de até 4,50%.

Números atuais, sobre a base **com o gabarito de evento da CVM** e **com o piso de R$ 50
mil** — 200 meses (2010–2026), 20 papéis, líquido de custo. Reproduzíveis com
`python -m estrategias.alicerce`:

| | retorno líquido | acima do CDI | Sharpe (vs CDI) | max DD | giro | capacidade |
|---|---|---|---|---|---|---|
| benchmark equal-weight | +4,3% | **−5,5 p.p.** | **−0,12** | −48,3% | 8%/mês | R$ 5,1 mi |
| momento 12-1 | +6,2% | −3,6 p.p. | −0,04 | −46,6% | 32%/mês | **R$ 0,8 mi** |
| reversão 1 mês | −18,4% | −28,2 p.p. | −0,72 | −97,5% | 86%/mês | R$ 0,7 mi |
| armagedom defensivo | +5,2% | −5,1 p.p. | −0,22 | **−26,0%** | 30%/mês | R$ 0,7 mi |

**Com o piso anterior de R$ 500 mil** (mesma base, para comparar): benchmark +6,3% /
−3,5 p.p. / **−0,03** / R$ 38,2 mi; momento 12-1 +10,8% / **+0,9 p.p.** / **0,16** /
R$ 6,9 mi; reversão −14,2% / −24,0 p.p. / −0,63; armagedom +7,5% / −2,7 p.p. / −0,08.

**Nenhuma das três famílias bate o CDI no piso novo**, e o momento volta a perder — o que
ele ganhou com a limpeza de eventos, perdeu com o custo da cauda ilíquida. A curva inteira
está em `estrategias/capacidade.py`.

**A limpeza de eventos não mexeu no benchmark: ele continuou em −0,03** (quem mudou a
barra depois foi o piso de liquidez, acima). O que mudou foi o momento, e por um
motivo de base, não de estratégia: 39 eventos de quantidade que ninguém ajustava entraram
no painel (29 deles confirmados pelo gabarito da CVM, ver `DIARIO.md` de 15/09) e 38
"eventos" que a contagem anual de ações confirmava por acaso saíram — entre eles o crash
da COVID em CVCB3 e IRBR3, que estava sendo apagado da série como se fosse desdobramento
4:3. Com a base limpa o momento sai de 0,4 p.p. abaixo do CDI para **0,9 p.p. acima**.

**Isso não promove o momento a estratégia.** 0,9 p.p. acima do CDI com Sharpe 0,16, em 200
meses, está dentro do erro padrão do próprio Sharpe (±0,24 para 16,7 anos), e o ponto
12-1 continua abaixo da mediana da grade de 24 variações. O que mudou é que ele deixou de
estar do lado errado do CDI.

**Duas coisas que mudaram de significado e não são comparáveis com números antigos:**

- **capacidade** agora é o GARGALO (`N × min(capacidade_dia) × 5 pregões`), não a soma. Os
  R$ 512 milhões que o momento reportava eram R$ 6,9 milhões. Linhas do ledger anteriores
  a 14/09/2026 guardam a soma.
- **giro** agora inclui o reequilíbrio de quem ficou na carteira, não só troca de nomes.

**A barra a usar é −0,12, com piso de liquidez de R$ 50 mil.** Qualquer estratégia,
ortodoxa ou alternativa, compara com ela — e quem não bater o CDI (9,8% no período) não é
estratégia, por melhor que seja o Sharpe relativo. **Compare sempre no mesmo piso**: um
Sharpe medido com R$ 500 mil não é comparável com um medido com R$ 50 mil, porque o
universo e o custo são outros.

### O horizonte de 1 mês tem CONTINUAÇÃO, não reversão (medido em 15/09/2026)

Vale para quem for desenhar sinal de curto prazo, e contraria a literatura importada.
`python -m estrategias.horizonte_curto` mede o spread transversal do sort de 1 mês
(quintil de cima menos quintil de baixo, realizado no mês seguinte):

| corte | spread anual | t (Newey-West) | meses |
|---|---|---|---|
| tudo | **+13,4%** | 3,17 | 200 |
| retorno do ponto médio (sem bid-ask bounce) | +12,7% | 2,95 | 200 |
| primeira metade (até 2018-05) | +15,8% | 2,88 | 101 |
| segunda metade | +10,9% | **1,55** | 99 |
| terço mais líquido do universo negociável | +13,0% | 2,68 | 200 |
| terço menos líquido | +7,8% | **0,95** | 200 |

Medido com o piso de R$ 50 mil. Com o piso anterior de R$ 500 mil dava +15,1% e t de 3,22,
ou seja, **descer o piso enfraqueceu o efeito em vez de reforçá-lo** — a cauda ilíquida
tem MENOS continuação, não mais (t de 0,95 no terço de baixo). A segunda metade da amostra
fica com t de 1,55: o efeito existe nas duas, mas não é significativo sozinho na recente.

O sinal é positivo: **o que subiu no mês passado continua subindo.** É o mesmo fato que a
família "reversão 1 mês" já dizia com Sharpe −0,63, e explica por que **pulo 0 bate pulo 1**
em 9 dos 12 pares da grade do momento. Não é artefato de microestrutura — medido sobre o
ponto médio (que não tem bid-ask bounce) o número não muda.

### As regras de convivência

Estão em `DIARIO.md`, e a primeira é a que pode corromper trabalho: **o DuckDB aceita um
escritor por vez.** Antes de rodar qualquer coisa que escreva no warehouse, registre no
diário. A tarefa agendada do Windows também escreve, às 20h, e não lê o diário.

### A regra de registro, que vale igual para os dois

Pedido do João em 11/09/2026, literal: **tudo que ele falar, tudo que o agente fizer e
tudo que o agente entender tem que ser registrado**, para que ele e o outro agente saibam
o que está acontecendo.

Isso é mais forte do que "documente o código". Significa três coisas:

1. **O pedido, nas palavras dele.** Não a sua interpretação do pedido — a frase. A
   interpretação vem depois, separada, para que dê para ver se você entendeu errado.
2. **O que você entendeu e decidiu.** Inclusive o que você decidiu NÃO fazer, e por quê.
   Uma decisão não registrada some, e a próxima pessoa a olhar o código vai refazer a
   discussão do zero.
3. **O que você mediu.** Número, não adjetivo. "Melhorou" não é registro; "Sharpe de 0,55
   para 0,60 em 200 meses, com 34 tentativas no ledger" é.

E o que deu errado entra com o mesmo peso do que deu certo — inclusive erro do próprio
agente. Este repositório já tem registrados: um Sharpe calculado sem descontar o CDI, uma
coleta de 30 minutos perdida por erro de schema, e um backoff de lock que nunca disparava
porque a mensagem de erro estava em português. Os três viraram teste.

### Onde cada coisa é registrada

| arquivo | o quê |
|---|---|
| `DIARIO.md` | cronológico e de processo: quem pediu o quê, quando, o que foi feito. **Toda ação vira entrada, assinada.** |
| `REGISTRO.md` | temático e de conteúdo: estado da base, bugs com o caso concreto que os revelou, decisões e o porquê |
| `crosswalk/` | decisão humana com evidência por linha |
| `knowledge/` | pesquisa do Codex |
| `EQUIPE.md` | este arquivo |

### O padrão de prova, igual para os dois

Herdado da leitura que o João mandou guardar ("The Only Way to Become a Good Quant") e da
regra do projeto de que auditoria mede e não conserta:

- comparar contra o **null certo** (buy-and-hold, aleatório de mesmo giro), não contra zero
- **tamanho efetivo de amostra**: 10 anos com holding de 6 meses ≈ 20 apostas
  independentes, não 2.500 observações
- **contar as tentativas** — 200 variações testadas e o "melhor" é quase todo construção
- **aumentar o custo até a estratégia quebrar** e reportar esse limiar junto do Sharpe
- **arquivo de ideias mortas**: o que não funcionou fica escrito, com o porquê
- resultado sem custo e sem capacidade não é resultado
