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
3. **`git pull --rebase` antes de todo push.** O repositório é público e tem dois autores;
   um push forçado apaga trabalho do outro sem aviso.
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
