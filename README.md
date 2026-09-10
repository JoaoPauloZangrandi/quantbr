# quantbr

Casa de research quant em ações brasileiras, operada por agentes de IA.

Não é um robô de trade. É a infraestrutura de uma gestora pequena: um fluxo auditável de
hipóteses testadas (a maioria nulas, e tudo bem), com um protocolo estatístico que o
próprio sistema não consegue burlar, e controles de risco determinísticos.

Plano completo: `~/.claude/plans/queria-estabelecer-um-mini-wise-octopus.md`

## Comece por aqui: `acoes_diario`

Decisao de 02/09/2026: o escopo de trabalho e UMA tabela, preco de fechamento **nominal**
(sem ajuste nenhum), diario, todas as acoes da B3 de 2005 em diante.

```python
import warehouse
with warehouse.connect(read_only=True) as con:
    df = con.execute("SELECT * FROM acoes_diario WHERE classe IN ('on','pn')").df()
```

1.676.758 linhas, 1.129 papeis, 03/01/2005 a 28/08/2026. Reconstroi com `python -m painel`.

Ressalva que vale ter em mente, medida e nao teorica: preco nominal faz desdobramento
parecer queda. A PETR4 marca -49,5% em 28/04/2008, que foi um desdobramento 2:1 e nao
uma queda. Para nivel de preco, liquidez e volume, tanto faz. Para RETORNO, importa.
O ajuste ja esta no painel: `painel.py` entrega `fechamento_ajustado` e
`fechamento_retorno_total` ao lado do nominal, e desde 10/09/2026 tambem `retorno_qtd` e
`retorno_total` -- que sao a primitiva, nao o preco.

O resto do que esta descrito abaixo continua no warehouse, inerte, sem atrapalhar.

## Estado atual

**Fase 0 concluída.** Repositório, ambiente e coletores de base.
**Fase 1 concluída em substância.** Identidade de empresa no tempo, detecção de eventos
corporativos e as três séries de preço, com auditoria. Pendências honestas na seção final.

| Camada | Situação |
|---|---|
| L0 dados | COTAHIST, NEFIN, BCB, CVM, B3 eventos carregando |
| L0 master | identidade + eventos + preços + auditoria prontos |
| L1 protocolo | pendente (Fase 2) |
| L2 agentes | pendente (Fase 4) |
| L3 risco | pendente (Fase 5) |

## Não existe "o preço"

Regra do projeto, definida explicitamente. `acoes_diario` entrega três séries lado a
lado e **nenhuma é o padrão**. A escolha vira campo obrigatório do pré-registro na L1.

Desde 10/09/2026 a hierarquia mudou: **o retorno é a primitiva** (`retorno_qtd`,
`retorno_total`) e o preço ajustado é derivado dele. O motivo é reprodutibilidade — o
ajuste por fator retroativo faz todo o passado mudar quando um evento novo acontece, e
dois backtests do mesmo código em datas diferentes davam números diferentes. Preço
ajustado serve para desenhar gráfico; retorno serve para calcular.

| Coluna | Quando usar |
|---|---|
| `fechamento` | preço como negociou. Custo de transação, checagem externa, nível nominal |
| `fechamento_ajustado_qtd` | corrigido por desdobramento e grupamento. Default sensato para sinal de preço |
| `fechamento_retorno_total` | com provento. Necessário em posição longa e comparação com índice de retorno total. **Cobertura incompleta**, ver `cobertura_provento` |

## Por que COTAHIST e não yfinance

Quem monta universo com os tickers que existem hoje apagou toda empresa que quebrou,
foi comprada ou saiu da bolsa. A literatura estima 5-15% ao ano de inflação de retorno.

O arquivo anual COTAHIST contém **todo ticker que negociou naquele ano**. Verificado na
ingestão de 2024: AESB3, RRRP3, TRPL3/4, APER3, SEQL3, BAHI3 estão lá; nenhum existe no
yfinance hoje. Entre 14 e 38 ações param de negociar por ano na nossa base, nunca zero.

## Identidade: ticker não é empresa

CNPJ é a chave estável. Nome muda, ticker muda, ISIN muda.

O `master/` descobre a cadeia de sucessão sozinho, empilhando o formulário cadastral da
CVM ano a ano e agrupando por CNPJ. Prova: TRPL4 negocia até 2024-11-14 e ISAE4 começa em
2024-11-18; RRRP3 até 2024-09-06 e BRAV3 a partir de 2024-09-09. Pregões consecutivos.
**43 sucessões confirmadas** — GUAR3→RIAA3, VIIA3→BHIA3, ESTC3→YDUQ3, SSBR3→ALSO3,
QGEP3→ENAT3, BRDT3→VBBR3, entre outras.

## Detecção de evento corporativo

A B3 apaga o histórico de proventos de quem sai da bolsa, então ela não pode ser a fonte
primária. Os eventos são detectados do próprio COTAHIST e a B3 vira **gabarito**.

O discriminante é que desdobramento deixa razão **exata**: 2:1 dá 2,000, enquanto crise
dá 1,69 ou 2,08. Confirmações que sustentam a confiança alta, em ordem de força:

1. **classes cruzadas** — ITUB3 e ITUB4 com a mesma razão no mesmo dia. Mercado não faz isso
2. **razão extrema** — acima de 3x ou abaixo de 1/3 não é movimento de mercado
3. **quantidade e volume financeiro** — informativos só para fator moderado

## Auditoria (roda de verdade, não é enfeite)

