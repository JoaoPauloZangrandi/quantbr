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
`quantbr` criado no GitHub e primeiro commit publicado.
**Nota:** o João escolheu **público** depois de eu apontar que uma casa de research com
capital próprio em vista perde a vantagem quando o método é aberto. Decisão dele,
registrada aqui.
