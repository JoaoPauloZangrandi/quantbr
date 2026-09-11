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

### A barra que o alicerce estabeleceu (10/09/2026)

As três famílias já foram construídas e medidas. **O null certo — comprar todo o universo
líquido em peso igual e segurar — venceu as três em Sharpe.** Isso vale para as duas
frentes: qualquer estratégia, ortodoxa ou alternativa, tem que ser comparada com isto.

| | retorno líquido | acima do CDI | Sharpe (vs CDI) | max DD | giro |
|---|---|---|---|---|---|
| **benchmark equal-weight** | **+22,4%** | **+12,5 p.p.** | **0,57** | −36,9% | 4%/mês |
| momento 12-1 | +26,0% | +16,1 p.p. | 0,55 | −42,1% | 27%/mês |
| reversão 1 mês | +8,3% | **−1,6 p.p.** | 0,16 | −75,7% | 81%/mês |
| armagedom defensivo | +10,8% | +1,0 p.p. | 0,14 | **−21,6%** | 26%/mês |

200 meses (2010–2026), 20 papéis, líquido de custo, filtro de R$500 mil/dia.

Leitura, em uma linha cada: **momento** rende mais e arrisca mais na mesma proporção;
**reversão** perde do CDI depois do custo e está morta; **armagedom** entrega o drawdown
menor que promete e cobra por isso quase todo o prêmio.

O detalhe completo, com o porquê de cada morte, está em `estrategias/MORTAS.md`.

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
