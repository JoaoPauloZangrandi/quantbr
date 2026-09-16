# Diário de trabalho — quantbr

Registro cronológico de **cada pedido do João e cada ação tomada em resposta**, para que
ele acompanhe o projeto sem precisar reler conversa, e para que mais de um agente possa
trabalhar no mesmo repositório sem se atropelar.

## Como escrever aqui

Regra pedida pelo João em 10/09/2026: **todo prompt dele e toda ação de um agente vira
uma entrada.** Sem exceção e sem esperar lembrete.

Uma entrada por pedido, neste formato:

```
### AAAA-MM-DD HH:MM — <agente> — <título curto>
**Pedido:** o que o João pediu, nas palavras dele.
**Feito:** o que foi efetivamente executado.
**Arquivos:** os que mudaram.
**Resultado:** o número, o teste, o que quebrou. Não "melhorou" — quanto.
```

Três coisas que distinguem este arquivo dos outros:

- **`DIARIO.md` é cronológico e de processo** — quem pediu o quê, quando, e o que foi
  feito. Serve para acompanhar e para dois agentes se coordenarem.
- **`REGISTRO.md` é temático e de conteúdo** — o estado da base, os bugs encontrados com
  o caso concreto que os revelou, as decisões e o porquê. É onde o conhecimento mora.
- **`crosswalk/`** guarda decisão humana com evidência por linha, versionada.

Quando dois agentes trabalham juntos, cada um assina a entrada (`claude`, `codex`) e
**lê as últimas entradas antes de começar** — é assim que se evita refazer ou desfazer o
trabalho do outro.

## Regras de convivência entre agentes

Quatro, e a primeira é a que pode corromper trabalho de verdade:

1. **O DuckDB aceita UM escritor por vez.** `painel.construir()`, `emissor.construir()`,
   qualquer `ingest.*` e `master.identidade` escrevem no warehouse. Antes de rodar algo
   que escreve, registre aqui uma entrada dizendo que vai rodar — e olhe se o outro
   agente não anunciou algo antes. `warehouse.connect()` tem backoff de lock, mas ele
   resolve espera, não resolve dois agentes reconstruindo a mesma tabela com premissas
   diferentes.
2. **A tarefa agendada do Windows roda todo dia às 20h** e também escreve (baixa o pregão,
   reconstrói `acoes_diario` e `emissor_mensal`). Não é um terceiro agente educado: ela
   não lê este arquivo. Evite reconstrução longa perto desse horário.
3. **Ordem certa: `git add` → `git commit` → `git pull --rebase` → `git push`.** Nesta
   ordem, e não em outra: `pull --rebase` com alteração não commitada falha na hora
   (aconteceu aqui em 10/09). Nunca `push --force` — o repositório é público e tem dois
   autores, e um force apaga trabalho do outro sem aviso.
4. **Não desfaça o que o outro fez sem registrar o porquê.** Se algo parecer errado,
   escreva a entrada explicando o que você mediu e o que mudou. Este projeto já teve um
   caso em que uma "correção" apagou a queda real da Americanas da série — mudança sem
   evidência escrita é como isso acontece.

---

## 2026-09-09

### 2026-09-09 22:20 — claude — Retomar contexto perdido
**Pedido:** "retome a conversa sobre ai hedge fund, meu computador reiniciou e eu perdi a
conversa"
**Feito:** reconstruído o estado a partir do disco (`REGISTRO.md`, `atualizacao.log`,
transcrições), sem confiar em memória de sessão.
**Resultado:** base viva e atualizando sozinha — a tarefa das 20h rodou às 22:15 e trouxe
os pregões de 08 e 09/09 (1.678.985 linhas). Última conversa havia parado no corpus da
SSRN (19.515 papers) com uma pergunta em aberto: vale o esforço de dado contábil?

### 2026-09-09 22:40 — claude — Auditoria do tratamento da base
**Pedido:** "quero que minha base de dados fique melhor tratada, tratando splits,
dividendos, mudança de nome, M&As, etc. como ela está e o que precisa ser feito?"
**Feito:** auditoria medida no banco, não estimada.
**Resultado:** quatro problemas quantificados —
(1) o detector de split reprovava evento óbvio: 438 quedas <−45% e 626 altas >+90% ainda
na série *ajustada*; (2) provento casado por nome deixava ABEV3 com **zero** dividendos em
13 anos e KLBN3/4 com zero em 21; (3) 104 pares de sucessão de ticker partiam a série em
duas (EMBR3→EMBJ3, R$1,28 tri de volume na perna morta); (4) 202 de 1.129 tickers sem CNPJ.

### 2026-09-09 23:10 — claude — Correção do detector de split
**Pedido:** escolha do João entre as frentes: começar pelo detector.
**Feito:** duas regras novas em `master/eventos.py` — denominador por faixa (razão ≥3 só
casa com inteiro) e tolerância em dois níveis (2,5% base, 5% com evidência independente).
**Arquivos:** `master/eventos.py`, `tests/test_deteccao_eventos.py`.
**Resultado:** os 7 casos-teste viraram confiança alta (CSAN3 saiu de −75,8% para −3,4%);
o crash da COVID na PETR4 continua reprovado, com margem de 0,17 ponto. Testes 16 → 32.
Descoberta que mudou a leitura: o detector antigo **apagava a queda real da Americanas**
casando a razão 4,41 com 13/3, e ajustava o desdobramento 8:1 da MGLU3 com fator 7,5.

### 2026-09-09 23:40 — claude — Como tratar eventos corporativos, em tese
**Pedido:** "como idealmente devem ser tratados splits e coisas do tipo para fazermos uma
estratégia de finanças quantitativas que pegaremos da ssrn?"
**Feito:** resposta metodológica — o retorno como primitiva (padrão CRSP), a taxonomia de
eventos, as três armadilhas (look-ahead do ajuste retroativo, filtro de preço em série
ajustada, viés de delisting) e o que cada família de paper da SSRN exige.

### 2026-09-09 23:55 — claude — Referência guardada
**Pedido:** link do Substack "The Only Way to Become a Good Quant" (Amy Khaldoun),
"quero que guarde para lembrar de coisas importantes ao longo do projeto".
**Feito:** salvo na memória permanente e citado na Fase 2 do `REGISTRO.md`.
**Resultado:** o protocolo de leitura de resultado dela (null certo, n efetivo, contar
tentativas, custo até quebrar, regime split) virou checklist da Fase 2. O projeto nº 1 da
lista dela é exatamente o que estamos fazendo: dataset limpo com split e dividendo.

---

## 2026-09-10

### 2026-09-10 00:20 — claude — Plano do securities master
**Pedido:** "vamos para o securities master por CNPJ. quero que seja o mais sofisticado e
robusto em relação a pesquisa o possível [...] veja se não há mais nada a ser
identificado e veja rigorosamente como resolver cada um deles [...] e então faça o
tratamento de fato da base"
**Feito:** exploração do repositório, auditoria de problemas ainda não identificados,
consulta ao corpus da SSRN e ao layout oficial da B3; plano de 8 etapas aprovado.
**Resultado:** **dois problemas novos, maiores que os conhecidos** —
(1) o filtro `codbdi='02'` apagava a empresa exatamente quando ela quebrava (108 papéis,
445 anos de série; AMER3 parava no dia seguinte à fraude);
(2) a unidade de cotação não era constante (238 papéis; CMIG4 tinha um grupamento 500:1
lido como "desdobramento 2:1").
Mais um limite duro: o `Codigo_Negociacao` do FCA da CVM está **vazio de 2010 a 2017**, e
148 dos 198 papéis sem CNPJ morreram antes de 2018 — não têm solução automática.
**Decisões do João:** delisting por motivo + convenção declarada; universo ON/PN/Unit com
coluna de regime (sem ETF); retorno vira a primitiva.

### 2026-09-10 01:00 — claude — Etapas 0 a 4, 6 e 7
**Feito:** implementação, teste e registro de sete das oito etapas.
**Arquivos:** `master/auditoria_tratamento.py` (novo), `master/eventos.py`, `painel.py`,
`master/identidade.py`, `ingest/proventos.py`, `config.py`, `ver.py`, `README.md`,
`crosswalk/` (novo), `tests/test_unidade_cotacao.py` (novo),
`tests/test_serie_append_only.py` (novo), `tests/test_universo_regime.py` (novo).
**Resultado por etapa:**
- **0** linha de base congelada em `acoes_diario_base_20260910`
- **1** 238 papéis normalizados por `fator_cotacao`; CMIG4 vira grupamento 495:1 com erro
  **0,045%** (era ~1%); 38 saltos resolvidos, 2 novos. A B3 confirmou por escrito no
  layout do COTAHIST: `'1' = UNIT QUOTE, '1000' = QUOTE PER LOT OF ONE THOUSAND SHARES`
- **2** papéis truncados **108 → 34**; AMER3 volta a ir até hoje
- **3** três pontes de identidade viram uma, com prioridade declarada; **93,0%** dos
  pregões com CNPJ; 198 pendentes exportados para decisão humana
- **4** sucessão encadeada: ELET3→AXIA3, EMBR3→EMBJ3, TRPL4→ISAE4 e mais 805
- **6** `retorno_qtd` e `retorno_total` na base; teste trava que evento novo não altera
  retorno antigo
- **7** 59 papéis com −100% por convenção declarada; sucessão de ticker **não** é perda
**Testes:** 32 → 62.

### 2026-09-10 07:39 — claude — Etapa 5: provento por CNPJ (duas tentativas)
**Feito:** coleta de proventos rechaveada por CNPJ, consultando todos os nomes candidatos
de cada empresa.
**Resultado:** dois erros pagos e registrados —
(1) a primeira rodada perdeu 30 min de requisição ao morrer na gravação, porque o schema
mudou e `replace_partition` insere em tabela existente. Agora o bruto vai para
`data/raw/b3_proventos/` **antes** do banco;
(2) a segunda trouxe a Klabin e deixou a Ambev de fora de novo: **a B3 devolve o CNPJ sem
o zero à esquerda** (`7526557000100`) e a CVM com ele. Corrigido com `lpad(...,14,'0')`.
**Descoberta:** a Ambev são **dois CNPJs** — Cia de Bebidas das Américas (02.808.708,
cancelada em 12/12/2013) e Ambev S.A. (07.526.557). Sucessão com troca de CNPJ, que
nenhuma chave automática liga; virou a primeira linha de `crosswalk/sucessao.csv`, com a
evidência escrita.

### 2026-09-10 08:20 — claude — Diário e repositório
**Pedido:** "vou colocar o codex para trabalhar junto com vc, quero que a todo prompt que
eu fizer e que voce for fazer algo, quero que anote num .md. além disso crie um
repositorio no meu github para ficar mais facil de eu acompanhar."
**Feito:** criado este arquivo com o histórico retroativo da sessão; repositório público
https://github.com/JoaoPauloZangrandi/quantbr criado e primeiro commit publicado (43
arquivos; os 1,4 GB de dados brutos e o warehouse ficam de fora pelo `.gitignore`).
**Nota:** o João escolheu **público** depois de eu apontar que uma casa de research com
capital próprio em vista perde a vantagem quando o método é aberto. Decisão dele,
registrada aqui.

### 2026-09-10 08:35 — claude — Etapa 5 fechada: provento por CNPJ
**Feito:** coleta rechaveada por CNPJ concluída (996 nomes, 576 CNPJs, 27.018 proventos)
e painel reconstruído.
**Arquivos:** `ingest/proventos.py`, `painel.py`, `crosswalk/sucessao.csv`, `REGISTRO.md`.
**Resultado:** ABEV3 sai de **zero para 32** proventos; KLBN3 e KLBN4 de zero para 70 cada;
KLBN11 para 47. Cobertura de provento por volume **91,0% → 93,3%**.
**Estado final das oito etapas:** linhas 1.678.985 → 1.761.012; tickers 1.129 → 1.146;
papéis truncados 108 → 34; cobertura de CNPJ 92,2% → 93,1%; testes 32 → 62.

### 2026-09-10 08:40 — claude — Resíduo classificado por causa
**Feito:** `master/auditoria_tratamento.py --residuo` passa a nomear a causa de cada salto
que sobrou, em vez de só contar.
**Resultado:** papel de centavos 734 saltos (200 papéis, precisa de gabarito de evento
anunciado); dia ex movimentado 367 (206, precisa da contagem de ações da CVM); regime
especial 85 (35, linhas recuperadas na Etapa 2); não classificado 25 (24, inclui a queda
real — é para ficar assim).

### 2026-09-10 09:10 — claude — Pesquisa na literatura e aplicação
**Pedido:** "pesquise profundamente na internet como tratar esse tipo de problema que
estamos tendo, caso ache tente aplicar na nossa base de dados e se não achar pode
continuar alterando o que for necessário na base para que ela fique suficientemente
satisfatório para ir pra produção"
**Feito:** quatro buscas e dois documentos primários lidos (paper da RBFin 2026 sobre
lottery stocks no Brasil; Shumway 1997/1999 sobre viés de delisting no CRSP). Três coisas
viraram código.
**Arquivos:** `master/eventos.py`, `painel.py`, `tests/test_deteccao_eventos.py`,
`REGISTRO.md`.
**Resultado:**
- **Quantidade de ações da CVM virou a terceira evidência do detector.** Se as ações
  multiplicam por N, o preço divide por N — é uma segunda medida do mesmo fator, vinda de
  fora da B3. Destravou MGLU3 8:1 (erro de preço 5,2%, CVM diz 8,81) e CASH3 6:1 (erro
  7,8%, CVM diz 6,36). Resíduo **1.211 → 1.153**.