```bash
python -m master.auditoria          # cobertura de identidade e sucessões
python -m master.calibracao         # recall e precisão contra o gabarito da B3
python -m master.auditoria_precos   # séries contra o fator de mercado do NEFIN
```

Resultado atual da auditoria de preços, período 2005-2026, 5.324 pregões:

| Série | Correlação com o fator NEFIN |
|---|---|
| crua | 0,8498 |
| ajustada por quantidade | **0,9296** |

O que interessa é o contraste, não o nível: se a série crua batesse igual, o ajuste não
estaria fazendo nada. Nos piores dias o erro cai de 20 pontos percentuais para 0,02.

## Uso

```bash
uv venv && uv pip install -e .

python -m ingest.cotahist 2024 2025 2026   # ano corrente é sempre rebaixado
python -m ingest.nefin
python -m ingest.bcb
python -m ingest.cvm                        # cadastro + FCA (ponte ticker<->CNPJ)
python -m ingest.b3_empresas
python -m ingest.b3_eventos                 # gabarito de eventos (~20 min)
python -m ingest.canario                    # as fontes continuam de pé?

python -m master.identidade                 # securities master por CNPJ
python -m master.eventos
python -m painel                            # reconstroi acoes_diario

python -m master.auditoria_tratamento --congelar     # antes de mexer na base
python -m master.auditoria_tratamento --comparar acoes_diario_base_AAAAMMDD
python -m master.auditoria_tratamento --pendentes    # o que falta decidir a mao

pytest tests/ -q
```

## Regras do repositório

1. **Point-in-time ou nada.** Toda tabela carrega `_downloaded_at` e `_source_file`.
2. **Preço cru e ajustado convivem.** Nunca só o ajustado.
3. **Coletor é idempotente.** Rodar duas vezes substitui a partição, não duplica.
4. **O arquivo original nunca é editado.** Fica em `data/raw/`, intocado.
5. **Nenhum módulo inventa caminho.** Tudo sai de `config.py`.
6. **Auditoria mede, não conserta.** Correção é decisão humana e vira arquivo versionado.

## Armadilhas encontradas (todas verificadas, nenhuma suposta)

**Nas fontes externas**
- BCB devolve **HTTP 200 com corpo HTML** de erro, intermitente. Sem checar JSON a série
  sumia calada. Tratado em `ingest.base.get_json`.
- SGS limita série diária a 10 anos por requisição (HTTP 406). Paginado.
- B3 `GetInitialCompanies` aceita `pageSize` até 120; acima disso devolve corpo vazio com
  status 200.
- **O cadastro da B3 só tem empresa viva**: 3.506 registros, todos com status "A". A CVM
  mantém as 1.912 canceladas.
- Consulta por prefixo na B3 pode casar errado: pedir `TRPL` devolve um **fundo
  imobiliário** chamado FII TRPL, não a CTEEP.
- O campo `Codigo_Negociacao` do FCA está vazio em metade das linhas e às vezes traz lixo
  (`4030`, `NÃO HÁ`). Por isso CSNA3, KLBN4 e VALE5 ficam sem vínculo.
- **A referência também erra**: o fator do NEFIN marca +13,47% em 13/06/2025 e SMB de
  +23,37% em 12/06/2025. A bolsa não fez isso. A auditoria marca e exclui esses dias.
- A API de índices da B3 ignora o parâmetro de ano: **não há carteira histórica gratuita**.

**No nosso código**
- DuckDB aceita um escritor por vez; coletores em paralelo se atropelam.
  `warehouse.connect` espera o lock.
- `cad_cia_aberta` é histórico de registro, não uma linha por empresa. Sem deduplicar, a
  Vibra saía como 'ativa' e 'cancelada' ao mesmo tempo.
- Detector com denominador 20 classificou o **crash da COVID na PETR4 como desdobramento**,
  confiança alta. Corrigido para 4. Travado em `tests/test_deteccao_eventos.py`.
- Denominador 4 quebrou o inverso: `Fraction(0,02).limit_denominator(4)` é **zero**, e
  grupamento de 50:1 sumia (ASTA4 virou +4.900%). Resolvido aproximando o inverso.
- Quantidade e financeiro não confirmam evento extremo (o papel muda de regime de
  liquidez). BRPR3 tinha erro de 0,003% contra 1/39,75 e mesmo assim caía em "baixa".
- Filtrar a referência por "|retorno| > 10%" excluía outubro de 2008 e março de 2020 —
  crise de verdade. O critério certo é discordância, não magnitude.

## Pendências abertas

1. **20% dos pregões de ação sem CNPJ.** 453 tickers, incluindo CSNA3, KLBN4, VALE5.
   Casar por nome é traiçoeiro (`KLABIN S/A` casa com três empresas na CVM, duas
   canceladas). Escopo real: **209 emissores líquidos**, revisão manual uma vez, congelada
   em crosswalk versionado. **Precisa de decisão do João.**
2. **Recall de 40,6%** sobre os eventos ao alcance do detector. Precisão de 24,9% em
   "alta" contra 2,8% em "baixa" — o ordenamento funciona, o nível não é suficiente.
3. **Cobertura de provento fraca.** O endpoint usado é esparso: 391 de 613 emissores com
   zero dividendo. O endpoint paginado `GetListedCashDividends` tem muito mais (337 para
   a Petrobras contra 24 aqui) e deveria substituí-lo.
4. **Aluguel por papel.** O NEFIN só dá o agregado de mercado. O gate de viabilidade de
   short precisa do arquivo BTB diário da B3.
