# Registro do projeto quantbr

Documento vivo. Registra **tudo que foi feito** e **tudo que está planejado**, em ordem
cronológica, com as decisões e o motivo de cada uma.

Atualizado a cada avanço, sem exceção, por pedido explícito do João (02/09/2026).

Última atualização: **02/09/2026**

---

## Índice

1. [O que é o projeto](#1-o-que-é-o-projeto)
2. [Cronologia](#2-cronologia)
3. [Estado atual da base](#3-estado-atual-da-base)
4. [Inventário de código](#4-inventário-de-código)
5. [Decisões tomadas e por quê](#5-decisões-tomadas-e-por-quê)
6. [Bugs e armadilhas encontrados](#6-bugs-e-armadilhas-encontrados)
7. [O que está planejado](#7-o-que-está-planejado)
8. [Decisões pendentes do João](#8-decisões-pendentes-do-joão)

---

## 1. O que é o projeto

Pedido original (30/08/2026): montar um mini hedge fund que monitore periodicamente o
SSRN atrás de papers novos, teste esses papers em ações brasileiras, opere com controles
de risco reais de fundo, e seja implementado com o estado da arte de agentes de IA.

Não é um robô de trade. É a infraestrutura de uma gestora: um fluxo auditável de
hipóteses testadas, com protocolo estatístico que o próprio sistema não consegue burlar.

**Repositório**: `C:\Users\joaoz\quantbr`
**Plano completo**: `~/.claude/plans/queria-estabelecer-um-mini-wise-octopus.md`

### Arquitetura em 5 camadas

| Camada | Conteúdo | Situação |
|---|---|---|
| L0 dados | warehouse point-in-time, identidade, preços | **feito** |
| L1 protocolo | pré-registro, ledger de trials, vault, estatística | pendente |
| L2 agentes | scout, librarian, implementer, adversary, risk, pm, scribe | pendente |
| L3 risco | limites, vol alvo, escada de drawdown, stress | pendente |
| L4 execução | paper trading, depois capital real | pendente |

### Contexto que moldou o desenho

Três fatos do João pesaram em toda decisão:

1. **Ele já tem um ativo raro**: pipeline de ingestão da CVM (CDA de fundos), que
   reconstrói a posse institucional de todo o universo de ações BR. Quase ninguém replica.
2. **Ele já viveu o fracasso típico**: >700 especificações testadas no TCC, e *todo*
   candidato positivo morreu na auditoria. O caso decisivo: o lucro inteiro do melhor
   sinal vinha de vender a descoberto micro caps sem aluguel disponível.
3. **Regras metodológicas que ele pagou caro para aprender**: Newey-West com janela
   sobreposta, Fama-MacBeth mês a mês nunca pooled, re-corte de quintil a cada mês,
   custo e viabilidade antes de declarar lucro.

---

## 2. Cronologia

### 30/08/2026 — Pesquisa e plano

Pesquisa do estado da arte antes de qualquer código. Achados que orientaram o desenho:

- **XAlpha** (HKU, jul/2026): loop fechado hipótese→código com memória em três camadas,
  AST gate anti-leakage, juiz de alinhamento ideia↔código.
- **QRAFTI** (2026): framework agêntico para pesquisa empírica em finanças.
- **PseudoBench** (2026) e "Prompt-Hacking: The New p-Hacking?" (CACM): auto-research
  agêntico produz pseudociência de forma mensurável. Mitigação recomendada na
  literatura: pré-registro da configuração e reporte de todas as combinações testadas.
- **FINSABER**: vantagem de estratégias LLM some quando período e universo são ampliados.
- **Deflated Sharpe Ratio** e **PBO/CSCV** (Bailey & López de Prado) como padrão de
  validação; `pypbo` implementa.

**Decisões do João nesta sessão** (via perguntas diretas):
- Python no núcleo, R preservado para econometria já validada
- Casa de research + paper trading; capital real só depois
- GitHub Actions cron + máquina local
- **Só dados gratuitos, tudo via API/download automático** (nada de export manual do
  Economatica, porque isso trava o caminho da ideia até o trade)

### 30/08/2026 — Fase 0: fundação

- Repositório criado, Python 3.12.4 (3.14 não tem wheels do stack quant), `uv`, DuckDB
- `ingest/cotahist.py`: parser do COTAHIST com layout de 245 caracteres
- Carga histórica 2005-2026: 3.459.731 linhas
- `ingest/nefin.py`: fatores de risco BR, aluguel agregado, dividend yield
- `ingest/bcb.py`: Selic, CDI, PTAX, IPCA, IGP-M
- `ingest/canario.py` + GitHub Actions: verifica todo dia útil se as fontes estão de pé
- `tests/test_cotahist_layout.py`: trava o layout contra erro de posição

**Validação empírica da escolha do COTAHIST**: na ingestão de 2024 apareceram AESB3
(AES Brasil, comprada pela Auren), RRRP3 (3R, virou Brava), TRPL3/4 (CTEEP, migrou),
APER3 (fechou capital), SEQL3, BAHI3. Nenhum existe no yfinance hoje.

### 01/09/2026 — Fase 1: identidade e preço

**Descoberta que definiu o desenho**: a B3 e o COTAHIST têm vieses **opostos**. O
COTAHIST é completo mas cru; a API de eventos da B3 é limpa mas só lembra de quem
sobreviveu. Verificado ao vivo: AESB3 devolve listas vazias, RRRP3 devolve corpo vazio,
e consultar `TRPL` devolve um **fundo imobiliário** chamado FII TRPL.

Consequência: os eventos são **detectados do próprio COTAHIST**, e a B3 vira gabarito
para medir se o detector acerta.

Construído:
- `ingest/cvm.py`: cadastro de companhias + formulário cadastral (FCA), 2010-2026
- `ingest/b3_empresas.py`, `ingest/b3_eventos.py`: cadastro e gabarito de eventos
- `master/identidade.py`: securities master (CNPJ como chave estável)
- `master/eventos.py`: detector de desdobramento/grupamento
- `master/precos.py`: três séries de preço lado a lado
- `master/auditoria.py`, `master/calibracao.py`, `master/auditoria_precos.py`
- `tests/test_deteccao_eventos.py`: 20 testes

**Resultados verificados**:
- 43 sucessões de ticker descobertas sozinhas, com as datas encaixando pregão a pregão:
  TRPL4→ISAE4 (14/11 → 18/11/2024), RRRP3→BRAV3, GUAR3→RIAA3, VIIA3→BHIA3, ESTC3→YDUQ3,
  SSBR3→ALSO3, QGEP3→ENAT3, BRDT3→VBBR3, CARD3→CSUD3, LLIS3→VSTE3
- Correlação com o fator de mercado NEFIN: **0,8498 na série crua, 0,9296 na ajustada**
- Nos piores dias o erro cai de 20 pontos percentuais para 0,02
- Saídas por ano entre 14 e 38, nunca zero (controle de survivorship)

### 02/09/2026 — Simplificação de escopo

**Decisão do João**: "está mais complexo do que deveria, podemos ficar só com os dados de
preço de fechamento não ajustados (nominal) de todas as ações da b3 de 2005 pra cá em
frequência diária, e descartar todos os outros dados".

- `painel.py` → tabela `acoes_diario`, uma só, preço nominal
- As outras tabelas continuam no warehouse, **inertes, não apagadas** (reconstruir
  custaria 50 min de download; o ganho seria só disco)
- `ver.py`: raio-x da base

Ressalva registrada uma vez e aceita: preço nominal faz desdobramento parecer queda
(PETR4 marca −49,5% em 28/04/2008, que foi desdobramento 2:1).

### 02/09/2026 — Atualização automática

**Descoberta**: a B3 publica arquivo **diário** (`COTAHIST_D02092026.ZIP`, 576 KB) além
do anual (80 MB). Atualização incremental vira questão de segundos.

- `atualizar.py`: rotina diária idempotente, recupera dias perdidos sozinha
- Primeira execução achou 3 pregões faltando (31/08, 01/09, 02/09) e completou em 3s
- Tarefa agendada no Windows: `quantbr-atualizar`, todo dia às 20:00
- Reconfigurada para **LogonType S4U**: roda com a máquina ligada mesmo sem login, e
  **sem armazenar senha**. Exigiu elevação de administrador (UAC)
- `configurar_tarefa.ps1`: script versionado que registra a tarefa

### 02/09/2026 — Este documento

Pedido do João: manter um registro detalhado de tudo, sempre, ao longo de toda a conversa.

### 02/09/2026 - Revisao: quais problemas sobrevivem ao escopo reduzido

O Joao perguntou se as pendencias continuam valendo agora que so usamos a base de precos.
Verificado no dado, nao por raciocinio:

**Sumiram** (existiam para sustentar dado fora do escopo): os 209 emissores sem CNPJ, o
endpoint errado de proventos, o aluguel por papel (BTB), e o recall de 40,6% do detector.

**Praticamente sumiram**: reaproveitamento de ticker foi checado -- so BIDI11 e BPAC13, e
nos dois casos e a MESMA empresa (Inter e BTG) com instrumento temporario de subscricao,
8 a 10 pregoes cada. As 7 linhas com preco inconsistente da B3 seguem sendo 0,0004%.

**Persiste e ficou maior**: evento corporativo dentro da serie de preco.

| Confianca | Eventos dentro do painel | Papeis afetados |
|---|---|---|
| alta | 1.142 | 534 |
| media | 403 | 222 |

534 dos 1.129 papeis tem ao menos um desdobramento ou grupamento de confianca alta, e
**206 desses eventos acontecem em papel com mais de R$10 milhoes de volume diario** -- nao
e canto do mercado. Mudou a natureza da coisa: antes era bug a corrigir, agora e
propriedade do dado escolhido, e so morde quando a analise calcula RETORNO.

Proposta em aberto (aguardando o Joao): adicionar uma coluna booleana `tem_evento` ao
`acoes_diario` marcando esses 1.545 pregoes. Custo de uma coluna, sem desfazer a
simplificacao nem trazer de volta as series ajustadas.

### 02/09/2026 - Exclusao dos dados fora de escopo e coluna de ajuste

O Joao mandou excluir tudo que nao fosse a base de acoes da B3, e levantou a questao certa:
"quando vamos negociar esses ativos o que vamos ganhar ou perder de fato e o nominal, nao?".

**A resposta, registrada porque orienta o desenho daqui pra frente**: metade certa. O
nominal e o que voce transaciona, mas nao e o que voce ganha. O que voce ganha e preco
vezes QUANTIDADE, e desdobramento muda a quantidade.

    PETR4, quem tinha 100 acoes:
      25/04/2008   R$84,30 x 100 = R$8.430
      28/04/2008   R$42,59 x 200 = R$8.518

    A serie nominal marca -49,5%. O dinheiro na conta subiu 1,0%.

Isso inverte o que a serie ajustada e: nao e construto academico, e o registro honesto do
que aconteceu com o dinheiro. A nominal e que mostra um preco que ninguem perdeu. Vale
igual para dividendo (o preco cai no ex, mas o dinheiro entrou na conta).

    para EXECUTAR (ordem, corretagem, emolumento, lote)  -> nominal
    para MEDIR (retorno, backtest, P&L, sinal, risco)    -> ajustado

Consequencia pratica para o objetivo de negociar de verdade: backtest em nominal veria
uma queda de 49,5% num dia de ganho de 1%, em 573 dos 1.129 papeis. Sinal de momento e
reversao erraria sistematicamente. **Isso afeta a pesquisa historica, nao a execucao
futura** -- o corretor ajusta a posicao sozinho quando o evento acontece.

**O que foi feito**: antes de excluir, a informacao de evento foi dobrada para dentro da
propria tabela, como duas colunas:

    fator_acum   preco ajustado = fechamento / fator_acum   (1,0 quando nao ha evento)
    tem_evento   marca o pregao do evento

Assim o painel continua sendo UMA tabela e nominal continua sendo a coluna principal, mas
o retorno correto esta a uma divisao de distancia. 1.547 pregoes com evento, 573 papeis,
542.772 linhas com fator diferente de 1.

Verificado: PETR4 em 28/04/2008 marca -49,5% nominal e +1,0% ajustado; no crash da COVID
o fator fica em 1,0 e o retorno de -29,7% nao e tocado.

**Excluido de fato**:
- 17 tabelas (b3_empresas, b3_eventos_*, bcb_sgs, cvm_*, eventos_detectados, master_*,
  nefin_*, precos_diarios) -- ~2,08 milhoes de linhas
- brutos de NEFIN e CVM em `data/raw/`
- banco recompactado reescrevendo so as tabelas mantidas (DROP TABLE nao devolve espaco
  ao sistema de arquivos): **382 MB -> 184 MB, 52% menor**
- canario do CI reduzido para vigiar so o COTAHIST anual e o diario; vigiar fonte que
  ninguem consome so geraria alarme falso

**Mantido**: `b3_cotahist` (landing bruto da B3) e `acoes_diario` (o painel). Os zips
anuais em `data/raw/b3_cotahist` (639 MB) ficaram, porque sao a fonte para reconstrucao e
para `--reconciliar`.

Codigo nao foi apagado: `master/` e os coletores de NEFIN/BCB/CVM continuam no repo.
`master/eventos.py` inclusive segue em uso -- e ele que produz o `fator_acum`. Os demais
(`master/precos.py`, `identidade.py`, `calibracao.py`, `auditoria*.py`, `ingest/nefin.py`,
`bcb.py`, `cvm.py`, `b3_empresas.py`, `b3_eventos.py`) referenciam tabelas que nao existem
mais e **nao rodam sem reingerir os dados**.

### 02/09/2026 - Decisao: as duas series ficam, e a escolha segue o paper

Joao: "mantem as duas entao e a gente adapta de acordo com o que os papers que a gente vir
da SSRN fizer".

E o desenho certo, e coincide com o que o plano original ja previa para a camada de
protocolo: a serie de preco vira **parametro do teste**, declarado no pre-registro, e nao
um default escondido dentro do pipeline. Paper de momento costuma usar preco ajustado por
evento; paper de asset pricing costuma usar retorno total; paper de microestrutura usa
nominal. Nao ha uma resposta unica, e fingir que ha e que seria errado.

**Implementado**: `fechamento_ajustado` virou coluna materializada, ao lado de
`fechamento`. As duas sao cidadas de primeira classe. Antes o ajustado era uma conta
(`fechamento/fator_acum`) que alguem precisava lembrar de fazer -- e esquecer disso e erro
silencioso: o numero sai, so sai errado.

Colunas finais de `acoes_diario`:

    ticker, data, classe, empresa, isin,
    fechamento,            -- nominal
    abertura, maxima, minima, volume, quantidade, negocios,
    fechamento_ajustado,   -- corrigido por desdobramento/grupamento
    fator_acum, tem_evento

Numeros: 1.547 pregoes com evento, 573 papeis afetados, 542.772 linhas com fator != 1.

**LACUNA QUE VAI APARECER LOGO**: nao ha ajuste por PROVENTO. A maior parte da literatura
de asset pricing usa retorno TOTAL (com dividendo e JCP), entao o primeiro paper do SSRN
que a gente testar provavelmente vai esbarrar nisso. O caminho ja esta mapeado: o endpoint
paginado `GetListedCashDividends` da B3, que tem 337 registros para a Petrobras contra os
24 do `GetListedSupplementCompany` usado antes. Nao foi feito agora porque nao ha analise
esperando por ele.

`ver.py` ganhou uma secao "AS DUAS SERIES DE PRECO" explicando qual usar para que.

### 02/09/2026 - Terceira serie (retorno total) + bid/ask + taxa livre de risco

Joao: "mantenha tambem a ajustada por proventos. apenas essas 3 ou adicione outra se achar
importante para a gente testar papers da ssrn".

**PROVENTOS -- endpoint trocado.** A primeira tentativa usou `GetListedSupplementCompany`,
que e esparso: 24 registros para a Petrobras. O `GetListedCashDividends`, paginado, tem
**343 para a Petrobras, 956 para o Itau, 152 para a Vale**. Total coletado: **28.848
proventos de 777 empresas, contra 1.213 antes -- 24 vezes mais**.

Detalhes que importam e ja foram tratados:
- teto de pagina 120 (acima disso volta vazio com status 200, a mesma armadilha de sempre)
- o endpoint e chaveado por `tradingName`, e o campo `nome_res` do COTAHIST e exatamente
  esse nome -- a ponte sai do proprio dado, sem cadastro externo
- `typeStock` (ON/PN/PNA...) mapeia para o sufixo do ticker pela convencao da B3
- a razao de ajuste e (P_com - D)/P_com com preco CONTEMPORANEO: livre de escala, entao
  dividendo antigo nao precisa ser corrigido por desdobramento posterior

**O resultado mostra por que a serie importa** (2005 a 2026):

| Papel | Nominal | Ajustado | Retorno total |
|---|---|---|---|
| PETR4 | **-49%** | +309% | **+2.251%** |
| BBAS3 | -33% | +305% | +1.542% |
| VALE3 | +8% | +332% | +1.282% |
| CMIG4 | **-83%** | -54% | **+89%** |

A serie nominal diz que a Petrobras perdeu metade do valor desde 2005. Quem ficou com o
papel multiplicou por 23. A CMIG4 parece desastre de -83% e deu lucro.

**COBERTURA, que precisa ser reportada em todo resultado**: 740 de 1.129 papeis (66%) tem
provento registrado. Os 389 que faltam sao em boa parte empresas que sairam da bolsa -- a
B3 nao mantem o historico delas. Ou seja, a serie de retorno total e forte para quem esta
vivo e fraca para quem morreu, que e o oposto do que um estudo sem survivorship precisa.

**DUAS ADICOES QUE EU RECOMENDEI E IMPLEMENTEI:**

1. `melhor_compra` / `melhor_venda` -- bid e ask no fechamento. Ja estavam no COTAHIST e
   eu os tinha descartado. Voltam porque o spread e a maior parcela do custo em papel
   pouco liquido (ignora-lo faz estrategia de small cap parecer lucrativa quando nao e) e
   porque spread relativo e proxy padrao de liquidez na literatura. Custo marginal: zero.

2. `taxa_livre_risco` (tabela separada) -- CDI e Selic diarios do BCB, 2005-2026, 10.881
   observacoes. Retorno excedente, Sharpe, alfa e premio de risco todos comecam
   subtraindo a taxa livre de risco; sem ela metade das contas da literatura nao fecha.
   Ficou fora do painel de acoes de proposito -- o painel continua sendo so acoes.

**Colunas finais de `acoes_diario`** (20):

    ticker, data, classe, empresa, isin,
    fechamento, abertura, maxima, minima,
    melhor_compra, melhor_venda,
    volume, quantidade, negocios,
    fechamento_ajustado, fator_acum, tem_evento,
    fechamento_retorno_total, fator_prov_acum, tem_provento

### 02/09/2026 - Valor de mercado

Joao: "adiciona o valor de mercado tambem".

**FONTE**: Formulario de Referencia da CVM, dois arquivos por ano desde 2010.

    fre_cia_aberta_capital_social        -> acoes ON, PN e total
    fre_cia_aberta_distribuicao_capital  -> as mesmas EM CIRCULACAO (free float)

Conferido na Petrobras, FRE 2023: 7.442.454.142 ON + 5.602.042.788 PN = 13.044.496.930,
com 8.268.206.423 em circulacao (63,4%). Carregados 15.522 registros de capital e 11.381
de free float, 2010 a 2026.

**O PROBLEMA DA PONTE, que era a pendencia numero 1 do projeto.** O FRE e chaveado por
CNPJ e o painel por ticker. O FCA da CVM resolve 580 dos 1.035 tickers -- o campo
`Codigo_Negociacao` esta vazio em metade das linhas. Os que faltavam incluiam nomes
grandes: B3SA3, CSNA3, KLBN3/4, MBRF3, CMIN3.

Resolvido SEM casar por nome, que erraria em silencio ("KLABIN S/A" casa com tres empresas
na CVM, duas canceladas). O caminho e deterministico, em tres saltos:

    ticker -> emissor do ISIN (BRCSNAACNOR6 -> CSNA)
    emissor -> codeCVM, via GetListedSupplementCompany da B3
    codeCVM -> CNPJ, via cad_cia_aberta da CVM

Com uma **guarda contra falso par**: o vinculo so e aceito se o `tradingName` que a B3
devolve bater com o nome que o COTAHIST registra para aquele ticker. Resultado: 209 de 303
emissores resolvidos, e **28 descartados justamente pela guarda** -- seriam pares errados
do tipo "FII TRPL", o fundo imobiliario que a B3 devolve quando se pergunta pela CTEEP.

**DUAS MEDIDAS**, porque servem a coisas diferentes:

    valor_mercado_classe    acoes daquela classe vezes o preco dela
    valor_mercado_empresa   soma das classes; e o "tamanho" dos size sorts e do fator SMB

**DEFASAGEM DE DIVULGACAO**: o FRE tem data de referencia 31/12 mas so e entregue por
volta de maio seguinte. Aplicada defasagem de 6 meses (liberado em 1o de julho). Sem isso,
o painel saberia em janeiro um numero que so seria publicado em maio -- look-ahead.

**VALIDACAO**: as maiores empresas hoje saem Petrobras R$661 bi, Itau R$476 bi, Vale
R$359 bi, BTG R$253 bi, Ambev R$246 bi, WEG R$213 bi. Nomes certos, ordem certa, magnitude
certa.

**COBERTURA**: 94,8% das linhas a partir de julho/2011; 11,7% antes, porque o FRE so
comeca em 2010. Entre os papeis liquidos hoje, **181 de 182**. A limitacao pre-2011 e
estrutural e precisa ser respeitada em qualquer teste que use tamanho.

`acoes_diario` fica com **24 colunas**:

    ticker, data, classe, empresa, isin, cnpj,
    fechamento, abertura, maxima, minima, melhor_compra, melhor_venda,
    volume, quantidade, negocios,
    fechamento_ajustado, fator_acum, tem_evento,
    fechamento_retorno_total, fator_prov_acum, tem_provento,
    acoes_da_classe, valor_mercado_classe, valor_mercado_empresa

Warehouse em 279 MB. Tabelas auxiliares: `b3_proventos` (28.848), `taxa_livre_risco`
(10.881), `cvm_capital_social` (15.522), `cvm_free_float` (11.381), `cvm_ponte_ticker`
(4.388), `ponte_emissor_cnpj` (209), `b3_cotahist` (landing bruto).

### 03-06/09/2026 - Corpus de papers da SSRN e triagem

Joao pediu, antes de decidir sobre dado contabil: pegar os papers mais relevantes da SSRN,
todos desde 2025, atualizacao periodica, e so entao avaliar se vale o esforco contabil.

**ACESSO -- o que da e o que nao da.** Testado ao vivo:

    api.ssrn.com                     FUNCIONA, devolve JSON
    papers.ssrn.com (HTML)           403 do Cloudflare, tanto requests quanto WebFetch
    api.ssrn.com/.../papers/{id}     401, exige autenticacao

Entao ha metadado, mas **nao ha abstract em massa**. O OpenAlex tambem nao resolve: indexa
1,67 milhao de trabalhos da SSRN, mas so 0,1% tem abstract (a SSRN nao deposita abstract de
preprint no Crossref).

**LIMITE DURO DA API**: o parametro `index` trava em 9.999 -- acima disso vem HTTP 500.
Da para pegar o top ~9.800 por download e os ~9.800 mais recentes, e nada alem por essa via.

**DUAS FONTES, que se encaixam:**

| Fonte | Da | Limite |
|---|---|---|
| SSRN API, binding 203 (Financial Economics Network, 276 mil papers) | downloads, a metrica de relevancia deles | teto de 9.800 por consulta |
| OpenAlex, fonte S4210172589 | corpus completo desde 2025, citacoes, topicos classificados | sem teto (cursor) |

Chave de ligacao: o DOI do OpenAlex e `10.2139/ssrn.{id}`, o mesmo id da SSRN.

**COLETADO**: 19.515 papers da SSRN (9.794 mais baixados de todos os tempos, corte em
~2.930 downloads, mais 9.800 recentes) e 20.676 trabalhos do OpenAlex em financas desde
2025. Validacao do corpus: os campeoes sao Fama-French Five-Factor, Jegadeesh-Titman
("Relative Strength Strategies"), Kelly-Xiu, Jensen-Meckling. E o corpus certo.

**ATUALIZACAO**: embutida na rotina diaria (`atualizar.py`), com controle proprio de
frequencia -- roda no maximo uma vez a cada 7 dias, e a propria tabela diz quando foi a
ultima. Evitou criar segunda tarefa agendada e outra elevacao de administrador. Fica num
`try` separado: falha de rede na SSRN nao pode derrubar a atualizacao de preco.

**TRIAGEM** (`triagem.py`): classifica cada paper em (1) e estudo de retorno de acao? e
(2) de que dado precisa. Por palavra-chave, com todos os conjuntos escritos em aberto no
modulo. **E heuristica, serve para dimensionar e nao para decidir paper a paper.**

Dois erros reais foram pegos olhando exemplos, e corrigidos:
- `profitab` casava com "A **Profitable** Day Trading Strategy", classificando como se
  precisasse de balanco. Trocado por formas em que rentabilidade e caracteristica da
  empresa ("profitability factor", "gross profitability"...)
- "A Five-Factor Asset Pricing Model" caia na zona cinzenta, quando exige rentabilidade e
  investimento. Adicionados "five-factor", "q-factor", "hml"

**RESULTADO -- a resposta sobre dado contabil:**

| | Corpus inteiro (19.515) | Relevantes, >=2.000 downloads |
|---|---|---|
| estudos de retorno de acao | 2.523 (13%) | 1.225 |
| **testaveis hoje, sem dado novo** | **546** | **220** |
| destravariam so com contabil | 173 | 65 |
| zona cinzenta (nao deu para classificar) | 1.238 | 731 |

Dado contabil somaria cerca de **32% a mais** de papers testaveis (173 sobre 546).

**A RESSALVA QUE PESA MAIS QUE O NUMERO**: a zona cinzenta (1.238) e maior que as duas
categorias somadas. Sem abstract, o titulo sozinho nao diz de que dado o paper precisa.
Entao 32% e piso, nao estimativa central, e a incerteza e grande.

### 09/09/2026 - Auditoria do tratamento: split, provento, mudanca de ticker

Joao pediu a base "melhor tratada" (splits, dividendos, mudanca de nome, M&A) e perguntou
como ela esta. Isto e o diagnostico, medido no banco, nao estimado.

**1. SPLIT/GRUPAMENTO -- o detector reprova evento obvio pela tolerancia.**

O painel marca 1.549 dias de evento em 573 papeis. Mas a serie AJUSTADA ainda tem
**438 quedas maiores que 45% e 626 altas maiores que 90%, em 199 papeis**. Foram
inspecionados os maiores, e a causa e sempre a mesma:

| ticker | data | de | para | razao | fracao mais proxima | erro | veredito |
|---|---|---|---|---|---|---|---|
| CSAN3 | 06/05/2021 | 89,17 | 21,54 | 4,1397 | 17/4 = 4,25 | 2,59% | descartado |
| KROT3 | 12/09/2014 | 61,94 | 15,05 | 4,1156 | 4,00 | 2,89% | descartado |
| NATU3 | 31/03/2006 | 125,00 | 25,70 | 4,8638 | 19/4 = 4,75 | 2,40% | descartado |
| TRPL4 | 05/04/2019 | 79,20 | 20,30 | 3,9015 | 4,00 | 2,46% | descartado |
| CSNA3 | 23/01/2008 | 144,00 | 46,00 | 3,1304 | 13/4 = 3,25 | 3,68% | descartado |
| LWSA3 | 01/02/2021 | 102,22 | 26,66 | 3,8342 | 15/4 = 3,75 | 2,25% | descartado |
| ORVR3 | 11/08/2026 | 67,60 | 16,40 | 4,1220 | 4,00 | 3,05% | descartado |

Dois defeitos somados, e o segundo e o mais insidioso:

- `TOLERANCIA_RELATIVA = 0,02` e apertada demais. O papel **tambem negocia no dia ex**;
  o erro real medido nesses casos fica entre 2,2% e 3,7%, nao abaixo de 2%. A tolerancia
  foi calibrada num caso feliz (PETR4 2008, erro 1,03%) e generalizada.
- `DENOMINADOR_MAXIMO = 4` foi acertado para razao PEQUENA e esta errado para razao
  GRANDE. Perto de 4 as fracoes com denominador 4 sao densas (13/4, 15/4, 17/4, 19/4,
  espacadas de 0,25, ou 6%), entao **elas roubam o casamento do inteiro verdadeiro**:
  4,14 casa com 17/4 em vez de 4, e 4,86 casa com 19/4 em vez de 5. O erro fica pequeno
  e mesmo assim acima da tolerancia -- reprovado pelo motivo errado.

Nos sete casos, `quantidade_confirma` e/ou `financeiro_estavel` eram VERDADEIROS e
`razao_extrema` tambem. Toda a evidencia estava la; so o teste de "razao redonda" barrou.
Como ele entra como AND obrigatorio em todos os ramos da classificacao, veta sozinho.

Contagem do balde inequivoco: **42 eventos com razao extrema (>=3x), erro entre 2% e 6% e
confirmacao de quantidade ou financeiro, todos descartados**. Em 42 papeis distintos.

**Bonificacao nao e tratada**: `RAZAO_MINIMA = 1,30` significa que bonificacao de 10% ou
20% -- comum no Brasil -- nunca vira candidata. Ela entra na serie como retorno negativo.

**2. PROVENTO -- o buraco e de identidade, nao de dado faltando.**

`b3_proventos` tem 28.848 registros de 547 empresas, de 1995 a 2026, ja pelo endpoint
certo (`GetListedCashDividends`; a correcao do endpoint listada como pendente na secao 8
JA FOI FEITA -- Petrobras tem 166 registros PN, nao 24).

O problema esta no casamento. `painel._fatores_de_provento` liga provento a ticker por
**(nome da empresa, sufixo)**. O nome do COTAHIST muda com o tempo e o nome que a B3 aceita
na consulta e o atual. Resultado medido:

| ticker | periodo | proventos aplicados |
|---|---|---|
| ABEV3 | 11/2013 a hoje (3.181 pregoes) | **0** |
| KLBN4 | 2005 a hoje (5.374 pregoes) | **0** |
| KLBN3 | 3.263 pregoes | **0** |
| AMBV4 | ate 11/2013 | 31 |

A AMBEV existe na tabela de proventos com 67 registros ON e 67 PN, mas **terminando em
13/09/2013** -- exatamente quando virou "AMBEV S/A" e ABEV3. A consulta pelo nome novo
nao trouxe nada, e o nome velho so casa com AMBV3/AMBV4. Treze anos de dividendo da
maior pagadora da bolsa simplesmente nao estao na base.

Nomes do painel sem nenhum provento casado, por volume negociado:
AMBEV S/A (R$ 1,06 tri), VALE R DOCE (500 bi), KLABIN S/A (340 bi), AZUL (332 bi),
SUZANO PAPEL (168 bi), TIM PART S/A (157 bi), HYPERMARCAS (119 bi), ESTACIO PART (111 bi),
ITAUBANCO (100 bi), LIGHT S/A (94 bi), BRF FOODS (69 bi).

Somado a isso, a limitacao ja conhecida e registrada: a B3 tem cobertura fraca de provento
de empresa que saiu da bolsa.

**3. MUDANCA DE TICKER E M&A -- a base parte a serie da mesma empresa em duas.**

**669 dos 1.035 papeis ON/PN morrem** (ultimo pregao antes de 06/2026), e eles somam
**25,3% de todo o volume da base**. Boa parte nao morreu: mudou de codigo.

Busca por par "ticker morre / outro nasce no pregao seguinte com o MESMO nome de pregao":
**104 pares, 85 empresas, R$ 1,28 trilhao de volume na perna morta**.

| nome | morreu | nasceu | volume da perna morta |
|---|---|---|---|
| EMBRAER | EMBR3 (31/10/2025) | EMBJ3 (03/11/2025) | R$ 434 bi |
| GOL | GOLL4 (11/06/2025) | GOLL54 (12/06/2025) | R$ 265 bi |
| MARFRIG | MRFG3 (22/09/2025) | MBRF3 (23/09/2025) | R$ 255 bi |
| SUZANO PAPEL | SUZB5 (09/11/2017) | SUZB3 (10/11/2017) | R$ 100 bi |
| B3 | BVMF3 (23/03/2018) | B3SA3 (26/03/2018) | R$ 15 bi |
| ITAUUNIBANCO | ITAU4 (19/05/2009) | ITUB3 e ITUB4 (20/05/2009) | R$ 7 bi |
| BRF FOODS | PRGA3 (09/12/2009) | BRFS3 (10/12/2009) | R$ 8 bi |

E **esse numero e piso**, porque a busca exige nome identico. Quando o nome muda junto,
ela nao acha. Caso concreto: ELET3/ELET6 param em 07/11/2025 e AXIA3/AXIA6 (AXIA ENERGIA)
comecam em 10/11/2025 -- a Eletrobras, R$ 593 bi de volume, aparece como empresa que
faliu mais um IPO novo. Para achar esses, so pelo CNPJ da CVM.

Falta tambem o **retorno de delisting**: quando o papel sai por OPA ou incorporacao, o
acionista recebe dinheiro ou acao do comprador. Hoje a serie so termina, e o backtest ou
descarta a posicao no ultimo preco (otimista) ou nao sabe o que fazer.

**4. IDENTIDADE**: 202 dos 1.129 tickers (7,2% do volume) ainda sem CNPJ.

**Nota de arquitetura descoberta na auditoria**: `master/precos.py` esta MORTO. Ele le
`eventos_detectados` e `b3_eventos_caixa`, tabelas que nao existem mais depois da limpeza
de 02/09. Quem constroi as tres series hoje e `painel.py`, que chama `eventos.detectar()`
ao vivo. Manter os dois confunde -- o proximo trabalho deve consolidar num so.

### 09/09/2026 - Correcao do detector de split, e o que ela revelou

Regra nova, em duas partes (`master/eventos.py`):

1. **Denominador por faixa de razao** (`RAZAO_SO_INTEIRA = 3.0`): de 3x para cima so casa
   com inteiro. Abaixo de 3 continua ate denominador 4, onde 3:2, 5:2, 4:3 e 7:4 existem
   de verdade.
2. **Tolerancia em dois niveis**: `TOLERANCIA_RELATIVA` de 2% para **2,5%**, e
   `TOLERANCIA_COM_EVIDENCIA = 5%` liberada SO quando ha evidencia que nao vem da propria
   fracao -- razao extrema (>=3x) ou classe irma confirmando no mesmo pregao. Quantidade e
   financeiro NAO liberam a folga: sao confirmacoes mais fracas, e com 5% solto em razao
   pequena uma queda perto de 7/4 comecaria a passar.

A trava do desenho e o crash da COVID na PETR4: razao 1,4224, erro de 5,17% contra 3/2.
Fica reprovado nos dois niveis, com margem de 0,17 ponto. Quem for mexer nesses numeros
tem que olhar esse caso primeiro -- virou teste.

**Resultado nos sete casos da auditoria**: todos passaram a confianca **alta**. CSAN3 em
06/05/2021 era -75,8% na serie ajustada, virou -3,4% (o movimento real do dia). PETR4 em
09/03/2020 segue -29,7%, como tem que ser.

**A/B no mesmo dado**, mesma base, so trocando os parametros:

| | eventos aplicados | quedas < -45% | altas > +90% | papeis |
|---|---|---|---|---|
| antes | 1.846 | 438 | 626 | 357 |
| depois | 2.106 | **446** | **648** | 347 |

**O contador de saltos SUBIU, e isso e uma boa noticia -- o motivo importa mais que o
numero.** Diff dos conjuntos: 66 saltos resolvidos, 96 novos. Os "novos" nao sao erro
novo; sao erro que estava escondido atras de fracao inventada. Com denominador 4 solto em
razao alta, o detector antigo casava razao grande com fracao meia-quebrada e aplicava,
com confianca ALTA:

| caso | razao real | fator que o detector antigo aplicava | o que era de verdade |
|---|---|---|---|
| **AMER3 12/01/2023** | 4,4118 | 13/3 = 4,3333 (erro 1,8%) | **o colapso da Americanas** -- fraude contabil, -77% real |
| MGLU3 06/08/2019 | 7,5410 | 15/2 = 7,5 (erro 0,5%) | desdobramento 8:1, ajustado errado |
| MGLU3 05/09/2017 | 7,5828 | 15/2 = 7,5 | desdobramento 8:1, ajustado errado |
| PCAR3 01/03/2021 | 3,5577 | 7/2 = 3,5 (erro 1,6%) | **cisao do Assai**, nao desdobramento |
| CASH3 10/09/2021 | 5,5346 | 11/2 = 5,5 | desdobramento, fator provavelmente 6:1 |
| NATU3 02/07/2025 | 3,6173 | 11/3 = 3,6667 | evento societario, nao desdobramento |

Ou seja: **o detector antigo estava apagando da serie ajustada a queda da Americanas** e
a cisao do Assai, e ajustando desdobramento 8:1 com fator 7,5 (residuo de 6,7% embutido).
O contador de saltos era menor porque a maquiagem escondia o buraco. A regra nova se
recusa a inventar fracao, e o que sobra fica visivel.

**Verificacao que fecha o ponto**: no painel reconstruido, das 1.094 quedas e altas
residuais, **ZERO estao em dia marcado como evento**. Todo ajuste que foi aplicado ficou
certo; o que sobrou e evento que nunca foi detectado.

**O residuo, agora, tem quatro causas distintas -- e so a primeira e "erro do detector":**

| causa | exemplos | o que resolve |
|---|---|---|
| desdobramento com dia ex mexendo mais de 5% | MGLU3 8:1 (erro 5,2% e 5,7%), CASH3 6:1 (7,8%) | corroborar com a **contagem de acoes da CVM** (`cvm_capital_social`), nao afrouxar mais a tolerancia -- 6% ja encostaria na cisao da NATU3, a 9,6% |
| grupamento em papel de centavos | GPCP3 (0,09 -> 18,90), IRBR3 (0,93 -> 22,06), BHIA3 (0,50 -> 11,17), OSXB3, AMOB3, AERI3 | `PRECO_MINIMO_CONFIAVEL = R$1` exclui **justamente a populacao que faz grupamento** -- quem agrupa esta barato, e por isso agrupa. 2.057 candidatos estao nesse balde |
| cisao / spin-off | PCAR3 -> Assai, NATU3 07/2025 | evento diferente: o acionista recebeu acao da nova empresa. Tratamento proprio, parecido com provento em especie |
| queda real | AMER3, OIBR3 | **nada** -- e para ficar assim mesmo |

**Testes**: 32 passando (eram 16). Os 12 novos travam os sete desdobramentos, a regra de
"fracao densa nao rouba o inteiro" (4,1397 tem que casar com 4, nao com 17/4) e a COVID
reprovada tambem no nivel de 5%.

**Estado do painel apos reconstruir**: 1.678.985 linhas, **1.766 dias de evento em 605
papeis** (eram 1.549 em 573).

### 10/09/2026 - Etapa 0 e 1 do tratamento: linha de base e unidade de cotacao

Plano aprovado: securities master por CNPJ + tratamento de eventos, em 8 etapas.
Decisoes do Joao: delisting por motivo + convencao declarada; universo ON/PN/Unit com
coluna de regime (ETF fora); retorno vira a primitiva.

**ETAPA 0 -- linha de base congelada.** `master/auditoria_tratamento.py` (novo) grava
`acoes_diario_base_20260910` e compara duas versoes da base. Alem das metricas agregadas,
devolve o DIFF caso a caso dos saltos residuais -- porque o agregado ja mentiu uma vez
(09/09: o contador subiu quando o detector melhorou). Estado congelado: 1.678.985 linhas,
1.129 papeis, 446 quedas e 648 altas residuais, 91,0% de cobertura de provento por volume,
92,2% de CNPJ, 108 papeis truncados.

**ETAPA 1 -- o preco vira preco POR ACAO.**

O COTAHIST cota parte da base por LOTE DE MIL e o campo `fator_cotacao` diz qual. Nada no
pipeline dividia por ele. Verificacao que fechou o diagnostico: a mediana de
`fechamento / (volume/quantidade)` e **exatamente** o fator_cotacao em cada faixa
(1, 100, 1.000, 10.000, 1e6) -- o campo nao e decorativo, e a unidade.

238 papeis do painel atravessam uma virada de unidade, quase todos entre 2005 e 2007,
quando a B3 migrou de por-mil para por-acao: LREN3, ELET3, SBSP3, CMIG4, BRKM5, CPLE6,
PCAR4, AMBV4, CESP6, ALPA4.

O dano nao era so de nivel de preco. Como a migracao vinha junto com um GRUPAMENTO, a
razao cotada mostrava o efeito LIQUIDO dos dois:

| ticker | data | cotado | por acao | detector antes | detector agora | erro |
|---|---|---|---|---|---|---|
| CMIG4 | 04/06/2007 | 79,56 -> 39,40 | 0,0796 -> 39,40 | desdobramento 2:1 | **grupamento 495:1** | 1% -> **0,045%** |
| ELET3 | 20/08/2007 | 47,50 -> 24,40 | 0,0475 -> 24,40 | desdobramento 2:1 | grupamento 514:1 | 0,06% |
| BRKM5 | 16/05/2005 | 88,85 -> 22,90 | 0,0889 -> 22,90 | desdobramento ~4:1 | grupamento 258:1 | 0,10% |
| SBSP3 | 04/06/2007 | 315,00 -> 39,20 | 0,315 -> 39,20 | desdobramento 8:1 | grupamento 124:1 | 0,36% |

O erro relativo caiu uma ordem de grandeza em todos. Isso e a evidencia de que a leitura
normalizada e a certa: grupamento de verdade usa razao redonda, e razao redonda so aparece
na unidade certa.

**Onde a normalizacao entrou**: em `master/eventos.py::_serie_por_ticker` (antes do
detector, senao ele continua lendo o efeito liquido) e em `painel.py::construir`
(fechamento, abertura, maxima, minima, melhor_compra, melhor_venda). `fechamento_cotado` e
`fator_cotacao` ficam como colunas de rastreabilidade -- regra 2 do projeto.

**Duas correcoes que sairam de brincadeira e viraram parte da etapa:**

1. **O corte de centavos tem que valer sobre o preco COTADO, nao sobre o preco por acao.**
   O tick de R$0,01 incide sobre a cotacao; num papel cotado por mil acoes ele vale
   R$0,00001 por acao, e o argumento simplesmente nao se aplica. Se o corte olhasse o
   preco por acao, os 238 papeis cairiam inteiros no balde de centavos e o grupamento da
   CMIG4 ficaria de fora do ajuste -- a correcao teria criado um buraco maior que o que
   fechou.

2. **`fator_cotacao_mudou` era calculado e jogado fora.** Virou evidencia, no mesmo nivel
   de `classes_confirmam`: a empresa trocava de unidade PORQUE tinha acabado de agrupar.
   Nao ha risco de falso positivo por essa via -- unidade mudando sem evento deixa o preco
   por acao continuo, a razao fica perto de 1 e a linha nem vira candidata. Caso que
   revelou: CBMA4 em 02/07/2007, R$0,325 -> R$0,65 por acao, razao 0,5 com erro **zero**,
   rebaixada a 'baixa' porque a quantidade nao confirmou.

3. **`preco_confiavel` vetava sozinho** -- o mesmo defeito estrutural que `razao_redonda`
   tinha. Agora razao extrema mais (classes confirmam OU unidade mudou) supera o veto do
   tick. Nao existe artefato de tick que gere razao de 1:900 com erro de 0,03% e as duas
   classes concordando no mesmo pregao. Casos: JBDU3/JBDU4 em 30/04/2007 e TEKA3/TEKA4 em
   01-05/06/2009, grupamentos de ~900:1 que deixavam +90.000% de retorno falso na serie.
   Conservador de proposito: IRBR3 (0,93 -> 22,06) NAO e promovida, porque tem classe
   unica e a unidade nao mudou -- continua no balde de centavos, declarada.

**Resultado medido (A/B contra a linha de base, mesmo dado):**

| | antes | depois |
|---|---|---|
| quedas < -45% | 446 | **435** |
| altas > +90% | 648 | **623** |
| saltos resolvidos | -- | **38** |
| saltos novos | -- | **2** |

Os 2 novos sao FCAP3 e FCAP4 em 02/05/2007: razao 0,309 contra 1/3, erro de 7,3%. Fica
descartado de proposito -- acima da tolerancia mesmo com evidencia, e a regra 11 do plano
diz que ajuste sem evidencia e pior que ajuste nenhum.

**Testes**: 43 passando (eram 32). `tests/test_unidade_cotacao.py` trava as cinco viradas
reais, o fato de a leitura ingenua ser plausivel (e por isso passar batido), e a regra de
que o corte de centavos olha a cotacao.

### 10/09/2026 - Etapas 2 a 4: universo, identidade e sucessao

**ETAPA 2 -- universo e regime de negociacao.**

O filtro `codbdi = '02'` apagava a empresa exatamente quando ela quebrava. Confirmado na
tabela oficial da B3 ("CODBDI TABLE", layout do COTAHIST, rev. 01 de 17/04/2017):

| codigo | significado oficial | decisao |
|---|---|---|
| 02 | ROUND LOT | normal |
| 05 | BMFBOVESPA REGULATIONS SANCTION | admitido |
| 06 | STOCKS OF COS. UNDER REORGANIZATION | admitido |
| 07 | EXTRAJUDICIAL RECOVERY | admitido |
| 08 | JUDICIAL RECOVERY | admitido |
| 09 / 11 | TEMPORARY ESPECIAL MANAGEMENT / INTERVENTION | admitidos (nao ocorrem hoje) |
| 58 | OTHERS | admitido |
| 10 | RIGHTS AND RECEIPTS | **fora** -- nao e a acao |
| 12 / 14 | REAL ESTATE FUNDS / INVESTMENT CERTIFICATES | fora (decisao do Joao: sem ETF) |
| 22, 34/35/36, 96 | bonus, BDR (DRN/DRE), fracionario | fora |

A mesma consulta confirmou de quebra a Etapa 1: **FATCOT -- "'1' = UNIT QUOTE, '1000' =
QUOTE PER LOT OF ONE THOUSAND SHARES"**, exatamente o que a auditoria tinha inferido do
dado.

**Regra de admissao, aplicada antes de admitir qualquer codigo**: so entra o codbdi para
o qual, nos tickers que transitam de 02 para ele, o ISIN permanece o mesmo e o preco e
continuo. Medido: 07, 08, 58 e 05 tem 100% de ISIN identico. O codigo 10 reprova -- 0% de
ISIN identico e razao mediana de 0,03. E outro papel.

Resultado: **papeis truncados 108 -> 34**, base de 1.678.985 para 1.761.012 linhas.
AMER3, LIGT3, OIBR4, RSID3, AMBP3, PCAR3 e BRKM5 passaram a chegar ao ultimo pregao.
AMER3, que parava em 19/01/2023 -- o dia seguinte a fraude --, agora vai ate hoje.

Custo declarado: **176 saltos residuais novos**, quase todos grupamento em papel de
centavos dentro de recuperacao judicial (LUPA3 1:290, AMER3 1:140, OGXP3 1:100, OSXB3
1:100). Nao sao regressao -- sao linhas que antes nem existiam. No regime **normal** os
saltos cairam de 1.094 para 1.040. Esses ficam declarados para a Etapa 5, que traz
gabarito de evento anunciado: pela regra 11, ajustar sem evidencia e pior que nao ajustar.

**ETAPA 3 -- reingestao da CVM e securities master.**

`ingest/cvm.py` reconstruiu `cvm_cadastro` (2.677 companhias) e `cvm_fca_valores`
(13.066 linhas, 2010-2026).

`master/identidade.py` foi estendido para consolidar as **tres pontes que estavam soltas**
-- havia tres resolucoes de CNPJ no repo e nenhum lugar unia todas; o painel usava duas,
o identidade.py usava outra. Agora ha uma so, com prioridade declarada e registrada em
`fonte_do_vinculo`:

| prioridade | fonte | tickers | pregoes |
|---|---|---|---|
| 1 | FCA da CVM (oficial, datado) | 609 | 1.397.612 |
| 2 | ponte B3/ISIN (com guarda de nome) | 329 | 228.713 |
| 3 | irmao de mesmo emissor de ISIN | 29 | 14.363 |
| 4 | crosswalk humano versionado | 0 | 0 |
| -- | **nao resolvido** | 198 | 122.636 |

Cobertura de CNPJ: **93,0% dos pregoes**. O resto vai para `crosswalk/pendentes_identidade.csv`.

**O limite e estrutural, nao de esforco**: o campo `Codigo_Negociacao` do FCA esta VAZIO
de 2010 a 2017 -- a CVM so passou a preencher em 2018. Dos 198 pendentes, **148 morreram
antes de 2018**. Nao ha fonte automatica para eles; pela regra 6 do projeto viram decisao
humana em `crosswalk/identidade.csv`, com evidencia por linha. O README do diretorio
avisa: nunca preencher por semelhanca de nome -- "KLABIN S/A" casa com tres empresas na
base da CVM, duas canceladas, e foi esse tipo de casamento que deixou a ABEV3 treze anos
sem dividendo.

**ETAPA 4 -- sucessao.** `master_sucessao` (808 linhas) encadeia ticker por CNPJ e pegou
todos os casos-teste da auditoria: ELET3 -> AXIA3 (Eletrobras -> Axia Energia, o caso que
a heuristica de nome nao achava), TRPL4 -> ISAE4, EMBR3 -> EMBJ3, RRRP3 -> BRAV3,
BVMF3 -> B3SA3, VIIA3 -> BHIA3, GOLL4 -> GOLL54, MRFG3 -> MBRF3, SUZB5 -> SUZB3.

Verificacao das duas chaves, feita antes de desenhar: o emissor do ISIN sobrevive a
conversao de classe (SUZB -> SUZB, GOLL -> GOLL) mas **nao** a troca de nome (EMBR -> EMBJ,
ELET -> AXIA, TRPL -> ISAE, BVMF -> B3SA). O CNPJ do FCA faz o contrario. As duas sao
complementares e nenhuma basta sozinha -- por isso as duas entram, com a continuidade de
pregao corroborando.

### 10/09/2026 - Etapas 6 e 7: o retorno vira a primitiva, e a saida do papel

**ETAPA 6 -- inversao de quem e o dado primario.**

Ate aqui a base guardava preco ajustado por fator acumulado RETROATIVO. Quando um evento
novo acontece hoje, todo o passado da serie muda: o preco ajustado de 2010 lido em marco
nao e o mesmo lido em setembro. Backtest rodado duas vezes dava numero diferente, e nao
havia como saber se a diferenca era o codigo ou o dado.

O desenho do CRSP, a base que a literatura usa, e o inverso -- o RETORNO e a primitiva:

    R(t) = [ P(t) x F(t) + D(t) ] / P(t-1) - 1

depende so de t e t-1. Nenhum evento posterior entra na conta. Entao o retorno de ontem
nunca muda por causa de um evento de hoje, e a serie vira append-only.

`acoes_diario` ganhou `retorno_qtd` e `retorno_total`. As tres series de preco continuam
lado a lado (regra 7, "nao existe o preco"); o que mudou foi a hierarquia -- preco
ajustado passou a ser vista do retorno, e nao o contrario.

A expressao virou a constante `painel.SQL_RETORNOS`, e o teste importa DAQUI. Teste que
reimplementa a formula nao prova nada sobre o pipeline.

**`tests/test_serie_append_only.py`** monta uma serie sintetica num DuckDB em memoria
(nunca toca o warehouse) e trava tres coisas:
- acrescentar um evento 3:1 em 09/01 **nao altera** nenhum retorno anterior;
- o preco ajustado **muda** com o evento novo -- documentado de proposito, porque e o
  comportamento que nao da para evitar e a razao de o retorno ser a primitiva;
- no dia ex do 2:1 o retorno e ZERO, nao -50%.

**ETAPA 7 -- motivo de saida e retorno de delisting.**

669 dos 1.035 papeis ON/PN morrem, 25% do volume. Se a serie so termina, a carteira
"vende no ultimo preco" e nunca leva a perda final -- o vies que Shumway documentou no
CRSP e cuja correcao mudou a magnitude do efeito tamanho na literatura.

O `destino` do `master_empresa` foi refinado contra os motivos que a CVM de fato registra:

| destino | criterio | empresas |
|---|---|---|
| fechou_capital | CANCELAMENTO VOLUNTARIO, ou Instrucao CVM **361/02** (a que rege a OPA) | 595 |
| cancelamento_de_oficio | CANCELAMENTO DE OFICIO (Instr. 287/98, 29/84) | 349 |
| incorporada | ELISAO POR INCORPORACAO | 290 |
| liquidada | ELISAO POR EXTINCAO / LIQUIDACAO | 29 |
| cancelada_outro | reenquadramentos antigos (Instr. 03/78, 229/95) | 598 |
| ativa | -- | 669 |

**Convencao, escrita no codigo e aqui** (decisao do Joao em 09/09):
- liquidada e cancelamento de oficio -> **-100%**. Nao ha sucessor nem oferta.
- incorporada e fechou capital -> ultimo preco, com `delisting_observado = FALSE`. O
  acionista recebeu dinheiro ou acao do comprador; QUANTO exige ler o edital caso a caso,
  e isso ficou para outro projeto. O campo esta pronto para receber o valor observado
  depois, sem refazer nada.
- **sucessao de ticker NAO e delisting.** EMBR3 vira EMBJ3 e a posicao continua; marcar
  perda ali inventaria um prejuizo que nao houve. Verificado: EMBR3, TRPL4 e ELET3 saem
  como `sucessao_de_ticker`, e VALE3 e AMER3, vivas, saem sem motivo.

Resultado: 59 papeis com -100% (53 de oficio, 6 liquidados), 68 marcados como sucessao,
203 fechamento de capital, 76 incorporadas, 187 desconhecido. Os 192 em que a empresa
segue registrada mas o papel parou saem como `papel_encerrado_empresa_ativa` -- conversao
de classe, saida da B3 sem cancelar registro, migracao de segmento.

`delisting_observado` existe justamente para dizer que o numero e **convencao, nao
medida** -- regra 8 do projeto.

### 10/09/2026 - Etapa 5 e 8: provento por CNPJ, e o residuo classificado

**ETAPA 5 -- o dividendo sempre esteve la, atras de outro nome.**

O casamento por nome deixava ABEV3 com ZERO provento em 13 anos e KLBN3/KLBN4 com zero em
21. A causa nao era falta de dado: era a chave.

Testado ao vivo no endpoint da B3:

    "AMBEV S/A"    ->   0 registros      "AMBEV S.A."   ->  39 registros
    "KLABIN S/A"   ->   0 registros      "KLABIN SA"    -> 219 registros
    "VALE S.A."    ->   0 registros      "VALE"         -> 152 registros
    "TIM S.A."     ->   0 registros      "TIM"          ->  34 registros

**Nenhum campo sozinho acerta.** ABEV e KLBN so respondem ao `companyName` do cadastro da
B3; VALE e TIMS so ao `tradingName`. E o `nome_res` do COTAHIST, unica fonte usada antes,
vem truncado em 12 caracteres. Solucao: consultar TODOS os nomes candidatos de cada CNPJ
(cadastro da B3 pelos dois campos, mais os nomes historicos do COTAHIST) e unir,
deduplicando por (cnpj, classe, data com, valor, tipo). 996 nomes para 576 CNPJs.

Cada provento passou a carregar o **CNPJ**, e o painel casa por (CNPJ, sufixo). Fallback
declarado por nome para os 198 tickers cujo CNPJ ninguem resolveu -- quase todos mortos
antes de 2018, onde o nome ainda e a unica chave que existe.

| ticker | antes | depois |
|---|---|---|
| ABEV3 | **0** | 32 |
| KLBN4 | **0** | 70 |
| KLBN3 | **0** | 70 |
| KLBN11 | 0 | 47 |

Cobertura de provento por volume: **91,0% -> 93,3%**.

**DOIS ERROS PAGOS NESTA ETAPA, e os dois valem mais que o resultado:**

1. **Trinta minutos de coleta jogados fora por erro de schema.** A rodada terminou os 926
   nomes e morreu na ultima linha: `replace_partition` faz INSERT em tabela existente, e
   a `b3_proventos` antiga nao tinha as colunas novas. Agora o bruto vai para
   `data/raw/b3_proventos/*.parquet` ANTES do banco, e o modulo recria a tabela quando o
   schema muda. Falha de gravacao agora custa um `read_parquet`, nao outra coleta.

2. **A B3 e a CVM escrevem o mesmo CNPJ de formas diferentes.** A B3 devolve
   `7526557000100`, sem o zero a esquerda; a CVM devolve `07.526.557/0001-00`. O
   casamento falhava CALADO para toda empresa cujo CNPJ comeca com zero -- e a segunda
   rodada trouxe a Klabin (CNPJ 896...) e deixou a Ambev (075...) de fora **outra vez,
   pelo motivo errado**. Corrigido com `lpad(..., 14, '0')`.

**Descoberta de identidade:** a Ambev sao DOIS CNPJs. Companhia de Bebidas das Americas
(02.808.708/0001-07, cancelada em 12/12/2013 por cancelamento voluntario) e Ambev S.A.
(07.526.557/0001-00, ativa). AMBV4 encerra em 08/11/2013 e ABEV3 estreia em 11/11/2013, o
pregao seguinte. E sucessao COM TROCA DE CNPJ -- o caso que nenhuma chave automatica liga,
porque nem o CNPJ e estavel ali. Virou a primeira linha de `crosswalk/sucessao.csv`, com
a evidencia da CVM escrita na propria linha.

**ETAPA 8 -- o residuo, classificado por causa.**

`master/auditoria_tratamento.py --residuo` para de contar salto e passa a nomear causa:

| causa | saltos | papeis | o que resolve |
|---|---|---|---|
| papel de centavos | 734 | 200 | gabarito de evento anunciado -- abaixo de R$1 o tick domina e fracao redonda nao prova nada |
| dia ex movimentado | 367 | 206 | contagem de acoes da CVM (MGLU3 8:1 erra 5,2%) |
| regime especial | 85 | 35 | linhas recuperadas na Etapa 2; antes nem existiam |
| nao classificado | 25 | 24 | inclui a queda REAL -- e para ficar assim |

Tambem: `ver.py` ganhou os blocos de regime, saida do papel e retorno; o README foi
corrigido (falava de `precos_diarios` e `master.precos`, que nao existem mais);
`master/precos.py` foi marcado como MODULO MORTO no topo -- apagar exige o OK do Joao.

**ESTADO FINAL DAS OITO ETAPAS (A/B contra a linha de base congelada):**

| metrica | antes | depois |
|---|---|---|
| linhas | 1.678.985 | **1.761.012** |
| tickers | 1.129 | **1.146** |
| papeis truncados | 108 | **34** |
| cobertura de provento (volume) | 91,0% | **93,3%** |
| cobertura de CNPJ (pregoes) | 92,2% | **93,1%** |
| testes | 32 | **62** |

Saltos residuais: 59 resolvidos, 176 novos -- e os novos sao a populacao recuperada na
Etapa 2 (grupamento de centavos em recuperacao judicial), nao regressao. No regime
**normal** os saltos cairam de 1.094 para 1.040.

### 10/09/2026 - Pesquisa na literatura, e o que dela virou codigo

Joao pediu: pesquisar a fundo como a literatura e a industria tratam esses problemas, e
aplicar o que servir. Quatro buscas e dois documentos primarios depois, tres coisas
entraram na base e uma mudou a expectativa do que e "bom o suficiente".

**1. O QUE A LITERATURA BRASILEIRA DE FATO FAZ -- e a barra e mais baixa do que parecia.**

O paper mais proximo do nosso problema e de 2026: "Lottery-type stocks in Brazil: Evidence
from a survivorship-bias-corrected universe" (Revista Brasileira de Financas, 24, 2026).
Ele constroi exatamente o universo que estamos construindo: COTAHIST oficial, 1.097
tickers, dez/1999 a dez/2024, incluindo papel deslistado. Filtros: acao domestica ON/PN/
unit, minimo de 10 pregoes no mes, preco de fechamento positivo, minimo de 12 meses de
retorno; unidade de analise e o EMISSOR, ficando com a classe mais liquida quando ha mais
de uma.

E a secao 3.3, "Data limitations and scope", diz com todas as letras:

> "The COTAHIST series are nominal closing prices and carry **no adjustment for corporate
> actions** -- splits, reverse splits, stock dividends, or interest on own capital -- and
> monthly returns are computed directly from consecutive closes as r_t = P_t/P_{t-1} - 1.
> **I do not implement a formal split adjustment**, and I have not run a sensitivity
> analysis to corporate events."

Ou seja: um paper publicado, revisado, que quantifica survivorship bias em +1,90 p.p. ao
mes no alfa de loteria, **nao ajusta evento corporativo nenhum**. Nossa base ja esta acima
disso. Isso nao e desculpa para parar -- e a referencia honesta de onde a barra esta.

O paper tambem da uma convencao de universo que vale adotar quando formos rodar teste:
agregar por EMISSOR e ficar com a classe mais liquida do mes. Fica anotado; nao muda a
base, muda a camada de analise.

**2. QUANTIDADE DE ACOES DA CVM COMO TERCEIRA EVIDENCIA (aplicado).**

O criterio padrao de deteccao de evento de quantidade e a relacao que qualquer manual
descreve: se as acoes multiplicam por N, o preco divide por N, e o valor de mercado nao
muda. Ou seja, **a contagem de acoes e uma segunda medida do mesmo fator** -- e vem da
CVM, nao da B3, entao e imune aos dois erros que sobravam no detector: o tick de R$0,01 em
papel de centavos e o movimento do proprio dia ex.

Implementado em `master/eventos.py::_razao_de_acoes`, sobre o `cvm_capital_social` (FRE,
2010-2026) que ja estava no disco. Verificado antes de construir:

| ticker | evento | erro do preco | razao de acoes na CVM |
|---|---|---|---|
| MGLU3 09/2017 | desdobramento 8:1 | 5,2% (reprovava) | **8,81** |
| MGLU3 08/2019 | desdobramento 8:1 | 5,7% (reprovava) | **8,52** |
| CASH3 09/2021 | desdobramento 6:1 | 7,8% (reprovava) | **6,36** |
| TRPL4 2018/19 | desdobramento 4:1 | -- | **4,000** exato |
| IRBR3 2019 | desdobramento 3:1 | -- | **3,000** exato |

Tres regras novas, nesta ordem de forca:
- `acoes_confirmam` -- a razao de acoes bate com o fator dentro de 15%. Folga larga de
  proposito: o FRE e anual e mistura o evento com emissao e recompra do mesmo ano. O que
  ele oferece nao e precisao, e INDEPENDENCIA.
- `TOLERANCIA_COM_ACOES = 10%` -- quando a CVM confirma, o preco so precisa ser
  aproximadamente consistente. Nos outros niveis a fracao redonda e toda a prova que
  existe; aqui o evento ja foi medido por fora.
- a confirmacao da CVM **supera o veto de papel de centavos** sozinha: a CVM nao sabe nada
  sobre o tick de R$0,01 da B3.

**A trava que valida o desenho**: AMER3 (queda real de 77%), PCAR3 (cisao do Assai) e a
COVID na PETR4 tem razao de acoes de **1,00** -- nenhuma emissao aconteceu, porque nenhum
evento de quantidade aconteceu. Sem confirmacao nao ha folga, e os tres continuam de fora
mesmo com erro de preco perto do limite. Virou teste.

Resultado: 165 candidatos confirmados pela CVM; confianca alta de 1.879 para 1.917.
Residuo de saltos **1.211 -> 1.153** (centavos 734 -> 690, dia ex 367 -> 353).

**3. RETORNO DE DELISTING: A LITERATURA IMPUTA -30%, NAO -100% (aplicado).**

Shumway (1997), "The Delisting Bias in CRSP Data", Journal of Finance: delisting por
desempenho ruim e surpresa, e o retorno final costuma faltar justamente ali -- delisting
por fusao ou migracao raramente falta. Ele mediu os casos em que o retorno EXISTIA e usou
a media para imputar nos que faltavam: **-30%**. Shumway e Warther (1999) estimam **-55%**
para o Nasdaq -- mercado de empresa menor e mais fragil, e a correcao fez o efeito tamanho
no Nasdaq desaparecer.

Nossa convencao anterior, -100%, era mais extrema que a literatura inteira. Mas trocar por
-30% tambem seria arbitrar: o -30% americano embute a venda no mercado de balcao, que para
acao cancelada no Brasil simplesmente nao existe.

Entao a base passa a entregar **as duas**, lado a lado, como ja faz com preco:
- `retorno_delisting` = -0,30 (Shumway 1997, o numero que um paper da SSRN tera usado)
- `retorno_delisting_conservador` = -1,00 (a posicao virou po)

Nenhuma foi observada -- `delisting_observado` segue FALSE nas duas. Qualquer resultado
sensivel a essa escolha tem que reportar as duas versoes.

**4. O QUE A PESQUISA NAO RESOLVEU.** Nao existe fonte gratuita e completa de evento
corporativo para empresa que saiu da bolsa no Brasil. O que aparece e pago (UP2DATA da
B3, Economatica, Bloomberg) ou incompleto (APIs que cobrem so empresa viva). O caminho que
sobra e o gabarito de evento anunciado da B3 para quem ainda esta listado, mais crosswalk
humano para o resto -- que e o desenho que ja temos.

### 10/09/2026 - Painel por emissor: a unidade em que o teste se faz

Joao autorizou implementar se melhorasse o uso da base para testar estrategia. Melhora, e
por uma razao anterior a "o paper faz assim".

**O problema.** `acoes_diario` e por PAPEL, e tem que ser -- e o papel que se compra, e o
custo, o lote e o spread sao dele. Mas teste de cross-section nao se faz por papel, e sim
por EMPRESA. ON e PN da mesma companhia nao sao dois ativos independentes: num sort por
tamanho ou valor, ITUB3 e ITUB4 entram como duas observacoes da MESMA firma. Isso infla o
N efetivo, quebra a independencia que o erro-padrao de Fama-MacBeth assume, e deixa uma
empresa ocupar duas vagas no mesmo decil.

**O tamanho do problema, medido**: **30,7% dos meses-empresa da nossa base tem duas
classes negociando**. Sem agregar, quase um terco das observacoes seria empresa duplicada.
No Brasil isso pesa muito mais que nos EUA.

**`emissor.py` -> tabela `emissor_mensal`**: 75.420 linhas empresa-mes, 572 emissores,
01/2005 a 09/2026. Uma linha por (CNPJ, mes), com o retorno composto a partir da primitiva
diaria, valor de mercado da empresa, liquidez, regime, motivo de saida e as duas
convencoes de retorno de delisting.

**ONDE DISCORDAMOS DO PAPER DA RBFin, DE PROPOSITO.** Ele escolhe a classe mais liquida DO
MES e usa o retorno DAQUELE MES. E look-ahead, e do tipo pior: a escolha correlaciona com
o resultado, porque a classe que teve a noticia foi a que negociou mais naquele mes. Aqui
a classe sai da liquidez dos **12 meses anteriores**.

**A janela de 12 meses nao veio da teoria, veio de medir.** Com janela de um mes:

| empresa | trocava de classe em |
|---|---|
| IGUACU CAFE | 50,9% dos meses |
| ALFA HOLDING | 49,8% |
| TELEMIG CL | 42,9% |

As duas classes mal negociam, entao "a mais liquida" alterna por acaso e produz um giro
que nenhuma carteira real suportaria. Com 12 meses o giro cai de **4,11% para 1,75%** dos
meses-empresa, e a ITAUSA -- que oscilava entre ITSA3 e ITSA4 -- fica em ITSA4 nos 261
meses. Janela longa e sticky por construcao, sem precisar de regra de buffer.

**O que sobra de troca esta inteiro em microcap, verificado e nao suposto:**

| faixa de troca | empresas | volume mensal mediano |
|---|---|---|
| menos de 5% dos meses | 491 | **R$ 54,6 milhoes** |
| 5% a 20% | 34 | R$ 48,7 mil |
| 20% ou mais | 11 | **R$ 11,6 mil** |

Quatro mil vezes menos liquido. Qualquer filtro de negociabilidade tira esses papeis, e a
coluna `trocou_de_classe` deixa o custo a vista para quem nao filtrar.

**Conferencia da escolha nos papeis conhecidos**: BBDC4, PETR4, ITUB4, GGBR4, KLBN4 e
ITSA4 -- todos a classe mais liquida. ELET6 dando lugar a ELET3 ao longo do tempo, e VALE5
em 2005-2009, que era mesmo a mais liquida na epoca.

**O modulo NAO filtra.** O paper exige minimo de 10 pregoes no mes e 12 meses de
historico; aqui isso vira COLUNA (`pregoes_no_mes`) e o filtro fica com quem roda o teste
-- regra 6 do projeto. Filtro embutido em base e filtro que ninguem ve.

**Ligado na rotina diaria**: `atualizar.py` reconstroi `emissor_mensal` junto do painel
diario. Se um nao acompanhar o outro, um teste rodado amanha usa universo de ontem sem
ninguem perceber.

Testes: 68 -> 71.

### 10/09/2026 - Validacao externa contra o NEFIN, e o bug que ela achou

Ate aqui a garantia da base era INTERNA: consistencia, nao acuracia. Nada nunca tinha sido
conferido contra fonte independente. O modulo que fazia isso (`master/auditoria_precos.py`)
estava morto desde a limpeza de 02/09, porque dependia de `precos_diarios` e
`nefin_fatores` -- duas tabelas apagadas.

`ingest/nefin.py` reingerido: 6.321 dias de fatores (Rm-Rf, SMB, HML, WML, IML e taxa
livre), 2001 a 07/2026, mais aluguel e short interest agregados.

**O TESTE.** Nao e reproduzir a carteira do NEFIN -- universo e ponderacao sao diferentes
e a comparacao seria injusta. E comparar a NOSSA serie crua e a NOSSA serie ajustada
contra a mesma referencia externa: se ajustar nao aproximar, o ajuste nao esta fazendo
nada. Carteira de teste: top 150 por liquidez mediana de 12 meses, recomposta todo mes,
selecionada com informacao ate o mes anterior (senao a propria auditoria teria look-ahead).

| serie | correlacao com o mercado NEFIN | desvio do acumulado |
|---|---|---|
| **crua** (sem ajuste nenhum) | **0,5381** | +846,7 p.p. |
| ajustada por quantidade | **0,9247** | -583,8 p.p. |
| **retorno total** | 0,9143 | **-139,2 p.p.** |

Ajustar quase **dobra** a correlacao (+0,3866). E o dividendo se confirma sozinho: num
acumulado de 820%, a serie de retorno total fica a -139 p.p. da referencia contra -584 da
serie sem provento -- 445 pontos de aproximacao que so o provento explica.

O modulo tambem excluiu sozinho 2 pregoes em que o proprio NEFIN esta errado (13 e
16/06/2025, |retorno| > 10%), usando a regra ja registrada no bug 8. Referencia externa
tambem se audita.

**O BUG QUE A VALIDACAO ACHOU -- e ele era invisivel por dentro.**

Nos "piores dias" apareceu 22/12/2014 com erro de 6,15 p.p. na serie JA AJUSTADA. Fui ver:
**OIBR4, R$1,00 -> R$9,50, +850%, com R$20 milhoes de volume e sem evento marcado.**

Diagnostico:

| ticker | razao | fator | erro | veredito |
|---|---|---|---|---|
| OIBR3 | 0,11165 | 1/9 | **0,49%** | alta |
| OIBR4 | 0,10526 | 1/9 | **5,26%** | **descartado** |

O MESMO grupamento 1:9, no mesmo pregao, nas duas classes da mesma empresa. A ON passou; a
PN foi reprovada por **0,26 ponto percentual**.

O defeito era de desenho, e era meu: `classes_confirmam` so RELAXAVA a tolerancia -- cada
classe ainda tinha que provar o fator com o proprio preco, e preco de classe menos liquida
e mais ruidoso. Mas **grupamento e fato da EMPRESA, nao do papel**: se a ON foi agrupada
1:9, a PN foi agrupada 1:9.

`master/eventos.py::herdar_entre_classes` -- quando a irma ja provou o evento com
confianca alta ou media, o fator dela vale para esta classe tambem. Conservadora de
proposito: a razao de preco DESTA classe tem que ser compativel com o fator herdado (20%),
senao seria carimbar evento que o preco dela nao viu; e a linha ja tinha que ser candidata,
entao nao se inventa evento em dia parado.

Resultado: **70 fatores herdados**, confianca alta de 1.917 para 1.987, correlacao de
0,9232 para 0,9247. A trava continua: AMER3, PCAR3 e a COVID na PETR4 seguem descartadas.

Tres testes novos travam a regra, incluindo o caso em que a heranca NAO pode alcancar
(PN que caiu 2% num dia em que a ON foi agrupada 1:9 -- aplicar 1/9 ali criaria -89% do
nada). Testes: 71 -> 74.

**A licao, e ela vale mais que o conserto**: esse erro estava ha meses na base, num papel
liquido e conhecido, e nenhuma auditoria interna o pegou -- porque por dentro a serie era
coerente consigo mesma. So a comparacao com um dado que nao e nosso mostrou. Auditoria
interna acha inconsistencia; so referencia externa acha erro sistematico.

---

## 3. Estado atual da base

**Arquivo**: `C:\Users\joaoz\quantbr\data\warehouse\quantbr.duckdb` (386 MB)
**Brutos**: `C:\Users\joaoz\quantbr\data\raw\` (1 GB, nunca editados)

### Tabela em uso: `acoes_diario`

1.678.985 linhas, 1.129 papéis, 03/01/2005 a **09/09/2026**.
Eventos de quantidade aplicados: **1.766 dias em 605 papéis** (09/09/2026).

| Classe | Papéis | Linhas |
|---|---|---|
| ON | 648 | ~1.072.000 |
| PN | 387 | ~543.000 |
| Unit/ETF/FII | 94 | ~61.000 |

Colunas: `ticker`, `data`, `classe`, `empresa`, `isin`, **`fechamento`** (nominal),
`abertura`, `maxima`, `minima`, `volume`, `quantidade`, `negocios`,
**`fechamento_ajustado`** (desdobramento/grupamento), `fator_acum`, `tem_evento`.

Warehouse em **245 MB** (era 382 MB antes da exclusao).

Fora do escopo por decisão: BDR (1.052 papéis, empresa estrangeira) e mercado
fracionário (duplicaria a série do mesmo papel).

### Outras tabelas

Só `b3_cotahist` (3,46M linhas), o landing bruto da B3 de onde `acoes_diario` é derivada.
Todo o resto foi excluído em 02/09/2026.

---

## 4. Inventário de código

20 arquivos Python, ~2.500 linhas.

| Arquivo | Função |
|---|---|
| `config.py` | caminhos centrais; nenhum módulo inventa caminho |
| `warehouse.py` | conexão DuckDB com espera de lock, partição idempotente |
| `painel.py` | constrói `acoes_diario` |
| `atualizar.py` | rotina diária incremental |
| `ver.py` | raio-x da base |
| `ingest/cotahist.py` | parser do COTAHIST (layout 245 chars) |
| `ingest/nefin.py`, `bcb.py`, `cvm.py`, `b3_empresas.py`, `b3_eventos.py` | coletores |
| `ingest/base.py` | download com retry, checagem de JSON |
| `ingest/canario.py` | verifica as fontes (roda no CI) |
| `master/identidade.py` | securities master por CNPJ |
| `master/eventos.py` | detector de evento corporativo |
| `master/precos.py` | três séries de preço |
| `master/auditoria*.py`, `calibracao.py` | auditorias |
| `tests/` | 20 testes |

---

## 5. Decisões tomadas e por quê

| Decisão | Motivo |
|---|---|
| COTAHIST como fonte primária, não yfinance | yfinance apaga quem saiu da bolsa; a literatura estima 5-15% a.a. de inflação de retorno por survivorship |
| Python 3.12, não 3.14 | 3.14 não tem wheels de boa parte do stack quant |
| DuckDB, arquivo único local | sem servidor, SQL completo, colunar; certo para casa de uma pessoa |
| Detectar eventos do COTAHIST, B3 como gabarito | a B3 apaga o histórico de quem saiu; o COTAHIST não apaga ninguém |
| CNPJ como chave de identidade | nome muda, ticker muda, ISIN muda; CNPJ não |
| Três séries de preço, nenhuma padrão | não existe "o preço"; a escolha depende do teste |
| Protocolo estatístico antes dos agentes | agentes rodando 24/7 são máquina de p-hacking; ligar antes do protocolo queima a confiança no sistema inteiro |
| Não apagar as tabelas inertes | reconstruir custa 50 min; o ganho seria só disco |
| Arquivo diário da B3 na atualização | 576 KB contra 80 MB para a mesma informação |
| S4U na tarefa agendada | roda sem login e sem armazenar senha |

---

## 6. Bugs e armadilhas encontrados

Esta seção é o ativo mais valioso do documento: todo item aqui é um erro **real** que
aconteceu, quase sempre silencioso — o pipeline continuava rodando e entregando número
errado.

### Nas fontes externas

| # | Achado |
|---|---|
| 1 | **BCB devolve HTTP 200 com corpo HTML** de erro, intermitente. Duas séries diárias sumiram caladas na primeira rodada |
| 2 | SGS limita série diária a 10 anos por requisição (HTTP 406) |
| 3 | B3 `GetInitialCompanies` aceita `pageSize` até 120; acima disso devolve corpo vazio com status 200 |
| 4 | **O cadastro da B3 só tem empresa viva**: 3.506 registros, todos status "A". A CVM mantém as 1.912 canceladas |
| 5 | Consulta por prefixo na B3 casa errado: pedir `TRPL` devolve um **fundo imobiliário** (FII TRPL), não a CTEEP |
| 6 | `Codigo_Negociacao` do FCA está vazio em metade das linhas e às vezes traz lixo (`4030`, `NÃO HÁ`) |
| 7 | **A B3 usa duas convenções no mesmo campo**: desdobramento em percentual, grupamento como razão direta |
| 8 | **O NEFIN tem erro de dado**: mercado +13,47% em 13/06/2025, SMB +23,37% em 12/06/2025. A bolsa não fez isso |
| 9 | A API de índices da B3 ignora o parâmetro de ano: **não há carteira histórica gratuita** |
| 10 | 7 linhas do COTAHIST com preço inconsistente (máxima < mínima), 4 delas em 08/06/2020 |

### No nosso código

| # | Achado |
|---|---|
| 11 | DuckDB aceita um escritor por vez; coletores em paralelo se atropelam |
| 12 | `cad_cia_aberta` é histórico de registro, não uma linha por empresa. Sem deduplicar, a Vibra saía como 'ativa' e 'cancelada' ao mesmo tempo |
| 13 | **Detector com denominador 20 classificou o crash da COVID na PETR4 como desdobramento**, confiança alta. Com denominador 20 as frações ficam tão densas que qualquer razão cai a 2% de alguma |
| 14 | Ao corrigir para denominador 4, quebrou o inverso: `Fraction(0,02).limit_denominator(4)` é **zero**, e grupamento de 50:1 sumia (ASTA4 virou +4.900%) |
| 15 | Quantidade e financeiro não confirmam evento extremo (o papel muda de regime de liquidez). BRPR3 tinha erro de 0,003% e caía em "baixa" |
| 16 | Filtrar a referência por "\|retorno\| > 10%" excluía outubro de 2008 e março de 2020 — crise real. O critério certo é discordância, não magnitude |
| 17 | Merge de proventos duplicava linhas quando duas datas-com caíam no mesmo pregão seguinte |
| 18 | "Top 150 por liquidez" em 2005 incluía papel com R$1.273 de volume diário — não havia 150 ações líquidas no Brasil naquele ano |
| 19 | **O detector inventava fração e apagava crash real.** Com denominador 4 solto em razão alta, a queda de 77% da AMER3 em 12/01/2023 (colapso da Americanas) casou com 13/3 = 4,3333, erro de 1,8%, confiança ALTA — e sumiu da série ajustada. A cisão do Assaí (PCAR3, 01/03/2021) virou "desdobramento 7/2". Corrigido em 09/09/2026 restringindo razão ≥ 3 a inteiro |
| 20 | **Ajuste com fator quase certo é pior que ajuste nenhum**, porque não deixa rastro: o desdobramento 8:1 da MGLU3 era ajustado por 15/2 = 7,5 e sobrava 6,7% de retorno falso — pequeno demais para aparecer em qualquer varredura por salto |
| 21 | **`PRECO_MINIMO_CONFIAVEL = R$1` exclui justamente quem faz grupamento.** Empresa que agrupa está barata, e é por isso que agrupa. IRBR3 (R$0,93 → R$22,06) e BHIA3 (R$0,50 → R$11,17) caem no balde `preco_de_centavos` e ficam fora do ajuste. 2.057 candidatos ali |
| 22 | **`master/precos.py` está morto** e ninguém notou: lê `eventos_detectados` e `b3_eventos_caixa`, que a limpeza de 02/09 apagou. Quem constrói as séries é `painel.py` |

Os que têm regra fixa viraram teste em `tests/test_deteccao_eventos.py`.

---

## 7. O que está planejado

### Imediato

- Manter este documento a cada avanço
- Usar `acoes_diario` para as primeiras análises (aguardando o João dizer quais)

### Fase 2 — Protocolo de research

O que impede o sistema de se enganar sozinho. Cinco mecanismos, **impostos por
código/hook, não por bom senso do agente**:

1. **Pré-registro**: hipótese vira YAML antes de rodar; hook bloqueia edição depois
2. **Ledger de trials**: todo backtest gravado, inclusive os descartados; o N alimenta o DSR
3. **Vault**: treino / validação / holdout trancado com orçamento de destravamentos
4. **Bateria estatística**: Fama-MacBeth mês a mês + Newey-West, DSR, PBO/CSCV, FDR
5. **Custo e viabilidade**: emolumentos, spread, impacto, teto de ADTV, **aluguel para short**

**Leitura de referência para esta fase** (João mandou em 09/09/2026):
[The Only Way to Become a Good Quant](https://akhaldoun.substack.com/p/the-only-way-to-become-a-good-quant),
Amy Khaldoun. O protocolo de leitura de resultado dela é quase a Fase 2 escrita por outra
pessoa, e vale como checklist: comparar contra o **null certo** (buy-and-hold, aleatório
com mesmo turnover) e não contra zero; **tamanho efetivo de amostra** (10 anos com holding
de 6 meses ≈ 20 apostas independentes, não 2.500 observações); erro padrão do Sharpe
(3 anos e Sharpe 1,0 → IC 95% de −0,4 a 2,4); contar as tentativas; jogar fora os melhores
dias e ver o que sobra; regredir contra fatores conhecidos; **aumentar o custo até a
estratégia quebrar** e reportar esse limiar; regime split. Mais: **arquivo de ideias
mortas** com o porquê de cada uma. O projeto nº 1 da lista dela é exatamente o que estamos
fazendo aqui — dataset limpo de 20 anos com split e dividendo, atacando survivorship.

### Fase 3 — Painel CVM CDA

Portar a ingestão de posse institucional (R → warehouse) e **estender de 2021 a 2026**.
A fonte é mensal e vai até hoje — a parada em 2021 era trabalho manual, não limite do dado.
Confirmado: `cda_fi_202604.zip` existe.

### Fase 4 — Agentes (Claude Agent SDK)

MCP server interno expondo a API do quant. `implementer` e `adversary` primeiro (os dois
que importam), depois `scout` e `librarian` com cron semanal do SSRN.

### Fase 5 — Portfólio, risco e paper trading

Limites pré-trade como bloqueio duro, escada de drawdown, stress. Motor de risco é código
determinístico, sem LLM na alça de controle. Paper trading com 6 meses de track record
antes de capital real.

**Nota regulatória**: gerir dinheiro de terceiros no Brasil exige registro de gestor na
CVM. Até lá, capital próprio. Clube de investimento é o caminho intermediário.

---

## 8. Decisões pendentes do João

| # | Pendência | Contexto |
|---|---|---|
| 1 | **209 emissores sem vínculo CNPJ** | 20% dos pregões de ação, incluindo CSNA3, KLBN4, VALE5. Casar por nome erraria (`KLABIN S/A` casa com três empresas, duas canceladas). Revisão manual uma vez, congelada em crosswalk versionado |
| 2 | **Apagar ou não as tabelas inertes** | Ganho seria só disco |
| 3 | **Primeiro commit** | Repo tem `git init`, zero commits, esperando OK |
| 4 | **Qual análise fazer com `acoes_diario`** | Base pronta e atualizando sozinha |

### Correções conhecidas, mecânicas, ainda não feitas

- ~~Endpoint de proventos errado~~ **RESOLVIDO** (verificado em 09/09/2026): `ingest/proventos.py`
  ja usa o paginado `GetListedCashDividends`; a Petrobras tem 166 registros PN na base
- Aluguel por papel exige o arquivo BTB diário da B3; o NEFIN só dá o agregado
- ~~Recall do detector em 40,6%~~ — a causa foi encontrada e corrigida em 09/09/2026
  (tolerância e denominador por faixa). O que sobra agora tem outras três causas, todas
  listadas na entrada de 09/09: dia ex movimentado, papel de centavos e cisão