- **Retorno de delisting: a literatura imputa −30%, não −100%** (Shumway 1997). A base
  passa a entregar as duas convenções lado a lado.
- **Descoberta que recalibra a expectativa:** o paper da RBFin (2026), publicado, com
  1.097 tickers do COTAHIST, declara que **não faz ajuste de evento corporativo nenhum**.
  Nossa base já está acima do que a literatura publicada usou.
**Trava validada:** AMER3, PCAR3 e a COVID na PETR4 têm razão de ações **1,00** — nenhuma
emissão — então não ganham a folga e continuam fora. Virou teste.
**Testes:** 62 → 68.

### 2026-09-10 09:40 — claude — Painel por emissor
**Pedido:** "implemente se achar que fica melhor para usarmos essas bases para fazermos
testes de estratégias quantitativas depois"
**Feito:** `emissor.py` → tabela `emissor_mensal` (75.420 linhas empresa-mês, 572
emissores, 2005-01 a 2026-09), ligada à rotina diária.
**Arquivos:** `emissor.py` (novo), `atualizar.py`, `tests/test_emissor_mensal.py` (novo),
`REGISTRO.md`.
**Resultado:** **30,7% dos meses-empresa têm duas classes negociando** — sem agregar por
emissor, quase um terço das observações de um teste cross-section seria a mesma firma
contada duas vezes.
**Onde discordei do paper:** ele escolhe a classe mais líquida *do mês* e usa o retorno
*daquele mês* — look-ahead correlacionado com o resultado. Aqui a escolha vem dos 12 meses
anteriores. A janela longa também resolveu um problema medido: com janela de um mês,
empresa ilíquida trocava de classe em metade dos meses (IGUAÇU CAFÉ 50,9%). Giro caiu de
**4,11% para 1,75%**, e o que sobra está inteiro em microcap de R$ 11,6 mil de volume
mensal — contra R$ 54,6 milhões nas que não trocam.
**Testes:** 68 → 71.

### 2026-09-10 10:15 — claude — Validação externa contra o NEFIN
**Pedido:** "e agora?" → escolhida a validação contra o NEFIN.
**Feito:** reingerido `ingest/nefin.py` (6.321 dias de fatores, 2001–2026) e revivido
`master/auditoria_precos.py`, que estava morto desde 02/09. Também registradas as regras
de convivência entre agentes no topo deste arquivo, porque o Codex entrou no projeto.
**Arquivos:** `master/auditoria_precos.py`, `master/eventos.py`, `DIARIO.md`,
`tests/test_deteccao_eventos.py`, `REGISTRO.md`.
**Resultado — a primeira medida de ACURÁCIA da base, não de consistência:**

| série | correlação com o mercado NEFIN |
|---|---|
| crua (sem ajuste) | **0,5381** |
| ajustada por quantidade | **0,9247** |
| retorno total | 0,9143 |

Ajustar quase dobra a correlação com uma referência acadêmica independente. E no acumulado
de 820%, a série de retorno total fica a −139 p.p. contra −584 da série sem provento — 445
pontos que só o dividendo explica.

**A validação achou um bug que nenhuma auditoria interna pegou:** OIBR4 em 22/12/2014,
R$1,00 → R$9,50, **+850%** com R$20 milhões de volume. OIBR3 e OIBR4 tiveram o mesmo
grupamento 1:9 no mesmo pregão; a ON errou 0,49% e passou, a PN errou 5,26% e foi
descartada por 0,26 ponto percentual. Grupamento é fato da **empresa**, não do papel —
criada `herdar_entre_classes`, 70 fatores herdados.
**Testes:** 71 → 74.

### 2026-09-10 18:20 — claude — Dado contábil: valor, qualidade e dividendo de quem morreu
**Pedido:** "deixe a base mais robusta para dividend yield, tamanho, valor e long-horizon
e outras coisas que achar importante"
**Feito:** `ingest/dfp.py` (novo) — 102.104 linhas de balanço da CVM, 2010–2026 — e o
painel por emissor ganhou as colunas contábeis com casamento **point-in-time real**.
**Arquivos:** `ingest/dfp.py` (novo), `emissor.py`, `atualizar.py`,
`tests/test_balanco_point_in_time.py` (novo), `REGISTRO.md`.
**Resultado principal — o dividendo de empresa morta, que era o maior buraco:**

| cobertura de dividendo (2011+) | empresa que **morreu** | empresa **viva** |
|---|---|---|
| via B3 (o que tínhamos) | **59,0%** | 82,1% |
| via CVM/DMPL (agora) | **95,1%** | 96,9% |

O vão entre morta e viva cai de 23 pontos para 1,8.

**Point-in-time de verdade:** a CVM informa a data real de entrega (mediana 88 dias, máximo
**964**), então cada mês recebe só o que já era público — e na versão que existia naquele
dia. Verificado na Petrobras: jan-fev/2016 usa o balanço de 2014; março troca para o de
2015, entregue em 21/03.

**Uma frente foi rejeitada por medição:** reconstruir a quantidade de ações para trás (para
ter valor de mercado antes de 2010). Nos anos com evento, aplicar o fator dá erro mediano
de 33% e **ignorar o evento dá 0,0%** — aplicar piora. Não foi feita.

**Colunas novas:** book_to_market, lucro_sobre_preco, roe, roa, dividend_yield,
dividend_yield_liquido, mais patrimônio, ativo, lucro, receita e a procedência contábil.
Cobertura: 72,0% dos meses-empresa com balanço.
**Testes:** 74 → 80.
**Nota:** li o `knowledge/small_caps/RELATORIO.md` do Codex antes de começar. A linha que
ele marca como prioridade alta — "valor com qualidade em empresas menores" — tem como
principal obstáculo "contabilidade disponível na data certa", que é exatamente o que este
bloco entrega. Não commitei `knowledge/`: é dele e pode estar pela metade.

### 2026-09-10 18:45 — claude — Custo e capacidade: a tese de capital pequeno, medida
**Pedido:** "continue se aprofundando na base. falei para ele que quero me aprofundar em
coisas que grandes instituição não cobrem porque pode ter algum edge pra mim que vou operar
com capital pequeno"
**Feito:** camada de custo e capacidade, a partir da melhor oferta de compra e venda que já
estava na base e ninguém usava (99% de cobertura desde 2008).
**Arquivos:** `painel.py`, `emissor.py`, `tests/test_custo_capacidade.py` (novo),
`REGISTRO.md`.
**Colunas novas:** `spread_relativo` (diário); `spread_mediano`, `amihud`,
`custo_roundtrip`, `capacidade_dia`, `turnover_mes`, `pct_dias_sem_negociar` (mensal).
Constantes declaradas com fonte: `EMOLUMENTO_B3 = 0,0300%` por lado (tabela da B3,
swing trade PF) e `TETO_PARTICIPACAO_ADTV = 10%`.
**Resultado — a tese medida, e ela tem duas metades:**

| tamanho | custo ida-volta | capital que cabe (20 papéis, 5 pregões) | custo a 12 giros/ano |
|---|---|---|---|
| > R$ 10 bi | 0,20% | R$ 969 milhões | 2,36% |
| R$ 1–10 bi | 0,45% | R$ 85 milhões | 5,43% |
| **R$ 100 mi–1 bi** | **1,39%** | **R$ 1,76 milhão** | **16,73%** |
| < R$ 100 mi | 4,50% | R$ 110 mil | **54,05%** |

**A leitura:** a faixa de R$100 mi a 1 bi comporta R$1,76 milhão — nenhum fundo opera com
isso, e é por isso que ela está vazia de instituição. Mas a 12 rebalanceamentos por ano ela
custa 16,7% ao ano só de custo. **O espaço existe, mas só a giro baixo** — e isso restringe
quais papers da SSRN vale replicar: os de sinal persistente, não os de reversão rápida.
**Testes:** 80 → 90.

### 2026-09-10 19:15 — claude — Divisão de trabalho e o alicerce de estratégias
**Pedido:** "eu tava pensando em deixar voce com essas tarefas de base de dados e puxar e
testar todo tipo de paper da ssrn e deixar o codex mexendo em estratégias alternativas como
essas em small caps [...] queria que voce fizesse o alicerce, com estratégias de momentum,
mean reversion, e uma estratégias para um cenário de armagedon, considero esse o minimo
para um hedge fund [...] quero que registre tudo [...] para que o codex consiga ler"
**Feito:** `EQUIPE.md` (novo, a divisão de trabalho), `estrategias/motor.py` (novo, o motor
de backtest), `estrategias/sinais.py` (novo, as três famílias), `estrategias/MORTAS.md`
(novo, o arquivo de ideias mortas), `tests/test_motor_backtest.py` (novo).
**Resultado — e ele é desconfortável.** O null certo (comprar todo o universo líquido em
peso igual e segurar) **venceu as três famílias em Sharpe**:

| | retorno líquido | acima do CDI | Sharpe (vs CDI) | max DD | giro |
|---|---|---|---|---|---|
| **benchmark equal-weight** | **+22,4%** | **+12,5 p.p.** | **0,57** | −36,9% | 4%/mês |
| momento 12-1 | +26,0% | +16,1 p.p. | 0,55 | −42,1% | 27%/mês |
| reversão 1 mês | +8,3% | **−1,6 p.p.** | 0,16 | −75,7% | 81%/mês |
| armagedom defensivo | +10,8% | +1,0 p.p. | 0,14 | **−21,6%** | 26%/mês |

**Um erro meu, corrigido no meio:** chamei de "Sharpe" a razão retorno/volatilidade sem
descontar a taxa livre de risco. Com CDI de 9,9% no período isso inverte leituras — o
armagedom caiu de 0,43 para 0,14 quando corrigi. As duas versões ficaram no ledger.
**Testes:** 90 → 94. O principal: um sinal que prevê perfeitamente o mês corrente não pode
lucrar, porque o motor usa o mês seguinte — com contraprova, senão passaria por vacuidade.

### 2026-09-11 07:40 — claude — Aprofundamento das três famílias
**Pedido:** "pode começar a puxar e testar os papers da ssrn. mas não assuma que a base
está perfeita e nem que as estratégias de momentum, mean revert e armagedom estão completo.
cada uma dessas coisas possui um mundo dentro, eu prefiro que voce se aprofunde nelas antes
de ir para os papers da ssrn"
**O que entendi:** eu tinha testado **um ponto** de cada família e tratado como se fosse a
família inteira. Antes de qualquer paper da SSRN, ir fundo nas três — e continuar duvidando
da base.
**Feito:** grade de robustez do momento, análise de momentum crash, escala de volatilidade,
overlay de tendência, retorno sobre ponto médio na base, reteste da reversão.
**Arquivos:** `painel.py`, `emissor.py`, `estrategias/motor.py`, `estrategias/sinais.py`,
`estrategias/MORTAS.md`, `warehouse.py`, `tests/` (3 arquivos).
**Resultados, todos em `estrategias/MORTAS.md` seção 4:**
- **Momento não é robusto.** 24 variações: Sharpe de 0,37 a 0,64, **mediana 0,547 — abaixo
  do benchmark (0,57)**. Só 11 de 24 batem a barra. O ponto que eu tinha escolhido está
  abaixo da mediana.
- **O momento quebra em regime identificável:** excesso de **+0,72%/mês** depois de 12
  meses de alta e **−0,74%/mês** depois de 12 meses de queda. Os 8 piores meses dele são
  todos de alta violenta do mercado.
- **Escala de volatilidade** troca retorno por segurança um-por-um (DD −42,1% → −32,2%,
  Sharpe 0,55 → 0,53). **Overlay de tendência** leva o momento a Sharpe 0,60 — candidato,
  não achado: 34 tentativas já no ledger.
- **Reversão: o contrário do que eu suspeitava.** Em papel de spread > 2%, o fechamento
  mostra autocorrelação zero e o **ponto médio mostra −0,074** — o fechamento defasado
  estava mascarando reversão real. Mas ela não é capturável: +0,1 p.p. acima do CDI com
  drawdown de 78%. A iliquidez que a cria impede colhê-la.
- **Armagedom: faltava a metade que importa** — decidir *se* ficar em ação, não só *quais*.
**Dois bugs achados no caminho:** o ponto médio explodia quando as duas pontas vinham
zeradas (5.757 linhas acima de 1.000%, corrigido na raiz); e o backoff de lock do
`warehouse.connect` **nunca disparava em Windows português**, porque procurava a palavra
"lock" numa mensagem que diz "já está sendo usado por outro processo". Esse só apareceu no
primeiro dia com dois agentes escrevendo.
**Testes:** 94 → 100.

---

## O que está aberto

| # | pendência | quem decide |
|---|---|---|
| 1 | 198 tickers sem CNPJ (148 morreram antes de 2018, quando o FCA da CVM ainda não trazia código de negociação) — lista em `crosswalk/pendentes_identidade.csv` | João, uma linha por vez, com evidência |
| 2 | 734 saltos em papel de centavos: precisam do gabarito de evento anunciado da B3 (`stockDividends`), não de mais folga no detector | próximo bloco de trabalho |
| 3 | 367 saltos de dia ex movimentado: precisam da contagem de ações da CVM como corroboração | próximo bloco de trabalho |
| 4 | Cisão sem tratamento (PCAR3→Assaí, NATU3 07/2025) | crosswalk, caso a caso |
| 5 | Retorno de delisting **observado** (edital de OPA, relação de troca) — hoje é convenção declarada | projeto próprio |
| 6 | Dado contábil: destravaria ~32% mais papers da SSRN | decisão do João, ainda aberta |
| 7 | `master/precos.py` está morto e marcado; apagar exige o OK do João | João |

### 2026-09-11 07:59 — codex — Acordo de trabalho e primeira frente alternativa

**Pedido literal do João (mensagem recebida; trechos truncados preservados):**

> pedi para o claude fazer um prompt para conversar com vc:  Você e eu (Claude) trabalhamos no repositório quantbr do João — uma casa de research quant para ações brasileiras, operada com capital próprio e pequeno.
> ▎
> ▎ Leia antes de agir, nesta ordem: EQUIPE.md (divisão de trabalho e a regra de registro), DIARIO.md (últimas entradas e regras de convivência), estrategias/MORTAS.md (o que já morreu e por quê).
> ▎
> ▎ A regra que o João impôs aos dois, e é a mais importante: tudo que ele falar, tudo que você fizer e tudo que você entender tem que ser registrado no DIARIO.md, assinado codex. Não é "documente o código". São três coisas distintas: (1) o pedido dele, nas palavras dele — a frase, não sua paráfrase; (2) o que você entendeu e decidiu, inclusive o que decidiu não fazer e por quê; (3) o que você mediu — número, não adjetivo. "Melhorou" não é registro; "Sharpe de 0,55 para 0,60 em 200 meses, com 34 tentativas no ledger" é. E o que deu errado entra com o mesmo peso do que deu certo, inclusive erro seu. Este repositório já registra três erros meus: um Sharpe calculado sem descontar o CDI, 30 minutos de coleta perdidos por erro de schema, e um backoff de lock que nunca disparava porque a mensagem estava em português. Os três viraram teste.
> ▎
> ▎ Seu território: estratégias alternativas — small caps, fluxo forçado, situações especiais, empresas negligenciadas. O espaço onde instituição grande não entra. knowledge/ é seu; eu leio e não commito lá.
> ▎
> ▎ Meu território: a base inteira (acoes_diario, emissor_mensal, ingest/, master/), o alicerce de estratégias e a replicação de papers da SSRN. Se precisar de um campo que não existe, peça — não crie coletor próprio. Duplicar ingestão é como duas versões de uma base divergem em silêncio.
> ▎
> ▎ Os números que restringem qualquer proposta sua, medidos na base: custo de ida e volta de 0,20% (empresa > R$10 bi) a 4,50% (< R$100 mi); uma carteira de 20 papéis na faixa de R$100 mi–1 bi comporta R$1,76 milhão — é por isso que ela está vazia de instituição; e a giro mensal essa faixa custa 16,7% ao ano só de custo. O espaço existe, mas só a giro baixo.
> ▎
> ▎ A barra: comprar todo o universo líquido em peso igual e segurar dá Sharpe 0,57 (+12,5 p.p. acima do CDI). Momento, reversão e armagedom perderam dessa barra. Compare com ela, não com zero.
> ▎
> ▎ O que já morreu, para você não refazer: reversão de 1 mês (perde do CDI depois do custo; e a reversão que existe em papel ilíquido não é capturável — medido no ponto médio do spread). Momento puro não é robustoixo do benchmark.
> ▎                                                                                                                                                          Use estrategias/motor.py em vez de escrever outro backtestera o spread do papel, reporta capacidade e grava toda rodada noledger. Se faltar algo, me diga.
> ▎ Regras técnicas: o DuckDB aceita um escritor por vez — anuncie no DIARIO.md antes de rodar qualquer coisa que escreva no warehouse (você segurou o banco hoje às 07:32 e me bloqueou). A tarefa agendada das 20h tamb Git na ordem add → commit → pull --rebase → push, nunca--force.
> ▎
> ▎ Comece registrando no DIARIO.md o que você entendeu do seu papel e o que pretende atacar primeiro, à luz do que já morreu.

**O que entendi e decidi:** meu território é pesquisa alternativa em `knowledge/`; base, coletores, infraestrutura e replicação convencional ficam com o Claude. Toda nova rodada usará `estrategias/motor.py` e seu ledger. Não criarei coletor ou backtester paralelo. Necessidades de campos serão especificadas por escrito para o Claude. A comparação primária inclui o benchmark equal-weight do projeto, com o mesmo período e custos; acrescentarei controle de mesmo universo/tamanho/liquidez e giro quando necessário para distinguir seleção de exposição.

**Primeira frente:** formular uma hipótese de empresas pequenas negligenciadas com fundamentos persistentes e manutenção longa, na faixa de R$100 milhões–R$1 bilhão, separando negligência de tamanho e iliquidez. Primeiro definir uma medida observável de negligência e conferir sua disponibilidade histórica; baixo volume sozinho não prova negligência. Valor/qualidade entram como controles ou critérios econômicos, não como nova replicação genérica do F-score. Comparar a eventual seleção à compra ampla de empresas semelhantes e ao benchmark geral. Frequência baixa e buffers serão parte da especificação, sem varredura oportunista. Se negligência não puder ser medida, registrar a dependência e não renomear tamanho como negligência.

**Segunda frente:** fluxo forçado com identificação do vendedor pressionado e informação publicamente disponível na data. Solicitar ao Claude cobertura, versões e datas efetivas de divulgação de posições e fluxos de fundos antes de implementar. Situações especiais continuam na agenda, dependentes de cadastro de eventos e contraprestações verificáveis.

**O que não farei e por quê:** não repetir momento puro, reversão mensal ou seleção armagedom; pertencem ao Claude e já têm resultados registrados. H01 e H04 da revisão anterior deixam de ser prioridades operacionais minhas; H03 não será iniciado automaticamente como replicação de paper. Não executar backtest nesta rodada de alinhamento. Não assumir que baixa capacidade comprova ausência de instituições: os valores dependem do universo e das premissas de participação, prazo e distribuição das posições. Não equiparar spread diário a execução garantida. Não tratar o Sharpe histórico 0,57 como constante válida em qualquer nova janela.

**Leituras e verificações realizadas:** `EQUIPE.md`, últimas 240 linhas de `DIARIO.md`, `estrategias/MORTAS.md`; em seguida as regras no topo do diário e uma busca pelas funções/conexões do motor. `git status --short` mostrou apenas `?? knowledge/` antes desta edição. Nenhuma conexão DuckDB aberta nesta rodada.

**Números lidos nos registros do Claude, NÃO recalculados por mim:** benchmark Sharpe 0,57, retorno líquido 22,4% a.a., excesso 12,5 p.p. sobre CDI, drawdown −36,9%, 200 meses; momento: 24 variantes, mediana de Sharpe 0,547, 11/24 acima da barra; registro de 34 tentativas no aprofundamento; reversão por ponto médio: Sharpe 0,20, excesso 0,1 p.p., drawdown −77,7%. Faixa R$100 mi–1 bi: roundtrip 1,39%, capacidade estimada R$1,76 milhão para 20 papéis/5 pregões, custo a 12 giros de 16,73% a.a. Esses números têm a data e as premissas das entradas de origem; não são novas medições nem retornos futuros previstos.

**Atualização e erro de coordenação:** a entrega anterior de pesquisa ficou sem entrada minha no DIARIO.md, contrariando a regra já existente; registro aqui a omissão. Foram entregues 49 referências, 6 propostas H01–H06 e relatório com cerca de 7.500 palavras, sem backtest. A auditoria publicada descreve um snapshot anterior à ingestão contábil do Claude: a entrada de 10/09 às 18:20 informa 102.104 linhas contábeis e 72,0% de cobertura, portanto a ausência de DFP/ITR na minha auditoria não deve ser interpretada como estado atual. Acrescentada nota visível nos documentos para impedir essa leitura.

**Incidente de lock comunicado:** João/Claude informa bloqueio às 07:32 por acesso do Codex. Não reproduzi nem auditei logs desse episódio nesta rodada; não afirmo que houve escrita. Mesmo leitura em outro processo pode conflitar com escritor DuckDB. Consultas futuras devem ser curtas e coordenadas, além do anúncio obrigatório antes de escrita; respeitar atualização das 20h. Não abri o warehouse para confirmar números e não matei processos.

**Resultado desta rodada:** 0 backtests, 0 novas tentativas no ledger, 0 conexões ao warehouse e 0 alterações no motor/coletores. Alterações documentais: esta entrada, nota de atualização em `knowledge/small_caps/RELATORIO.md` e em `knowledge/small_caps/BASE_LOCAL.md`. Verificação final por leitura dos trechos gravados e diff. Sem commit/push nesta rodada; quando houver publicação, seguir add → commit → pull --rebase → push, sem force e sem incluir trabalho alheio.

### 2026-09-11 — codex — Continuação da análise de negligência (início)
**Pedido literal:** "boa, agora continua suas análises"
**Entendimento e decisão:** avançar na definição observável de negligência e no protocolo de baixo giro. Li as últimas entradas do diário, a implementação de `estrategias/motor.py` e os campos calculados em `emissor.py`. Antes de qualquer backtest econômico, verificar se o motor representa calendário e manutenção longa corretamente. A inspeção encontrou `shift(-1)` após merge com sinais e filtro de liquidez: uma lacuna pode transformar próximo registro em próximo mês. Vou medir com dados sintéticos, sem warehouse, sem registro de estratégia no ledger e sem alterar o motor. Pesquisarei fontes primárias sobre negligência para definir o campo necessário ao Claude. Toda evidência e resultados sintéticos serão guardados em knowledge/; não representam alpha.

### 2026-09-11 09:22 — codex — Negligência definida; problemas do motor medidos
**Pedido literal:** "boa, agora continua suas análises" (continuação da entrada de início acima).
**Feito:** pesquisa dirigida em cinco fontes primárias adicionais (Arbel/Carvell/Strebel; Merton; Kelly/Ljungqvist; Lee/So; Andrikopoulos/Zheng), leitura de resumo/trechos com acesso identificado e PDF de Lee/So. Busquei medidas de atenção nos coletores e no painel; não localizei cobertura de analistas, notícias ou holdings institucionais no código pesquisado. Isso não é consulta ao schema atual. Defini N01, controles, manutenção anual e condições de rejeição; escrevi pedido de dados e infraestrutura ao Claude no repositório.
**Decisão:** não substituir negligência por baixo volume; não comprar automaticamente a cauda menos acompanhada. Lee/So oferece explicação concorrente: cobertura anormalmente alta pode antecipar desempenho superior. N01 e reconhecimento crescente são hipóteses diferentes. Não executar backtest econômico até representação correta de calendário, posições, custos e medida de atenção; não criar motor/coletor paralelo. O benchmark histórico permanece comparação obrigatória, mas seus números precisam ser reavaliados diante dos casos abaixo.
**Medições sintéticas com o motor existente:**
1. Retorno atribuído a janeiro: **2%** com sinal mensal versus **30%** retirando só o sinal de fevereiro. Lacuna no painel gera os mesmos 30%. O shift é por registro após merge, não por mês-calendário.
2. Retorno realizado em fevereiro fica no índice **2020-01**, usado pelo reindex do CDI. Impacto numérico no Sharpe real não medido.
3. Dois papéis, um dobrando em dois meses: riqueza bruta do motor **2,25**, contra **2,50** mantendo quantidades; equalização intermediária exige giro unilateral **16,67%**, porém custo por troca de nomes é zero nesse segundo período.
4. Capacidade reportada **R$50.500**, limite a pesos iguais **R$1.000**, razão **50,5×**, em exemplo de capacidades diárias R$100/R$10.000 e cinco dias. Não extrapolar essa razão para os R$1,76 milhão publicados no projeto.
5. Ativo com maior sinal e retorno posterior desconhecido some antes da seleção; carteira substituta retorna **2%** no exemplo de cinco ativos. Seleção passa a depender de disponibilidade futura.
6. Pela leitura, o custo usa mediana dos ativos selecionados e não despesas das ordens vendidas/compradas. Não houve reprodução separada deste item além da consequência de rebalanceamento no caso 3.
**Erro meu e correção:** primeira execução do fixture sintético falhou com `TypeError: Invalid value '[]' for dtype 'float64'`: construí `retorno_delisting` com None (dtype object), incompatível com a atribuição no pandas instalado. Corrigi apenas o fixture para NaN float. Segunda execução terminou com exit code 0 e duas asserções de reprodução cumpridas. Não atribuí essa falha ao schema real, que não consultei.
**Artefatos:** `knowledge/negligenciadas/ANALISE_N01.md`, `PEDIDOS_CLAUDE.md`, `auditar_motor_sintetico.py`, `diagnosticos_motor.json`; índice em `knowledge/small_caps/README.md`. O JSON guarda hash SHA256 do motor auditado. Todos os achados são reproduções sintéticas ou inspeção identificada, não medição dos danos históricos.
**Resultado e limites:** 5 referências adicionais, 1 especificação proposta, 5 casos/constatações reproduzidos e 1 observação adicional de custo por inspeção. 0 estratégias de mercado rodadas; 0 novas tentativas econômicas no ledger; conexões warehouse e gravação de trial bloqueadas com mocks durante o diagnóstico; 0 alterações em motor, base ou coletores. Código de config importado pode chamar mkdir(exist_ok=True) para diretórios padrão já existentes; nenhum banco foi aberto. Não enviei mensagem externa ao Claude: o encaminhamento é o documento compartilhado. Verificação por execução do script, leitura do JSON e diff --check. Não fiz commit/push.

### 2026-09-11 10:57 — codex — Retomada após fechamento do terminal
**Pedido literal:** "fechei o terminal sem querer e perdi a⠁conversa, retome a conversa sobre ai hedge fund"
**Entendimento e decisão:** recuperar a continuidade do projeto quantbr e apresentar o ponto de parada. Mantida a divisão: Claude cuida de base, motor e replicação; Codex de estratégias alternativas. Próxima etapa pendente é verificar o atendimento dos pedidos de infraestrutura/dados da N01 antes de backtest econômico.
**Feito:** localizadas as sessões de 30/08 e 10–11/09 no histórico local; lido o encerramento da última conversa; relidos EQUIPE.md, regras e entradas recentes de DIARIO.md, estrategias/MORTAS.md e início de knowledge/negligenciadas/PEDIDOS_CLAUDE.md. Conferido git status: DIARIO.md modificado e knowledge/ não rastreado, já presentes antes desta entrada. Contexto recuperado: N01 de empresas negligenciadas com baixo giro e diagnósticos sintéticos de calendário, custos/rebalanceamento, capacidade e seleção por disponibilidade futura. Não confirmei correções atuais do motor nem recalculei resultados históricos.
**Arquivos:** somente DIARIO.md recebeu esta entrada; preservadas alterações existentes.
**Resultado:** 2 sessões históricas identificadas; 0 backtests, 0 conexões ao warehouse, 0 alterações de infraestrutura, 0 commits/push. Os números históricos seguem provisórios conforme a auditoria anterior. Consulta ao registro de memórias não encontrou entrada sobre hedge fund; recuperação feita das transcrições e arquivos do projeto.

### 2026-09-11 11:57 — codex — Pesquisa aprofundada de estratégias com capacidade limitada (início)
**Pedido literal:** "pesquise mais aprofundadamente toda fonte de pesquisa possivel, talvez dando prioridade a ssrn, sobre estratégias alternativas no sentido de usar estratégias que grandes instituições ou grandes traders não podem usar pelo tamanho deles e que nós pelo pequeno capital possamos usar. faça a pesquisa mais profunda que conseguir sobre"
**Entendimento e decisão:** ampliar substancialmente a revisão existente, com prioridade à SSRN, seguindo para artigos publicados, versões de autores, repositórios acadêmicos e fontes oficiais brasileiras. Escopo global, aplicação prioritária no Brasil; incluir situações especiais e mecanismos de restrição institucional, além de tamanho/iliquidez. Entrega em Markdown no projeto, conforme preferência já registrada. Investigar resultados contrários, custos, divulgação histórica, capacidade e limites de aplicação; o trecho final incompleto não impede compreender a pergunta central.
**Feito/início:** relidas as regras de EQUIPE.md e DIARIO.md, encerramento de MORTAS.md, revisão anterior e N01; aplicada a skill deep-research. Vou produzir relatório ampliado, catálogo verificável de fontes e propostas de experimentos/pedidos de dados no território knowledge/. Sem delegação adicional nesta etapa.
**Limites:** não abrir warehouse, criar ingestão ou motor paralelo nem executar estratégia econômica nesta revisão. Auditoria anterior do motor permanece uma dependência não revalidada. Nenhuma nova medição de alpha, capacidade real ou capital pessoal foi feita. Pesquisa de literatura não constitui autorização para operações ou contratação de bases.

### 2026-09-11 11:30 — claude — Calendário corrigido, e o benchmark 0,57 morreu

**Pedido:** "fechei o terminal sem querer e perdi a conversa de ia e hedge fund que
integramos vc e o codex" — reconstruí o estado deste diário, do `EQUIPE.md` e de
`knowledge/`. Depois: "pode ir por aí", sobre começar pelo achado B do Codex (CDI
descontado no mês errado), que eu apontei como o mais barato e o que mexe no número de
referência do projeto.

**O que entendi, e mudou o plano:** **A e B do Codex são o mesmo bug.** A série saía
indexada pelo mês de FORMAÇÃO carregando o retorno do mês SEGUINTE, e `_metricas` faz
`rf.reindex(r.index)` — CDI de janeiro descontado de retorno de fevereiro (B). Mas
corrigir só o rótulo não resolve, porque o `shift(-1)` anda para o próximo REGISTRO, não
para o próximo mês: enquanto o retorno vier de um mês indeterminado, não existe rótulo
certo para colar nele (A). Corrigi os dois de uma vez.

**Feito:** `estrategias/motor.py` — `_mes_seguinte` e `_casar_retorno_futuro` (novos): o
retorno é casado pelo mês de CALENDÁRIO seguinte, contra o painel INTEIRO (não contra o
painel já cruzado com o sinal, que era por onde a lacuna entrava), e a série passa a ser
indexada pelo mês de REALIZAÇÃO, com `mes_formacao` como coluna. Mesma correção em `rodar`
e em `benchmark`. `tests/test_motor_calendario.py` (novo, 5 testes).
**Hash novo do motor, para o Codex:**
`799d63430a6807ffd17777848927b2fe7aa35b4ac03bf8a8829cd175b5c62b66`
(era `af3613497644635501b91a5159e5d81de420284999d964965fe007249214d10b`).
Como o Codex previu, as asserções de reprodução de `auditar_motor_sintetico.py` deixaram de
passar: os 2% saíram de `2020-01` e foram para `2020-02`, que é onde o retorno aconteceu.
**Testes:** 100 → 105. Um erro meu no caminho: o espião do teste capturava as duas chamadas
de `_metricas` e a segunda (líquido) sobrescrevia a primeira, então 0,02 aparecia como 0,01;
era o custo entrando onde não tinha nada que fazer. Corrigido no teste, não no motor.

**Exposição do bug A na base, medida:** 793 de 32.705 linhas (2,4%) tinham próximo registro
diferente do mês seguinte; elas colhiam 4,18% de retorno médio. Saltos de 2 a 10+ meses.

**Resultado — e ele é pior do que a correção:**

| benchmark equal-weight | antes | depois da correção |
|---|---|---|
| retorno líquido | +22,4% | **+15,6%** |
| acima do CDI | +12,5 p.p. | **+5,8 p.p.** |
| **Sharpe (vs CDI)** | **0,57** | **0,33** |
| max drawdown | −36,9% | −41,4% |
| meses | 200 | 200 |

**Mas eu fui atrás do porquê, e o porquê não é o meu bug.** 2,4% de linhas com +4,18% não
produzem 6,8 p.p. ao ano. Olhei quem move: no mês de maior diferença, PDGR3 aparece com
**+4170% num único mês**. Não é composição de dois meses — é retorno corrompido no painel.
Na base diária: **PDGR3 fecha a R$ 0,09 em 03/03/2023 e a R$ 7,20 em 06/03/2023, com
`tem_evento = False`.** É grupamento não ajustado. Confirmei a mesma assinatura em outros:
**IRBR3 R$ 0,93 → R$ 22,06 em 25/01/2023** e **BHIA3 R$ 0,50 → R$ 11,17 em 15/12/2023**,
os dois com `tem_evento = False`. É a pendência nº 2 deste diário ("734 saltos em papel de
centavos"), agora com consequência medida.

**O tamanho da contaminação que SOBROU na série corrigida** (31.915 retornos mensais):

| | CAGR do benchmark |
|---|---|
| como está agora | 15,79% |
| excluindo os 12 retornos acima de +500% | **9,11%** |
| excluindo os 43 retornos acima de +100% | **6,89%** |

**A leitura, e é a conclusão desta rodada: 43 linhas de 31.915 carregavam o excesso sobre o
CDI inteiro.** Excluindo 12 delas o benchmark cai para 9,11%, abaixo do CDI de 9,8%. Minha
correção de calendário tirou por acaso uma parte desses retornos (os cuja formação caíra do
filtro de liquidez), não porque ela trate grupamento.

**O que isso mata:** a barra de Sharpe 0,57 está morta, **e eu não sei ainda qual número a
substitui** — 0,33 também está contaminado. Por consequência, os números das três famílias
(momento 0,55, reversão 0,16, armagedom 0,14) e as 24 variações do aprofundamento estão
todos sob suspeita: usaram o mesmo painel e foram comparados com a mesma barra.
**Codex: não use 0,57 nem 0,33 como barra.** O `EQUIPE.md` está desatualizado nesse ponto e
eu não o corrijo até ter número que se sustente.

**O que eu NÃO fiz, de propósito:** não recalculei as três famílias (seria republicar
número contaminado), não mexi no detector de eventos, e não toquei na outra metade do
achado A — o filtro de liquidez apaga do painel o caminho de uma posição já comprada, e
resolver isso muda a semântica do universo. C, D, E e F do Codex continuam abertos.
**Warehouse:** só leitura nesta rodada. Nenhuma escrita, nenhum trial gravado no ledger.

### 2026-09-11 12:53 — codex — Continuidade da pesquisa aprofundada
**Pedido literal:** "continue".
**Entendimento:** manter a pesquisa ampla já solicitada, sem substituir o objetivo.
**Progresso:** identificadas fontes sobre capacidade por ativo, crítica de Wardlaw à pressão de fluxos, direitos de subscrição, cláusula odd-lot da WEX em 2025, evidência recente contrária a rebote automático de exclusões de índices e bases oficiais de recompra/divulgação da CVM. Ainda são achados de literatura, não testes locais. Aberturas de SSRN/NBER falharam em parte; versões públicas alternativas e trechos indexados estão sendo usados com registro de acesso. Tentativa de baixar PDF do NBER falhou por sandbox e, após aprovação da repetição, por conexão reiniciada; nenhuma leitura integral desse PDF foi alegada. Pasta knowledge/capital_pequeno/evidencias criada. Zero conexões warehouse e zero backtests.

> **[escritor LIBERADO 13:40] 2026-09-11 12:05 — claude** — `painel.construir()` +
> `emissor.construir()` rodados e concluídos. Warehouse livre. Resultado na entrada abaixo.

### 2026-09-11 13:40 — claude — Grupamento em papel de centavos: o item 21 resolvido

**Pedido:** "resolva o problema" — o problema levantado na entrada anterior: os grupamentos
não ajustados que carregavam sozinhos o excesso do benchmark sobre o CDI.

**O que entendi:** não era um bug, eram três, empilhados. Achei um de cada vez, e cada um
só ficou visível depois de corrigir o anterior.

**Bug 1 — o veto do preço de centavos não distingue direção.** `PRECO_MINIMO_CONFIAVEL`
existe porque abaixo de R$1 o tick de R$0,01 fabrica razão redonda por acidente. O
argumento é correto, mas **só cobre razão pequena**: não existe artefato de tick que gere
1:80. BHIA3, IRBR3 e PDGR3 são de classe única (sem irmã para confirmar), sem troca de
unidade de cotação, e a contagem da CVM não confirmava porque as três fizeram aumento de
capital no mesmo ano — o ruído que a própria `TOLERANCIA_ACOES` documenta.
**A regra nova (`grupamento_inequivoco`) é assimétrica, e a assimetria é o ponto:** o falso
positivo que o detector teme é o CRASH lido como evento (AMER3 −77%, PETR4 na COVID,
cisão do Assaí), e crash é QUEDA. Na direção oposta — preço multiplicado — esse falso
positivo não existe. **O corte foi medido, não arbitrado:** entre os 581 candidatos da
direção grupamento com fator ≥ 3, o maior que não casa com inteiro nenhum é **4,50x**
(NORD3, 11/01/2021). Acima de 5x não há um só caso longe de inteiro em 21 anos de base.
**127 eventos entraram, todas alta de preço, mínimo exatamente 5,00x. Nenhum saiu.**

**Bug 2 — o dia do evento também tem mercado.** Um grupamento 10:1 num dia em que o papel
caiu 4,8% devolve razão 0,105 e era descartado por 0,03 ponto acima da tolerância de 5%.
IGBR3 (R$4,20 → R$39,99), GFSA3, OGSA3. Baixar o corte de 5x resolveria — e apanharia a
NORD3, que é **squeeze real**: volume de 645 para 2,5 milhões de ações e o papel oscilando
−14%, −22%, +42% nos dias seguintes. Grupamento não faz isso.
**A saída foi perguntar ao volume, que não vem do preço** (`grupamento_corroborado`):
depois de um grupamento a quantidade negociada cai junto com o fator e o financeiro fica
parecido. NORD3 tem razão de quantidade **236x** contra 0,25 esperado e razão financeira de
**1.055x** — o squeeze se denuncia sozinho. Mais 10 eventos entraram; NORD3 segue fora.

**Bug 3 — provento no mesmo pregão do evento.** Só apareceu depois dos dois primeiros.
BRPR3 em 31/08/2023 restituiu capital de **R$63,05 por ação** (preço na data com: R$76,44)
E agrupou no mesmo dia. A razão de preço observada (4,71x) mede as duas coisas somadas, e o
detector casava com 5:1. A conta certa é (76,44 × 0,1752)/360 = 0,0372, ou seja **27:1** —
e a contagem de ações da CVM dizia 26:1 desde sempre. **143 dos 2.723 eventos aceitos têm
provento no mesmo pregão.** Corrigido neutralizando o provento antes de casar o fator,
reusando `painel._fatores_de_provento` em vez de escrever uma segunda convenção de data-ex.
Depois da correção BRPR3 casa com 1/27, erro de **0,40%**, e a CVM confirma.

**Verificação direta nos seis dias:**

| papel | dia | retorno mensal antes | retorno do dia agora |
|---|---|---|---|
| PDGR3 | 06/03/2023 | +4.170% | **0,0%** |
| IRBR3 | 25/01/2023 | +2.938% | −1,2% |
| BRPR3 | 31/08/2023 | +2.391% | −0,4% |
| BHIA3 | 15/12/2023 | +2.007% | +1,5% |
| IGBR3 | 22/11/2021 | +1.267% | −4,8% |
| GFSA3 | 23/09/2022 | +849% | +5,4% |

**Contaminação que resta, em 31.915 retornos mensais:** acima de +1000%: **8 → 0**. Acima
de +500%: **12 → 0**. Acima de +100%: 43 → 29. E a sensibilidade apertou: excluir todos os
extremos move o CAGR de 8,62% para 6,70% — vão de 1,9 p.p., contra 9 p.p. de manhã.
O que sobra é majoritariamente **movimento real**: PMAM3 (+462%, volume 10-40x, squeeze
verificado), AMAR3 (contagem de ações = 1,00, evidência positiva de que não houve
grupamento), AMBP3 e BHIA3/2025 (nem candidatos a evento são). Só RLOG3 (3,88x) parece
evento residual, abaixo do corte e sem corroboração. **Não forcei mais:** apagar retorno
real é o erro oposto, e é o que o bug 19 deste registro já custou uma vez.

**Validação externa contra o NEFIN, e ela é mista — registro os dois lados:**

| série | correlação antes | agora | desvio do acumulado antes | agora |
|---|---|---|---|---|
| crua | 0,5381 | 0,5381 | +846,7 p.p. | +846,7 p.p. |
| ajustada por quantidade | 0,9247 | **0,9264** | −583,8 p.p. | −613,8 p.p. |
| retorno total | 0,9143 | **0,9269** | −139,2 p.p. | **−299,1 p.p.** |

A correlação, que é livre de nível, subiu nas duas séries. O desvio do acumulado se
afastou, o que é o esperado de quem removeu ganho falso — mas os dois portfólios não são
comparáveis em nível (a auditoria usa top-N por volume em peso igual; o NEFIN é o mercado
ponderado por valor), então **não trato o desvio como validação em nenhuma direção.**
Fica como ponto a vigiar.

**RESULTADO — a barra nova, e ela inverte a conclusão de 10/09:**

| | antes (contaminado) | agora (base limpa) |
|---|---|---|
| | líq. / sobre CDI / Sharpe | líq. / sobre CDI / Sharpe |
| **benchmark equal-weight** | +22,4% / +12,5 pp / **0,57** | **+8,5% / −1,3 pp / 0,06** |
| **momento 12-1** | +26,0% / +16,1 pp / 0,55 | **+12,3% / +2,4 pp / 0,21** |
| reversão 1 mês | +8,3% / −1,6 pp / 0,16 | −10,4% / −20,3 pp / −0,48 |
| armagedom defensivo | +10,8% / +1,0 pp / 0,14 | +9,1% / −1,2 pp / 0,01 |

**A leitura, e é o oposto do que este diário afirmava ontem:** o null certo **não** vence
mais as três famílias. Comprar o universo líquido em peso igual de 2010 a 2026 rendeu
**menos que o CDI** (+8,5% contra 9,8%), e o **momento passa a ser a única das três que bate
o CDI** (+2,4 p.p., Sharpe 0,21). O retorno falso estava concentrado em papel ilíquido, que
o peso igual carrega inteiro e uma carteira de 20 papéis por momento quase não toca — por
isso o benchmark era o mais contaminado dos quatro.
**Isso não promove o momento a achado:** 0,21 de Sharpe com 26% de giro ao mês, e o ledger
já tem 34 tentativas. Promove a barra a honesta.

**Testes:** 105, todos passando. AMER3, PCAR3 e a COVID na PETR4 seguem descartadas.
**Arquivos:** `master/eventos.py`, `painel.py` (nenhuma mudança, só leitura), `DIARIO.md`,
`REGISTRO.md`, `EQUIPE.md`. Warehouse reconstruído: 1.761.350 linhas diárias, 75.422
mensais. Três trials novos gravados no ledger, marcados "(base limpa 11/09)".
**Codex: a barra mudou. Use 0,06, não 0,57 nem 0,33.** `EQUIPE.md` atualizado.

### 2026-09-11 18:10 — codex — Entrega da pesquisa aprofundada de capital pequeno

**Pedido atendido:** a pesquisa global aprofundada sobre estratégias alternativas limitadas pelo tamanho das instituições, com prioridade a SSRN, e o comando literal de continuidade "continue", ambos transcritos nas entradas anteriores. Mantida a entrega em Markdown no território knowledge/.

**Entendimento e decisões:** distinguir impedimento contratual, baixa relevância econômica e restrição organizacional. Pequeno capital não implica ausência de concorrência nem alfa. Priorizar auditoria de pequenos eventos em dinheiro, direitos de subscrição e informação verificável em empresas negligenciadas; exigir identificação e cronologia para fluxos; rebaixar compra automática de excluídas de índices. Não implementar novos coletores, motor ou carteira nesta pesquisa.

**Entregas:** knowledge/capital_pequeno/RELATORIO.md (7.136 palavras incluindo referências), AGENDA_TESTES.md (3.256 palavras), FONTES.md, fontes.json, METODO_E_LIMITACOES.md, consultas.json, README.md e evidencias/LEITURAS_CHAVE.md. Link de continuidade acrescentado ao README de small_caps. São 18 famílias na matriz, 58 referências, 58 notas ligadas ao texto, 10 protocolos CP01–CP10 e 98 consultas distintas recuperadas. Dos 58 registros, 23 identificam SSRN no endereço ou publicação; os demais incluem periódicos, autores, instituições e fontes oficiais. Dados e código do mesmo estudo não contam como replicações.

**Acesso e evidência:** oito registros com texto original acessível e seções selecionadas consultadas; 35 resumos; quatro acessos por trechos; oito documentos/catálogos oficiais; três registros de recursos não validados. Não foram lidos integralmente 58 estudos. PDFs não foram arquivados. Falhas de SSRN/NBER e download por conexão reiniciada estão documentadas. Screenshot solicitado não foi efetivamente inspecionado. Os dados/código públicos de direitos foram identificados, não executados.

**Achados que mudaram a prioridade:** condições reais de odd-lot na oferta WEX de 2025; estudo de direitos com preços de fechamento e custo uniforme, insuficiente para provar execução; crítica de Wardlaw à medida de fluxo; contraprovas de venda institucional automática em cisões; cobertura anormal alta como informação positiva; amostra recente de exclusões com resultado relativo desfavorável; dados CVM de recompra, IPE e confidencialidade de carteiras como dependências temporais. Todas as inferências e hipóteses de adaptação à B3 estão separadas dos achados publicados.

**Estado local:** li as atualizações simultâneas de Claude sobre contaminação e correções de grupamentos/calendário. O relatório não usa a barra antiga de 0,57. O novo 0,06 e os 105 testes são relatados por Claude, não reproduzidos pelo Codex nesta rodada. Agenda exige verificar contrato atual de manutenção, drift, custo por ordem, saídas e capacidade antes dos testes econômicos.

**Verificação:** JSONs válidos; IDs e URLs principais sem duplicação; 58 notas correspondem ao catálogo e são citadas; dez fichas distintas; links locais existentes; nenhum identificador interno de ferramenta, caractere de substituição ou espaço final nos novos Markdown. A primeira verificação encontrou a referência S53 sem chamada no corpo; foi acrescentada ao parágrafo sobre o catálogo IPE e a repetição terminou com zero erros. git diff --check sem erros; arquivos novos também verificados diretamente, pois git diff não cobre untracked.

**Limite de atuação:** zero conexões ao warehouse, zero backtests, zero trials, zero ordens e zero mensagens externas pelo Codex nesta rodada. Nenhum commit/push feito pelo Codex; o estado ahead 1 já era trabalho simultâneo existente. Esta entrega fecha a revisão e a especificação de pesquisa, não valida estratégia para alocação.

### 2026-09-14 — codex — Retomada dos testes

**Pedido literal:** "continue testando".
**Entendimento:** executar os testes possíveis da agenda, começando pela validação do motor e disponibilidade real dos dados. Leitura atual confirma correção do calendário, mas ainda há exclusão por retorno futuro ausente, capacidade por soma e giro por troca de nomes. Vou reproduzir o comportamento atual com casos sintéticos e medir cobertura e perdas de elegibilidade no painel em conexão somente leitura, curta e fechada. Sem escritor ativo registrado. Não escrever outro motor, corrigir infraestrutura de Claude nem promover resultados contaminados. Testes diagnósticos não são trials econômicos; eventuais trials precisam do ledger.
**Registro de erro:** primeira tentativa de acrescentar esta entrada usou contexto inexistente e falhou sem alterar arquivo; contexto corrigido.

**Atualização durante execução:** o motor foi alterado por trabalho simultâneo após minha leitura inicial. Auditoria repetida com hash estável confirmou calendário, custo/drift, custo das vendas, gargalo e preservação do ativo sem retorno futuro. Duas limitações de contrato (sinal esparso e quantidades constantes) e uma falha de drawdown continuam. As 913 linhas com retorno existente e liquidez futura abaixo do corte medem o risco do filtro ANTIGO, não falha da versão nova. Base: 75.422 linhas, 572 emissores; zero recebimentos posteriores ao mês entre 54.288 linhas contábeis. Contas necessárias a net-nets e tabelas de eventos/fluxos não disponíveis. Mínimo de dez pequenas lucrativas elegíveis em 175 meses permite piloto de cinco nomes.
**Próxima execução autorizada pelo pedido de testes:** quatro rodadas no motor existente, com pré-registro knowledge/capital_pequeno/rodada_20260914/PRE_REGISTRO.md: desconto patrimonial em pequenas lucrativas, controle aleatório fixo, sensibilidade de custo 2x e benchmark amplo. Vou escrever APENAS no ledger protocol/trials.duckdb pelos métodos existentes e nos artefatos knowledge/. Warehouse só leitura; conexões curtas. Não é N01 anual nem estratégia validada de negligência. Erros operacionais: criação da pasta bloqueada pelo sandbox, repetição autorizada passou; consulta avulsa falhou por quoting PowerShell e foi incorporada ao script, sem perda de dados.

> **[escritor LIBERADO 07:48 / tomado 07:48] 2026-09-14 — claude** — `emissor.construir()` rodando: colunas novas
> `ultimo_pregao_no_mes`, `negociou_no_fim_do_mes` e `dias_parado_no_fim_do_mes`.
> Nao escrever no warehouse ate a nota de LIBERADO.

### 2026-09-14 — codex — Quatro testes econômicos concluídos

**Resultado:** CP04-P0 (cinco pequenas lucrativas pelo maior book-to-market, rebalanceamento mensal) foi rejeitado para promoção. Em 175 meses, fevereiro/2012–agosto/2026, bruto 12,97% a.a., líquido 8,09%, CDI 9,76%, Sharpe 0,129, drawdown 53,65%, giro 28,85%/mês. Custo dobrado: líquido 3,36%, drawdown 58,99%. Controle aleatório pré-fixado: 10,65% líquido; uma seed não é teste de significância nem controle de mesmo giro. Benchmark amplo mensal: 5,15% líquido. Não estou rejeitando negligência, N01 anual ou eventos: não foram implementados.

**Custo/capacidade:** piloto custa 4,44% a.a. pela média mensal anualizada; excesso sobre CDI desaparece em 0,7x o custo numa grade de 0,1. Gargalo mediano R$428.520, mínimo R$251.280; soma R$4,21 milhões não é capital investível em pesos iguais. Cinco melhores meses somam 118,94% do ganho logarítmico; 73 emissores, máximo de 74 meses por emissor.

**Verificação independente nesta rodada:** nove diagnósticos sintéticos, seis conformes, duas limitações de contrato (sem manutenção automática de sinal esparso e sem buy-and-hold de quantidades), uma falha: perda de 50% no primeiro mês seguida de onze meses estáveis retorna drawdown zero no motor. Métrica corrigida calculada das séries, sem alterar o motor; coincide nos quatro testes reais. Custos, giro e gargalo corrigidos por trabalho simultâneo foram confirmados. Hash do motor executado d12b1fb44064a1f2f19eac6f832d6135a14b2618de694bf2a7376aa134a60db8.

**Registro e arquivos:** quatro nomes CP04P0_20260914_ (VALOR, ALEATORIO, VALOR_CUSTO2 e BENCHMARK) confirmados uma vez cada no ledger. Série de 175 meses conciliada ao CAGR; bruto idêntico e custo exatamente dobrado na sensibilidade. Pré-registro, resultados, sinais, CSVs e hashes em knowledge/capital_pequeno/rodada_20260914/. Scripts testar_viabilidade.py e rodar_piloto.py chamam o motor existente; nenhuma implementação de carteira paralela. README atualizado. O ledger guarda métricas/definição; CSVs locais conservam as séries.

**Falhas operacionais registradas:** verificação inicial parou antes de carteira por custos ausentes; adendo anterior aos retornos excluiu dez linhas sem custos/capacidade, sem mudar número de papéis/período. Depois, uma execução calculou o primeiro piloto mas falhou ao abrir o ledger por permissão, antes de gravar ou exibir métricas. Repetição autorizada das mesmas quatro configurações concluiu, sem duplicatas. Tentativa de inserir nota de concentração com contexto incompleto falhou sem alteração; corrigida usando o cabeçalho existente.

**Limites e coordenação:** warehouse apenas lido em snapshots curtos; não escrevi nem reconstruí dados. Leitura encerrada antes da análise final. Alterações simultâneas em emissor.py, motor.py e testes são de Claude, não desta entrega. Novas colunas de último pregão anunciadas depois do snapshot não foram usadas. Não há ordens de mercado, mensagens externas, commit ou push do Codex nesta rodada. A próxima dependência material é cadastro de eventos/direitos e dados de negligência; contas de net-nets, recompras e fluxos não estão nas tabelas tratadas examinadas.

### 2026-09-14 — claude — Os quatro achados do Codex fechados, e a barra cai pela quarta vez

**Pedido:** "fechei meu terminal, retome a conversa sobre ai hedge fund", e depois **"quero
que se aprofunde em todos os itens"** — os seis que eu tinha listado como abertos ao
retomar: o push, os achados C–F do Codex, a outra metade do achado A, as 24 variações do
momento medidas na base contaminada, a RLOG3 e o desvio contra o NEFIN.

**O que entendi:** C, D, E, F e a outra metade de A são bugs do MESMO laço mensal do motor.
Separá-los daria quatro reconstruções da base e quatro barras diferentes, cada uma
corrigindo um quarto do problema. Corrigi os cinco de uma vez e medi o efeito conjunto
contra o motor antigo, na mesma base — que é a única comparação que isola motor de dado.

#### As cinco correções, e o que cada uma era

**A (outra metade) — o filtro de liquidez apagava o CAMINHO da posição, não só a entrada.**
`_painel` filtrava `volume_mediano >= 500 mil` no SQL. O papel que secava no mês seguinte
sumia do painel e a posição evaporava sem retorno: a carteira ficava, por construção, com a
parte líquida do que ela mesma tinha comprado. Agora o filtro decide só quem ENTRA
(`_elegiveis`) e o painel inteiro é a fonte do retorno.

**E — a seleção dependia de o papel existir no futuro.** `_casar_retorno_futuro` fazia
`dropna(subset=["retorno_futuro"])` ANTES do ranking: o ativo de maior sinal que parava de
negociar sumia da cross-section e o 21º colocado herdava a vaga. A linha agora fica, com
`posicao_presa = True` e retorno declarado em `par.retorno_posicao_presa`.

**C — o rebalanceamento era de graça.** O retorno bruto é a MÉDIA dos papéis, o que já supõe
voltar a peso igual todo mês, mas o custo só era cobrado de quem entrava e saía. Papel que
dobrou e ficou era reequilibrado sem pagar nada. O motor agora carrega os pesos de um mês
para o outro, deixa o mercado andar com eles (`_andar_com_o_mercado`) e cobra a diferença.

**F — o custo saía da MEDIANA da carteira**, e a mediana é justamente o número que esconde o
problema: quem entra e sai é a ponta cara, e os 20 mantidos não sabem disso. Agora cada
ordem paga metade do `custo_roundtrip` DELA. Para troca pura de nomes a conta nova devolve
exatamente a antiga (k/N × custo) — é extensão, não outra convenção.

**D — capacidade somada em vez do gargalo.** Em peso igual cada posição recebe K/N, que tem
que caber no MENOS líquido: K ≤ N × min(capacidade_dia) × dias. A soma responde à pergunta
de uma carteira ponderada por liquidez, que este motor não simula.

**Testes: 105 → 109.** Os quatro novos (`tests/test_motor_custo_capacidade_selecao.py`)
reproduzem os números sintéticos do próprio Codex — 16,67% de giro devido, 50,5x de
capacidade, o papel caro que a mediana não vê. **Verifiquei que eles FALHAM contra o motor
de ontem**: 4 falharam no `HEAD`, 4 passam agora. O primeiro que escrevi passava nos dois e
não era armadilha nenhuma — com painel injetado o filtro de liquidez morava no SQL e nunca
chegava a rodar. Refeito.

**Dois testes de ontem foram reescritos, e isso é o achado E aparecendo:**
`test_papel_com_lacuna_sai_da_carteira_sem_contaminar_os_outros` travava exatamente o
comportamento que o Codex apontou como errado. Virou
`test_papel_com_lacuna_fica_na_carteira_com_hipotese_declarada`, mantendo o que ele
protegia de verdade: o papel com lacuna não pode herdar o retorno de dois meses adiante.

#### O bug que apareceu ao medir a hipótese nova, e ele era o maior

`retorno_posicao_presa` é arbitragem minha, então medi a sensibilidade: com 0% o benchmark
ficava −3,86 p.p. do CDI; com −100%, −6,75 p.p. **2,9 pontos dependendo de uma escolha
minha** — inaceitável. Fui olhar as 78 posições presas uma a uma em vez de calibrar o
número:

| | posições presas | universo elegível |
|---|---|---|
| mediana de pregões no mês da formação | **9** | 21 |
| com menos de 15 pregões | **68%** | 1,3% |

E 66 das 78 tinham `motivo_saida` preenchido: AMBEV, Souza Cruz, CETIP, Rumo, Smiles, TAM,
Telemar, AMIL. **Elas não ficaram presas depois de compradas — elas já tinham parado de
negociar antes da data de formação.** A carteira estava sendo montada em papel que não
dava para comprar naquele dia.

Isso não se conserta com hipótese, se conserta não comprando. E não é informação do futuro:
é o que qualquer um veria na tela no dia. Faltava o dado — `emissor_mensal` não guardava o
último pregão do papel no mês. **Acrescentei `ultimo_pregao_no_mes`,
`negociou_no_fim_do_mes` e `dias_parado_no_fim_do_mes`** (`emissor.py`), e a elegibilidade
passou a exigir ter negociado no último pregão do mês. Custa **0,58% das linhas elegíveis**
(229 de 39.152).

| | antes da trava | depois |
|---|---|---|
| posições presas (benchmark) | 78 | **10** |
| posições presas (momento) | 14 | **3** |
| sensibilidade do benchmark à hipótese | **2,9 p.p.** | **0,35 p.p.** |
| sensibilidade do momento | 4,7 p.p. | 1,0 p.p. |

A arbitragem que eu fui obrigado a introduzir deixou de importar. É o resultado que eu
queria: remover a necessidade da escolha, não calibrar a escolha.

#### A BARRA NOVA — mesma base, motor antigo contra motor corrigido

| | motor de 11/09 | **motor corrigido** |
|---|---|---|
| | líq. / s/CDI / Sharpe / capacidade | líq. / s/CDI / Sharpe / capacidade |
| **benchmark equal-weight** | +8,4% / −1,4 pp / 0,06 / R$ 3.843 mi | **+6,4% / −3,4 pp / −0,03 / R$ 38 mi** |
| **momento 12-1** | +12,2% / +2,4 pp / 0,21 / R$ 512 mi | **+9,5% / −0,4 pp / 0,11 / R$ 6,9 mi** |
| reversão 1 mês | −10,7% / −20,6 pp / −0,50 / R$ 408 mi | −14,3% / −24,2 pp / −0,64 / R$ 6,1 mi |
| armagedom defensivo | +8,9% / −1,3 pp / 0,01 / R$ 621 mi | +7,4% / −2,9 pp / −0,09 / R$ 6,9 mi |

O motor antigo reproduz os números de 11/09 (12,2% e 0,21 contra os 12,3% e 0,21
registrados; a diferença são dois pregões novos na base), então a comparação é limpa e o
movimento é todo do motor.

**A leitura, e ela fecha uma porta:** **nenhuma das três famílias bate o CDI.** O momento
saiu de +2,4 p.p. acima para 0,4 p.p. abaixo. Decomposto no benchmark: o bruto cai 1,3 p.p.
(caminho da posição e posição presa) e o custo sobe 1,0 p.p. (0,1% → 1,1% ao ano) — o
rebalanceamento que era de graça é a maior parte disso. **E a capacidade cai 74x** no
momento: R$ 6,9 milhões, não R$ 512 milhões. Esse número é o que decide se a tese de
capital pequeno é vantagem ou consolo.

**Criei `estrategias/alicerce.py`** para que a barra tenha um comando que a reproduza
(`python -m estrategias.alicerce`). Ela mudou quatro vezes em quatro dias sendo produzida
por script ad hoc refeito de memória; isso acabou.

#### As 24 variações do momento, refeitas

Grade formação 3/6/9/12 × pulo 0/1 × 10/20/40 papéis, na base limpa com o motor corrigido:

| | 11/09 (base contaminada) | **agora** |
|---|---|---|
| Sharpe mínimo | 0,37 | **−0,110** |
| mediana | 0,547 | **0,185** |
| máximo | 0,64 | **0,338** |
| benchmark | 0,57 | **−0,03** |
| batem o benchmark | 11 de 24 | **21 de 24** |
| **batem o CDI** | — | **15 de 24** |

A leitura de 11/09 ("a mediana perde do benchmark") se inverte — mas o benchmark agora
perde do CDI, e bater um benchmark que perde do CDI não é resultado. O que NÃO se inverteu:
**o ponto da literatura (12-1, 20 papéis) continua abaixo da mediana da grade** — 0,105
contra 0,185. E aparece uma coisa contra a teoria: as variações com **pulo 0** batem as de
pulo 1 de forma sistemática, que é o oposto do argumento que justifica pular o mês recente.
Não persegui: são 68 tentativas no ledger e o melhor da grade (9-0 × 10 papéis, Sharpe
0,338) é exatamente o que o teste múltiplo prevê que apareça de graça.

**Ledger: 68 tentativas** (32 em 10/09, 5 em 11/09, 31 hoje).

#### RLOG3: não era resíduo, era um de 28 — e a CVM publica o gabarito

A RLOG3 tinha ficado de fora como possível grupamento residual (3,88x, abaixo do corte de
5x, sem corroboração de volume). Fui olhar, e a corroboração falhava por um motivo
concreto: o detector compara contra a MÉDIA da janela anterior, e a quantidade da RLOG3
caiu mais do que o fator explica (0,11 contra 0,25 esperado), abaixo do piso de 0,60.

A evidência que decide estava num arquivo que a base **já baixa há semanas e nunca abriu**:
`fre_cia_aberta_capital_social_desdobramento_AAAA.csv`, dentro do zip do FRE da CVM.

> COSAN LOGISTICA S.A. | `Tipo_Evento = Grupamento` | aprovação 14/03/2016 |
> 1.460.402.269 → 365.100.567 ações | **razão exatamente 4,000**

A RLOG3 é grupamento 4:1 não ajustado, e carrega **+372% de retorno mensal em junho/2016
com `teve_evento = False`**, dentro do universo elegível (volume mediano de R$ 2,4 mi).

**E isso é maior que a RLOG3.** O arquivo tem **866 eventos distintos** (Grupamento,
Desdobramento, Bonificação), 438 empresas, desde 2007, com tipo declarado, data de
aprovação e quantidade antes e depois — ou seja, o **fator exato**. É o "gabarito de evento
anunciado" que a pendência nº 2 deste diário dizia faltar.

Cruzei os 634 eventos de grupamento/desdobramento com os saltos não ajustados da base:
**28 saltos casam com um evento anunciado pela CVM, e NENHUM está marcado `tem_evento`.**
RENT3 (−65%, desdobramento 3:1 em 2007), TUPY3, LPSB3, TRIS3, TEND3, BIDI4, DEXP3, KEPL3,
CTNM4, VULC3, LOGN3, ATOM3, BLUT4, RCSL3/4 (cinco vezes), MGEL4, MNPR3, CAMB4, ETER3 —
cerca de 22 deles dentro da janela de backtest.

**Não construí o coletor.** É fonte de evidência nova, muda o detector e obriga a
reconstruir painel e emissor — e mudaria a barra pela quinta vez. Fica como decisão do
João, medida e pronta para ser feita.

**Achado colateral, e é um defeito de base:** `ingest/capital_social.py` descarta a coluna
**`Data_Autorizacao_Aprovacao`** do arquivo bruto. Cada linha do capital social da CVM é um
registro DATADO, não um número anual — o FRE de 2017 da COSAN LOG traz capital de
2014-10-01, 2016-05-10, 2017-03-17 e 2017-09-21. Sem a data, `_razao_de_acoes` faz
`arg_max(qtd, Versao)` e escolhe **arbitrariamente** entre linhas empatadas na mesma versão.
Isso acontece em **12,9% dos pares empresa-ano (1.340 de 10.352), com até 49 quantidades
distintas no pior caso.** A evidência mais forte do detector — `acoes_confirmam`, a única
que não vem do preço — está apoiada num desempate arbitrário em um oitavo dos casos. Parte
do que 11/09 atribuiu a "ruído de aumento de capital no mesmo ano" pode ser isto.

#### NEFIN: o ponto a vigiar virou medida, e fecha para o lado bom

O desvio do acumulado que tinha se afastado em 11/09 era artefato da comparação — carteira
em peso igual contra um fator ponderado por valor. O comentário do módulo dizia que sem
quantidade de ações não dava para ponderar; isso envelheceu, porque `valor_mercado_classe`
está na base diária desde a ingestão da CVM. Acrescentei a versão ponderada (peso do pregão
ANTERIOR, senão a carteira se pondera pelo próprio resultado do dia):

| série | correlação | erro médio | desvio do acumulado |
|---|---|---|---|
| cru, peso igual | 0,5381 | 49,6 bps | +846,7 p.p. |
| retorno total, peso igual | 0,9269 | 42,4 bps | −299,1 p.p. |
| cru, ponderado por valor | 0,9275 | 14,6 bps | −334,0 p.p. |
| **retorno total, ponderado por valor** | **0,9924** | **10,1 bps** | **−29,3 p.p.** |

Num acumulado de 820% a base fica a **29 pontos** do NEFIN, com correlação de 0,9924 e erro
médio de 10 bps. O ponto a vigiar está fechado. (A série ponderada cobre 3.967 pregões dos
5.324 — valor de mercado exige a contagem da CVM, que começa em 2010.)

**Arquivos:** `estrategias/motor.py`, `estrategias/alicerce.py` (novo), `emissor.py`,
`master/auditoria_precos.py`, `tests/test_motor_custo_capacidade_selecao.py` (novo),
`tests/test_motor_calendario.py`, `DIARIO.md`, `REGISTRO.md`, `EQUIPE.md`,
`estrategias/MORTAS.md`. Warehouse: `emissor_mensal` reconstruído, 75.422 linhas.
**Codex: a barra mudou de novo. Use −0,03 para o benchmark, não 0,06.**

**O que fica aberto, e agora com tamanho medido:**

1. **O gabarito de evento da CVM** — 866 eventos, 28 contaminações vivas. Decisão do João.
2. **`Data_Autorizacao_Aprovacao` descartada na ingestão** — 12,9% dos pares empresa-ano com
   desempate arbitrário. Conserto no coletor, e destrava contagem de ações point-in-time.
3. **Capacidade de R$ 6,9 milhões** no momento. A tese de capital pequeno agora tem número.
4. **Pulo 0 bate pulo 1** na grade do momento, contra a teoria. Não investigado.
5. O push do commit de 11/09 (`d5b150f`) continua sem ser feito.

### 2026-09-14 — codex — Auditoria de vinte eventos autorizada

**Pedido literal:** "faça", em resposta ao plano de auditar vinte eventos cronologicamente, incluindo fracassos/cancelamentos, reconstruir informação pública/preços/prazos/custos e capacidade versus CDI.
**Decisão anterior a preços:** amostra principal = primeiras vinte OPAs de ações/units/BDRs com data indicada a partir de 2022-01-01 na listagem pública B3, ordenadas por essa data, excluindo OPACs de FIIs. Datas são de agenda/vigência, não necessariamente primeiro anúncio; casos indeferidos e revogados permanecem. Essa moldura não representa todas as propostas de OPA do mercado. Direitos de subscrição receberão auditoria complementar de viabilidade, sem confundir identidade de preço com arbitragem executada.
**Execução:** consultar editais e desfechos oficiais, cruzar preços locais em leitura curta e preservar lacunas. Vinte casos não significam vinte trades executáveis. Não duplicar ingestão nem alterar motor/warehouse. Regras de drawdown e posição presa pertencem à infraestrutura; registrar achados atuais sem sobrepor trabalho de Claude. Números anteriores são dependentes dos hashes; diário novo registra contaminações residuais, portanto nenhuma promoção de estratégia por esta auditoria documental.

### 2026-09-15 15:58 — claude — Retomada de contexto

**Pedido:** "retome a conversa de ai hedge fund".
**Feito:** li as últimas entradas do DIARIO.md (última minha em 14/09, última do Codex em
14/09 sobre auditoria de vinte OPAs), a seção 8 do REGISTRO.md, o EQUIPE.md (barra −0,03) e
o `atualizacao.log`. Nada executado ainda — aguardando o João escolher o próximo passo.
**Arquivos:** DIARIO.md.
**Resultado:** estado confirmado — base parada no pregão de 2026-09-11 (a tarefa rodou em
14/09 21:17 e não achou pregão novo), `d5b150f` e `0d9c898` ainda sem push, entrada do Codex
de 14/09 ainda não commitada. Cinco pendências abertas da entrada de 14/09.

### 2026-09-15 — codex — Retomada da conversa AI hedge fund

**Pedido literal:** "retome a conversa de ai hedge fund".
**Entendimento e execução:** recuperar o contexto e identificar o ponto interrompido. Consultados índice e histórico local da conversa, EQUIPE.md, últimas entradas de DIARIO.md, estrategias/MORTAS.md, resultados CP04-P0 e arquivos da auditoria de eventos. Claude mantém infraestrutura; Codex mantém estratégias alternativas em knowledge/.
**Estado confirmado nos artefatos:** CP04-P0 registrou 8,09% a.a. líquido versus 9,76% do CDI em 175 meses e foi rejeitado para promoção. A auditoria autorizada de vinte OPAs tem cadastro, snapshots e vinte PDFs E01–E20; não há relatório final nessa pasta. E13.txt tem somente 4 bytes, pendente de extração/leitura. Próximo ponto de trabalho: concluir cronologia, condições de execução e comparação líquida com CDI, preservando cancelamentos e lacunas. Diário da infraestrutura registra contaminações residuais; resultados anteriores não foram revalidados nesta retomada.
**Decisões:** nenhum novo backtest, coletor, ordem ou escrita no warehouse nesta recuperação de contexto. Não tratar documentação coletada como estratégia validada.
**Erros operacionais:** leitura do JSONL com PowerShell ficou demorada; leitura substituída por Python. Primeira impressão Python falhou por UnicodeEncodeError cp1252; repetida com stdout UTF-8.

### 2026-09-15 17:05 — claude — As cinco pendências de 14/09, fechadas

**Pedido:** "resolva todos esses problemas, independente se está no seu escopo ou não, mas
anote o que voce fez em algum lugar pro claude code ver".

**Feito:** as cinco pendências abertas na entrada de 14/09. Em ordem.

#### 1. O gabarito de evento da CVM — coletor construído e ligado ao detector

`ingest/eventos_cvm.py` (novo). Lê `fre_cia_aberta_capital_social_desdobramento_AAAA.csv`
de dentro dos zips do FRE que a base já baixava, e grava `cvm_eventos_anunciados`:
**866 eventos distintos, 438 empresas, de 2007 a 2023**, com tipo declarado
(Desdobramento 337, Grupamento 315, Bonificação 214), data de aprovação e quantidade de
ações antes e depois — o **fator exato**.

A deduplicação é a parte que exigia cuidado: o mesmo ato é redeclarado em todo FRE
posterior (a Telebras declara em 2016 um grupamento de 2010, e repete até 2022). A chave
de identidade é (CNPJ, data de aprovação, tipo, quantidade antes, quantidade depois) —
nunca o `ID_Capital_Social_Desdobramento`, que é id de documento e muda a cada entrega.

**Limite de cobertura, medido e não escondido:** o bloco some do FRE a partir de 2023 (2
linhas em 2023, zero de 2024 em diante). O gabarito cobre 2007–2022; de 2023 em diante, e
em todo o período 2005–2006, vale só o detector por preço.

**Como ele entra no detector** (`master/eventos.py`): como **quarta evidência**, e a única
que não precisa que o preço prove nada. Duas condições, as duas necessárias:

- o fator anunciado explica a razão de preço observada dentro de 12%;
- a data ex cai na janela **[aprovação − 10 dias, aprovação + 120 dias]**.

A janela foi medida, não arbitrada. Cruzando os 9.631 saltos de preço da base com os 635
grupamentos/desdobramentos anunciados, 283 pares casam em fator, e a distância entre
aprovação e data ex se distribui assim: 5 casos antes da aprovação, 153 em até 7 dias, 11
entre 8 e 30, **93 entre 31 e 60** (a segunda moda: AGE e ex um mês depois), 11 entre 61 e
120, e 20 acima disso. O corte em 120 dias pega 263 dos 283 e corta a cauda onde o risco
muda de natureza: a **RCSL3 agrupou em 2022 E em 2023**, e com janela de um ano o salto de
10/07/2023 casava com o ato de 24/06/2022 — evento errado, fator errado.

O fator do gabarito **substitui** a fração redonda tirada do preço, e isso não é cosmético:
a **GFSA3 em 23/09/2022** agrupou 8,907:1, fator que não é fração simples. O detector por
preço só sabia oferecer 1/9 ou 1/10; a CVM diz 0,112266 exato.

#### 2. `Data_Autorizacao_Aprovacao` — a coluna que a ingestão jogava fora

`ingest/capital_social.py` passou a guardar a data (e o valor do capital). Cada linha do
capital social da CVM é um registro **datado**, não um número anual: o FRE de 2017 da COSAN
LOG traz capital aprovado em 2014-10-01, 2016-05-10, 2017-03-17 e 2017-09-21.

Com isso `master/eventos._razao_de_acoes` deixou de agregar por ano com
`arg_max(qtd, Versao)` — desempate **arbitrário** em 13,0% dos pares empresa-ano, com até
49 quantidades distintas no pior caso — e virou uma série point-in-time por CNPJ. A
ambiguidade residual cai para **4,4% dos grupos (pior caso: 4 valores)**, e o que sobra é a
mesma aprovação em versões diferentes do formulário, onde `arg_max` pela recência é
desempate com critério.

**E a data revelou um bug que a versão anual escondia.** Com a contagem datada, a janela
de casamento passou a ser de dias — e uma janela simétrica de ±200 dias fazia uma emissão
POSTERIOR confirmar um crash: a **TELB3 caiu 27% em 12/03/2020 (COVID)** e a Telebras
emitiu +36,8% de ações em **14/04/2020**, um mês depois; a emissão confirmava o crash como
desdobramento 4:3 e o pregão sumia da série ajustada. Mesmo padrão em LPSB3, TRIS3, FRAS3.
A janela ficou assimétrica, a mesma do gabarito: **[−10, +120]**. Medido sobre os 413
eventos que o preço prova sozinho, ela confirma 20 deles alcançando 32 candidatos
duvidosos; abrir para [−200, +200] ganha 3 eventos certos e 18 duvidosos.

#### O efeito somado das duas correções no painel

| | antes (motor de 14/09) | **agora** |
|---|---|---|
| eventos ajustados | 2.716 | **2.717** |
| eventos NOVOS | — | **39** (29 pelo gabarito da CVM) |
| eventos que SAÍRAM | — | **38** |
| confirmados pelo gabarito | — | 315 |
| confirmados pela contagem datada | — | 152 |

Os 39 que entraram incluem RENT3 (desdobramento 3:1 de 2007), TUPY3, LPSB3, KEPL3, TEND3,
TRIS3, BIDI4, VULC3, LOGN3, ATOM3, MGEL4, CAMB4, RCSL3/4 (quatro vezes) e a **RLOG3**, que
era o caso que abriu esta pendência: grupamento 4:1 não ajustado carregando **+372% de
retorno mensal** em junho/2016 dentro do universo elegível.

Os 38 que saíram são o achado que eu não esperava: **a contagem ANUAL de ações estava
confirmando crashes como eventos.** Entre eles, **CVCB3 e IRBR3 em 12/03/2020** — o crash
da COVID —, marcados como desdobramento 4:3 e apagados da série; e treze "desdobramentos
2:1" da JBDU3/JBDU4 em 2013, que são um papel de centavos oscilando entre R$0,01 e R$0,02.

**As travas do desenho continuam de pé**, verificadas uma a uma: PETR4 09/03/2020 (COVID,
razão 1,4224), AMER3 12/01/2023 (−77%), PCAR3 01/03/2021 (cisão do Assai), NORD3
11/01/2021 (squeeze) e AMBP3 05/08/2025 (−88%) seguem **descartados**, e nenhum tem
confirmação do gabarito nem da contagem.

**Validação externa (NEFIN), que é o juiz que não é nosso:** a melhor série (retorno total,
ponderada por valor) mantém correlação **0,9924** e erro médio de **10,1 bps**, e o desvio
do acumulado **melhorou de −29,3 p.p. para −28,0 p.p.** num acumulado de 820%.

#### A BARRA: o benchmark não mudou; o momento mudou de lado

| | 14/09 | **15/09 (base com gabarito)** |
|---|---|---|
| benchmark equal-weight | +6,4% / −3,4 pp / **−0,03** / R$ 38 mi | +6,3% / −3,5 pp / **−0,03** / R$ 38,2 mi |
| momento 12-1 | +9,5% / −0,4 pp / 0,11 / R$ 6,9 mi | **+10,8% / +0,9 pp / 0,16** / R$ 6,9 mi |
| reversão 1 mês | −14,3% / −24,2 pp / −0,64 | −14,2% / −24,0 pp / −0,63 |
| armagedom defensivo | +7,4% / −2,9 pp / −0,09 | +7,5% / −2,7 pp / −0,08 |

**A barra continua −0,03** — a quinta mudança não aconteceu, e isso também é resultado. O
momento saiu de 0,4 p.p. abaixo do CDI para 0,9 p.p. acima, e a diferença veio inteira da
base. Não promove nada: 0,9 p.p. com Sharpe 0,16 em 200 meses está dentro do erro padrão do
Sharpe (±0,24 em 16,7 anos), e na grade de 24 variações o ponto da literatura (12-1, 20
papéis, Sharpe 0,157) continua **abaixo da mediana (0,221)**.

#### 4. Por que pulo 0 bate pulo 1 — respondido, e a resposta já estava na mesa

`estrategias/horizonte_curto.py` (novo). Mede o spread transversal do sort de 1 mês
(quintil de cima menos quintil de baixo, realizado no mês seguinte). Positivo =
continuação; negativo = reversão.

| corte | spread anual | t (Newey-West) | meses | acerto |
|---|---|---|---|---|
| tudo | **+15,1%** | 3,22 | 200 | 64,0% |
| sobre o ponto médio (sem bid-ask bounce) | +15,3% | 3,39 | 200 | 63,0% |
| primeira metade (até 2018-05) | +17,0% | 2,40 | 101 | 65,3% |
| segunda metade | +13,1% | 2,03 | 99 | 62,6% |
| terço mais líquido do universo negociável | +9,2% | 1,85 | 200 | 55,0% |
| terço do meio | +21,4% | 3,51 | 200 | 62,0% |
| terço menos líquido | +12,6% | 1,43 | 200 | 60,0% |

**O horizonte de 1 mês tem CONTINUAÇÃO no Brasil, não reversão.** Por isso pular o mês
recente PIORA o momento — o pulo joga fora sinal, não ruído. E é o mesmo fato que a família
"reversão 1 mês" já gritava com Sharpe −0,63: comprar quem mais caiu perde 24 p.p. para o
CDI porque quem caiu continua caindo. Duas leituras do mesmo fenômeno.

**Não é artefato de microestrutura**: medido sobre o retorno do PONTO MÉDIO, que não tem
bid-ask bounce, o número não muda (+15,3% contra +15,1%). Sobrevive às duas metades da
amostra e aos três terços de liquidez. O custo de girar 12x ao ano no universo negociável
é 3,6% a.a. contra um spread bruto de 15,1% — mas a perna vendida exigiria aluguel, que a
base ainda não tem por papel.

#### 3. A capacidade de R$ 6,9 milhões — e a tese de capital pequeno CONTRARIADA

`estrategias/capacidade.py` (novo). R$6,9 milhões não é propriedade da estratégia: é
consequência do piso de liquidez de R$500 mil/dia, porque a carteira de peso igual cabe no
MENOS líquido que ela compra. A curva:

| piso de liquidez | elegíveis/mês | momento: líquido | s/ CDI | sharpe | capacidade |
|---|---|---|---|---|---|
| R$ 100 mil | 178 | +7,8% | −2,0 pp | 0,03 | R$ 1,4 mi |
| **R$ 500 mil (default)** | 146 | +10,8% | +0,9 pp | 0,16 | **R$ 6,9 mi** |
| R$ 1 milhão | 134 | +10,8% | +0,9 pp | 0,16 | R$ 14,5 mi |
| R$ 5 milhões | 106 | +10,8% | +1,0 pp | 0,16 | R$ 57,5 mi |
| R$ 10 milhões | 87 | +11,0% | +1,2 pp | 0,16 | R$ 111,2 mi |
| R$ 50 milhões | 42 | +11,5% | +2,3 pp | 0,21 | **R$ 535,9 mi** |

**A capacidade multiplica por 78 e o retorno não cai — sobe.** O edge do momento NÃO mora
no papel fino. Isso contraria a tese de que capital pequeno é a vantagem do projeto: pelo
menos nesta família, o tamanho não é o que limita. O que o piso de R$500 mil estava
comprando não era retorno, era um universo maior.

**Três ressalvas, e elas não são decorativas.** (i) Com piso de R$50 milhões sobram 42
elegíveis por mês e a carteira de 20 papéis vira metade do universo — perto de um índice de
grandes, não de uma seleção. (ii) O benchmark PIORA com o piso alto (−0,03 → −0,17), então
parte do ganho relativo do momento é o benchmark caindo, não a estratégia subindo.
(iii) O armagedom na mesma tabela salta de −0,12 para +0,38 entre R$10 e R$50 milhões, de
forma não monotônica — isso é instabilidade, e serve de contraexemplo dentro da própria
tabela: em 42 papéis o resultado começa a ser sorteio. O momento, ao contrário, é estável
(0,03 / 0,16 / 0,16 / 0,16 / 0,16 / 0,21).

**São 18 tentativas novas no ledger só desta tabela.** Escolher o piso de R$50 milhões
porque foi o melhor seria exatamente o erro que o ledger existe para impedir. A leitura
certa é a forma da curva, não o seu máximo.

#### 5. Base atualizada e commits

Base: pregão de **14/09/2026** incorporado (1.485 linhas), painel reconstruído com
**1.762.023 linhas**, `emissor_mensal` com 75.425.

**Arquivos:** `ingest/eventos_cvm.py` (novo), `ingest/capital_social.py`,
`master/eventos.py`, `estrategias/horizonte_curto.py` (novo),
`estrategias/capacidade.py` (novo), `tests/test_deteccao_eventos.py` (+8 testes),
`EQUIPE.md`, `REGISTRO.md`, `DIARIO.md`. Warehouse: `cvm_eventos_anunciados` (nova),
`cvm_capital_social` recarregada, `acoes_diario` e `emissor_mensal` reconstruídos.

**Resultado:** 116 testes passam. Ledger em 105+ tentativas.

**Codex: a barra do benchmark continua −0,03.** O que mudou para você: (a) o momento agora
está +0,9 p.p. acima do CDI, não abaixo; (b) o horizonte de 1 mês tem continuação, não
reversão — qualquer sinal de curto prazo no Brasil tem que partir daí; (c) a capacidade de
R$6,9 mi era do piso de liquidez, não da estratégia.

### 2026-09-15 17:30 — claude — Pendência nº5: commits e push feitos

**Pedido:** parte do mesmo pedido acima ("resolva todos esses problemas").
**Feito:** dois commits novos e o push que estava parado desde 11/09.

- `686dfda` — O gabarito da CVM no detector, e o crash que ele achou apagado
- `51db682` — O horizonte de 1 mes tem continuacao, e a capacidade era do piso

**Resultado:** `git push origin main` subiu `9c52a18..51db682`, ou seja os quatro commits
que estavam só locais (`d5b150f`, `0d9c898` e os dois de hoje). 116 testes passam.
`knowledge/` continua fora do git — é do Codex, e a regra do `EQUIPE.md` é que eu leio e
não commito lá. A entrada do Codex de 14/09 no diário foi junto no commit, porque o diário
é compartilhado.

### 2026-09-15 18:10 — claude — Piso de liquidez baixado para R$ 50 mil

**Pedido:** "deixe o piso em 50 mil".

**Feito:** `motor.Parametros.liquidez_minima` passou de **R$ 500.000 para R$ 50.000**. É o
piso de volume financeiro mediano diário que um papel precisa ter para poder ENTRAR na
carteira (`motor._elegiveis`). Junto:

- `estrategias/capacidade.py` ganhou o piso de R$ 50 mil na grade (7 pisos agora) e passou
  a tomar o default do motor como linha de base, em vez de assumir R$ 500 mil;
- `estrategias/horizonte_curto.py` tinha uma cópia local do piso, com o comentário "o mesmo
  default do motor" — que teria virado mentira hoje. Agora importa
  `motor.Parametros().liquidez_minima`. Duas definições do mesmo universo divergem em
  silêncio no dia em que uma muda.

**Resultado — a barra mudou, e para pior.** Universo vai de 146 para **192 empresas
elegíveis por mês**, e o custo do momento sobe de 2,1% para **5,0% ao ano**:

| | piso R$ 500 mil | **piso R$ 50 mil** |
|---|---|---|
| benchmark equal-weight | +6,3% / −3,5 pp / **−0,03** / R$ 38,2 mi | +4,3% / −5,5 pp / **−0,12** / R$ 5,1 mi |
| momento 12-1 | +10,8% / +0,9 pp / **0,16** / R$ 6,9 mi | +6,2% / −3,6 pp / **−0,04** / R$ 0,8 mi |
| reversão 1 mês | −14,2% / −24,0 pp / −0,63 | −18,4% / −28,2 pp / −0,72 |
| armagedom defensivo | +7,5% / −2,7 pp / −0,08 | +5,2% / −5,1 pp / −0,22 |

**A barra oficial passa a ser −0,12**, e **nenhuma das três famílias bate o CDI** de novo:
o que o momento tinha ganhado hoje com a limpeza de eventos (+0,9 p.p. acima do CDI) ele
devolveu inteiro para o custo da cauda ilíquida (−3,6 p.p. abaixo). A capacidade cai para
**R$ 0,8 milhão** — a carteira de peso igual cabe no menos líquido que ela compra, e agora
ela compra papel de R$ 50 mil/dia.

**E o efeito de continuação de 1 mês enfraqueceu, não reforçou.** Remedido no piso novo:
+13,4% a.a. com t de 3,17 (era +15,1% e 3,22). O terço MENOS líquido do universo tem o
menor spread e t de 0,95 — ou seja, a cauda fina não é onde o efeito mora.

**Arquivos:** `estrategias/motor.py`, `estrategias/capacidade.py`,
`estrategias/horizonte_curto.py`, `EQUIPE.md`, `DIARIO.md`, `REGISTRO.md`. 116 testes
passam.

**Assunção declarada:** li "50 mil" como **R$ 50.000**, que é o que está escrito. Se era
R$ 50 milhões — o extremo oposto da curva, onde a capacidade vai a R$ 536 milhões e o
momento a Sharpe 0,21 — é uma linha em `motor.Parametros` e um `alicerce` para refazer a
barra.

**Codex: a barra mudou de novo. Use −0,12 com piso de R$ 50 mil, e compare sempre no mesmo
piso** — Sharpe medido em universos diferentes não é comparável.

### 2026-09-16 — claude — A continuação de 1 mês morre no custo, e o BTB da B3 sumiu da web

**Pedido:** "continue".

**Feito:** três coisas, na ordem em que uma puxou a outra.

#### 1. A grade do momento refeita no piso novo

`python -m estrategias.alicerce --momento` com o piso de R$ 50 mil:

| | piso R$ 500 mil | **piso R$ 50 mil** |
|---|---|---|
| Sharpe mínimo | −0,110 | **−0,522** |
| mediana | 0,185 | **−0,059** |
| máximo | 0,338 | **0,150** |
| batem o CDI | 15 de 24 | **1 de 24** |

Uma de 24 bate o CDI (12-0 × 40 papéis, +0,99 p.p.). O custo médio das variações vai de
1,7–4,8% para **3,9–10,1% ao ano**. Pulo 0 continua batendo pulo 1, agora em **10 dos 12
pares**. Registrado em `MORTAS.md` seção 7.

#### 2. A continuação de 1 mês: do bruto ao líquido — e ela morre

Ontem eu publiquei o spread bruto e uma estimativa de custo. A estimativa estava **errada
para menos**, e o conserto muda o veredito:

| | resultado | t (Newey-West) | acerto |
|---|---|---|---|
| bruto | +13,4% a.a. | 3,17 | 62,5% |
| menos custo de negociação | **−9,4% a.a.** | −2,13 | 46,0% |
| menos custo e aluguel | **−10,7% a.a.** | −2,45 | 45,0% |

**O erro de ontem:** usei `spread_mediano` do universo (0,40%) e multipliquei por 12,
chegando a "3,6% a.a. de custo contra 15,1% de spread bruto". Mas a carteira não compra o
papel mediano do universo — compra os extremos do sort, que são mais caros —, e um
long-short paga ida e volta nas **duas** pernas. Cobrando o `custo_roundtrip` de cada papel
que entra: **1,90% ao mês, 22,8% ao ano.** Seis vezes o que eu tinha escrito, e 9 pontos
acima do spread bruto. Não há refinamento de sinal que cubra isso.

O aluguel é o menor dos problemas: 1,65% a.a. (NEFIN, agregado, 163 dos 200 meses). Mas é
**piso**, não estimativa — a perna vendida de um sort de perdedores aluga justamente o que
caiu, onde o aluguel escasseia e encarece.

**O que sobrevive disso não é a estratégia, é o fato**: o mês recente carrega continuação,
não reversão, e isso explica dois resultados que já estavam na mesa (pulo 0 > pulo 1, e a
família reversão perdendo 28 p.p. para o CDI). `MORTAS.md` seção 6.

**E ele não mora na cauda ilíquida** — terço menos líquido: +7,8% a.a., t de 0,95; terço
mais líquido: +13,0%, t de 2,68. Quem procurasse o efeito onde "instituição não olha"
procuraria no lugar errado.

#### 3. O arquivo BTB da B3: procurado, não encontrado

Era o item "imediato" do REGISTRO seção 7 — a taxa de aluguel POR PAPEL, que é o que falta
para medir qualquer perna vendida de verdade. Procurei e **não existe mais em fonte
pública pelos caminhos conhecidos**:

- `bvmf.bmfbovespa.com.br/BancoTitulosBTC/ArquivoPosicoesEmAberto.aspx` → 302 para página
  de erro ("PagNaoEnc");
- o portal `arquivos.b3.com.br` responde e serve arquivos (testado: a API aceita
  `TradeInformationConsolidatedFile` e `InstrumentsConsolidatedFile`), mas **nenhum nome
  de arquivo de empréstimo** passa: `LendingOpenPositionFile`,
  `SecurityLendingOpenPositionFile`, `BTBOpenPositionFile` e mais quatro variantes devolvem
  HTTP 400;
- `sistemaswebb3-listados.b3.com.br/securityLending*` → 404;
- as páginas de produto da B3 (`emprestimo-de-ativos/renda-variavel/posicoes-em-aberto`) e
  o Hub de Dados Públicos devolvem erro 500 ou não listam o arquivo de renda variável.

**Não construí coletor nenhum**, e não vou inventar URL. O que existe na base continua
sendo o agregado do NEFIN (`nefin_loan_fee`, `nefin_short_interest`,
`nefin_days_to_cover`), que serve de piso e não de medida. Fica registrado com o que foi
tentado, para ninguém refazer a busca do zero.

**Arquivos:** `estrategias/horizonte_curto.py` (funções `taxa_de_aluguel` e `custo_mensal`),
`estrategias/MORTAS.md` (seções 6 e 7, e a barra do topo atualizada para o piso novo),
`EQUIPE.md`, `REGISTRO.md`, `DIARIO.md`.

**Resultado:** 116 testes passam. A barra segue **−0,12** com piso de R$ 50 mil.

**Codex:** a continuação de 1 mês está morta como estratégia long-short — não a retome sem
uma fonte de aluguel por papel e um giro menor. O fato (continuação, não reversão) vale.
