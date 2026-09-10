"""Painel de acoes da B3: uma tabela, diaria, 2005 em diante.

`acoes_diario` e a unica tabela de trabalho do projeto. Traz TRES series de preco lado a
lado, mais valor de mercado, liquidez e bid/ask.

AS TRES SERIES DE PRECO

    fechamento                 nominal, exatamente como o papel negociou
    fechamento_ajustado        corrigido por desdobramento e grupamento
    fechamento_retorno_total   tambem com dividendo e JCP

Nenhuma e o padrao. A escolha depende do teste e vira parametro declarado, nao default
escondido -- decisao do Joao em 02/09/2026, para se adaptar ao que cada paper do SSRN usar.

A tentacao e achar que so o nominal importa, porque e nele que o dinheiro troca de mao.
Mas o que voce ganha ou perde nao e o preco, e preco vezes QUANTIDADE, e evento
corporativo muda a quantidade:

    PETR4, quem tinha 100 acoes:
      25/04/2008   R$84,30 x 100 = R$8.430
      28/04/2008   R$42,59 x 200 = R$8.518     <- desdobramento 2:1

    A serie nominal marca -49,5%. O dinheiro na conta subiu 1,0%.

Medido em 21 anos, a diferenca entre as tres nao e detalhe:

    PETR4   nominal -49%   ajustado +309%   retorno total +2.251%
    CMIG4   nominal -83%   ajustado  -54%   retorno total    +89%

  para EXECUTAR (ordem, corretagem, emolumento, lote)  -> fechamento
  para MEDIR (retorno, backtest, P&L, sinal, risco)    -> ajustado ou retorno total

VALOR DE MERCADO

    valor_mercado_classe    acoes daquela classe vezes o preco dela
    valor_mercado_empresa   soma das classes; e o "tamanho" dos size sorts e do fator SMB

A quantidade de acoes vem do Formulario de Referencia da CVM, anual. E aplicada com
defasagem de 6 meses sobre a data de referencia, porque o documento de 31/12 so e
entregue por volta de maio seguinte -- usar antes disso seria look-ahead.

COBERTURAS, que precisam ser reportadas em qualquer resultado

    provento         740 de 1.129 papeis (66%)
    valor de mercado 94,8% das linhas a partir de julho/2011; quase nada antes, porque o
                     FRE so comeca em 2010
    identidade       ponte ticker->CNPJ do FCA, completada pelo caminho
                     ISIN -> codeCVM -> CNPJ para o que o FCA deixou vazio

O que falta em provento e valor de mercado e, em boa parte, empresa que saiu da bolsa: a
B3 nao mantem o historico delas. Ou seja, essas duas colunas sao fortes para quem esta
vivo e fracas para quem morreu -- o oposto do que um estudo sem survivorship precisa.
Serie com buraco nao e proibida; serie com buraco nao declarado e.

COBERTURA DO UNIVERSO

Acoes ordinarias, preferenciais e units, mercado a vista em lote padrao. BDR (empresa
estrangeira) e mercado fracionario ficam de fora. Empresa que quebrou, foi comprada ou
saiu da bolsa CONTINUA no painel nos anos em que negociou -- e a razao de a fonte ser o
COTAHIST da B3 e nao o yfinance.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import warehouse

# Sufixo do ticker -> o que o papel e. BDR e empresa estrangeira listada aqui, nao acao
# brasileira; fracionario e o mesmo papel em lote menor, entao duplicaria a serie.
# Confiancas do detector que entram no fator. "baixa" fica de fora de proposito:
# ajustar por evento duvidoso estraga a serie de um jeito dificil de perceber depois.
CONFIANCAS_ACEITAS = ("alta", "media")

# CODBDI -> regime de negociacao. Fonte: tabela oficial "CODBDI TABLE - LIST OF VALUES
# FOR BDI CODES" do layout do COTAHIST (B3, rev. 01 de 17/04/2017).
#
# POR QUE ISTO EXISTE: filtrar `codbdi = '02'` apagava a empresa exatamente quando ela
# quebrava. Ao entrar em recuperacao judicial o papel migra de 02 para 08 e continua
# negociando -- so que fora do painel. Mediu-se: 108 papeis truncados, 445 anos de serie
# perdidos, entre eles AMER3 (o painel parava em 19/01/2023, o dia seguinte a fraude,
# enquanto o COTAHIST tem ate hoje), LIGT3, OIBR4, RSID3, AMBP3, AZUL4, PCAR3 e BRKM5.
# E survivorship criado pelo proprio pipeline, e enviesado PARA CIMA, porque corta
# justamente a fase de perda.
#
# REGRA DE ADMISSAO, verificada antes de admitir cada codigo: so entra o codbdi para o
# qual, nos tickers que transitam de 02 para ele, o ISIN permanece o mesmo e o preco e
# continuo na virada. Medido: 07, 08, 58 e 05 tem 100% de ISIN identico. O codigo 10
# (rights and receipts) reprova -- 0% de ISIN identico e razao mediana de 0,03: e outro
# papel, nao a acao.
REGIME_POR_BDI = {
    "02": "normal",
    "05": "sancao_regulamentar",         # BMFBOVESPA REGULATIONS SANCTION
    "06": "reorganizacao",               # STOCKS OF COS. UNDER REORGANIZATION
    "07": "recuperacao_extrajudicial",   # EXTRAJUDICIAL RECOVERY
    "08": "recuperacao_judicial",        # JUDICIAL RECOVERY
    "09": "administracao_especial",      # TEMPORARY ESPECIAL MANAGEMENT
    "11": "intervencao",                 # INTERVENTION
    "58": "outros",                      # OTHERS -- e onde a AZUL4 foi parar em 2025
}
# Fora: 10 (direitos e recibos, outro papel), 12 (FII), 14 (certificados e ETF -- decisao
# do Joao: universo e ON/PN/Unit), 22 (bonus), 34/35/36 (BDR), 96 (fracionario).
SQL_BDI = "(" + ", ".join(f"'{c}'" for c in REGIME_POR_BDI) + ")"
SQL_REGIME = "CASE " + " ".join(
    f"WHEN codbdi = '{c}' THEN '{r}'" for c, r in REGIME_POR_BDI.items()
) + " ELSE 'outro' END"

# Expressao unica do retorno. Exportada como constante para que o teste de
# append-only rode exatamente o que o painel roda -- teste que reimplementa a formula
# nao prova nada sobre o pipeline.
SQL_RETORNOS = """
    fechamento_ajustado
      / lag(fechamento_ajustado) OVER (PARTITION BY ticker ORDER BY data)
      - 1 AS retorno_qtd,
    fechamento_retorno_total
      / lag(fechamento_retorno_total) OVER (PARTITION BY ticker ORDER BY data)
      - 1 AS retorno_total
"""

SQL_CLASSE = """
    CASE WHEN regexp_matches(ticker, '(33|34|35|39)$') THEN 'bdr'
         WHEN regexp_matches(ticker, '11$')            THEN 'unit_etf_fii'
         WHEN regexp_matches(ticker, '[0-9]B$')        THEN 'fracionario'
         WHEN regexp_matches(ticker, '3$')             THEN 'on'
         WHEN regexp_matches(ticker, '[4-8]$')         THEN 'pn'
         ELSE 'outro' END
"""


def _fatores_de_evento() -> pd.DataFrame:
    """Fator de ajuste por ticker/data, acumulado de forma retroativa."""
    from master import eventos  # importado aqui para o painel nao depender disso no import

    ev = eventos.detectar()
    ev = ev[ev["confianca"].isin(CONFIANCAS_ACEITAS)]
    ev = ev.dropna(subset=["fator_sugerido"])
    ev = ev[ev["fator_sugerido"] > 0]
    return ev.groupby(["ticker", "data"], as_index=False)["fator_sugerido"].prod()


SUFIXO_POR_TIPO = {
    "ON": "3", "PN": "4", "PNA": "5", "PNB": "6", "PNC": "7", "PND": "8", "UNT": "11",
}


def _fatores_de_provento(px: pd.DataFrame) -> pd.DataFrame:
    """Razao de ajuste por provento, por ticker e data-ex.

    A razao usada e (P_com - D) / P_com, com o preco CONTEMPORANEO ao provento. Duas
    razoes para nao somar valores em vez de multiplicar razoes:

      1. e livre de escala, entao dividendo antigo nao precisa ser corrigido por
         desdobramento posterior -- armadilha classica que produz erro silencioso;
      2. compoe direto com o fator de evento, que ja e multiplicativo.

    A data-ex e o primeiro pregao DEPOIS da ultima data com direito. A B3 informa a data
    com, nao a ex; confundir as duas desloca o ajuste em um dia.
    """
    with warehouse.connect(read_only=True) as con:
        if not warehouse.table_exists(con, "b3_proventos"):
            return pd.DataFrame(columns=["ticker", "data_ex", "razao"])
        tem_cnpj = "cnpj" in {c[0] for c in con.execute("DESCRIBE b3_proventos").fetchall()}
        sql_cnpj = "regexp_replace(cnpj, '[^0-9]', '', 'g')" if tem_cnpj else "NULL"
        prov = con.execute(f"""
            SELECT {sql_cnpj} AS cnpj_num,
                   empresa, tipo_acao,
                   try_strptime(ultima_data_com, '%d/%m/%Y')::DATE       AS data_com,
                   TRY_CAST(replace(valor_por_acao, ',', '.') AS DOUBLE) AS valor
            FROM b3_proventos
            WHERE _snapshot = (SELECT max(_snapshot) FROM b3_proventos)
        """).df()
        # Ponte ticker -> CNPJ, do securities master. Vem daqui e nao de `px` porque a
        # coluna cnpj de acoes_diario so nasce no bloco de valor de mercado, depois deste.
        mapa_cnpj = con.execute("""
            SELECT ticker, regexp_replace(cnpj, '[^0-9]', '', 'g') AS cnpj_num
            FROM master_ticker WHERE cnpj IS NOT NULL
        """).df() if warehouse.table_exists(con, "master_ticker") else pd.DataFrame()

    prov = prov.dropna(subset=["data_com", "valor"])
    prov = prov[prov["valor"] > 0].copy()
    prov["sufixo"] = prov["tipo_acao"].str.strip().str.upper().map(SUFIXO_POR_TIPO)
    prov = prov.dropna(subset=["sufixo"])
    if prov.empty:
        return pd.DataFrame(columns=["ticker", "data_ex", "razao"])

    # (CNPJ, sufixo) -> ticker. O casamento POR NOME, que era o que existia aqui, deixou
    # a ABEV3 com ZERO dividendo em treze anos e a KLBN3/KLBN4 com zero em vinte e um:
    # o nome muda ("AMBEV" -> "AMBEV S/A" em 2013) e o `nome_res` do COTAHIST ainda vem
    # truncado em 12 caracteres, entao os proventos antigos so casavam com o ticker
    # antigo. CNPJ nao muda -- e por isso ele e a chave.
    # Duas passadas, nesta ordem, e a segunda so alcança o que a primeira nao cobriu.
    por_nome = px[["ticker", "empresa"]].drop_duplicates().copy()
    por_nome["sufixo"] = por_nome["ticker"].str.extract(r"([0-9]+)$", expand=False)

    partes = []
    usar_cnpj = (not mapa_cnpj.empty) and prov["cnpj_num"].notna().any()
    if usar_cnpj:
        mapa = mapa_cnpj.dropna(subset=["cnpj_num"]).drop_duplicates().copy()
        mapa["sufixo"] = mapa["ticker"].str.extract(r"([0-9]+)$", expand=False)
        partes.append(prov.dropna(subset=["cnpj_num"]).merge(
            mapa, on=["cnpj_num", "sufixo"], how="inner"))
        # Fallback DECLARADO para o ticker cujo CNPJ ninguem resolveu -- 198 papeis, quase
        # todos mortos antes de 2018, quando o FCA da CVM ainda nao trazia o codigo de
        # negociacao. Para eles o nome ainda e a unica chave que existe; ficar sem
        # dividendo por pureza de metodo seria trocar um erro por outro.
        sem_cnpj = por_nome[~por_nome["ticker"].isin(mapa["ticker"])]
        if not sem_cnpj.empty:
            partes.append(prov.merge(sem_cnpj, on=["empresa", "sufixo"], how="inner"))
    else:
        partes.append(prov.merge(por_nome, on=["empresa", "sufixo"], how="inner"))

    prov = pd.concat(partes, ignore_index=True)
    # O mesmo pagamento pode chegar pelas duas passadas; a chave economica decide.
    prov = prov.drop_duplicates(["ticker", "data_com", "valor"])
    if prov.empty:
        return pd.DataFrame(columns=["ticker", "data_ex", "razao"])

    prov["data_com"] = pd.to_datetime(prov["data_com"])
    calendario = px[["ticker", "data", "fechamento"]].sort_values("data")

    # preco no ultimo pregao ATE a data com (o preco que ainda embute o direito)
    com_preco = pd.merge_asof(
        prov.sort_values("data_com"), calendario,
        left_on="data_com", right_on="data", by="ticker", direction="backward",
    ).dropna(subset=["fechamento"])

    # data-ex = primeiro pregao DEPOIS da data com
    com_ex = pd.merge_asof(
        com_preco.sort_values("data_com"),
        calendario[["ticker", "data"]].rename(columns={"data": "data_ex"}).sort_values("data_ex"),
        left_on="data_com", right_on="data_ex", by="ticker", direction="forward",
        allow_exact_matches=False,
    ).dropna(subset=["data_ex"])

    com_ex["razao"] = 1.0 - com_ex["valor"] / com_ex["fechamento"]
    # Provento maior que o preco indica dado ruim ou evento que nao e dividendo comum.
    # Nao ajusta, em vez de gerar preco negativo em silencio.
    com_ex = com_ex[(com_ex["razao"] > 0) & (com_ex["razao"] <= 1)]

    return (com_ex.groupby(["ticker", "data_ex"], as_index=False)["razao"].prod()
                  .rename(columns={"data_ex": "data"}))


# Defasagem entre a data de referencia do FRE (31/12) e o dia em que da para usar o
# numero. O formulario e entregue por volta de maio do ano seguinte, entao liberar em
# 1o de julho e conservador e defensavel. Sem essa defasagem, o painel saberia em janeiro
# a quantidade de acoes de um documento que so seria publicado em maio -- look-ahead.
# DUAS CONVENCOES DE RETORNO DE DELISTING, lado a lado -- a mesma logica de "nao existe
# o preco" aplicada aqui. Quando o papel sai da bolsa sem oferta e sem sucessor, o que o
# acionista de fato levou nao esta em lugar nenhum da base, e escolher um numero e
# ARBITRAR. Entao a base entrega os dois e a escolha vira campo do pre-registro.
#
#   retorno_delisting              -> -30%, de Shumway (1997), "The Delisting Bias in CRSP
#                                     Data", Journal of Finance. Ele mediu os delistings em
#                                     que o retorno final EXISTIA e usou a media para imputar
#                                     nos que faltavam. E o padrao da literatura, e o numero
#                                     que um paper da SSRN vai ter usado. Shumway e Warther
#                                     (1999) estimam -55% para o Nasdaq, mercado de empresa
#                                     menor e mais fragil -- mais perto do nosso caso.
#   retorno_delisting_conservador  -> -100%. Premissa de que a posicao virou po. Defensavel
#                                     no Brasil, onde nao ha mercado de balcao organizado
#                                     para acao cancelada: o -30% americano embute a venda
#                                     no OTC, que aqui simplesmente nao existe.
#
# Nenhum dos dois foi observado. `delisting_observado` continua FALSE nos dois casos, e
# qualquer resultado sensivel a essa escolha tem que reportar as duas versoes.
RETORNO_DELISTING_LITERATURA = -0.30

MESES_DEFASAGEM_FRE = 6


def _valor_de_mercado(px: pd.DataFrame) -> pd.DataFrame:
    """Valor de mercado por ticker e por empresa, com defasagem de divulgacao.

    Duas medidas, porque servem a coisas diferentes:
      valor_mercado_classe  -- quantidade de acoes DAQUELA classe vezes o preco dela
      valor_mercado_empresa -- soma de todas as classes; e o "tamanho" que a literatura
                               usa em size sorts e no fator SMB
    """
    with warehouse.connect(read_only=True) as con:
        for t in ("cvm_capital_social", "cvm_ponte_ticker"):
            if not warehouse.table_exists(con, t):
                return pd.DataFrame()

        # Ponte ticker -> CNPJ: uniao das duas fontes. A do FCA e direta; a do ISIN
        # cobre o que o FCA deixou vazio (B3SA3, CSNA3, KLBN3/4, MBRF3, CMIN3...).
        # A ponte de identidade vem do securities master, que consolida as tres fontes
        # com prioridade declarada (FCA > ponte B3/ISIN > irmao de emissor > crosswalk
        # humano) e registra em `fonte_do_vinculo` de onde cada vinculo veio. Antes disto
        # havia TRES resolucoes de CNPJ soltas no repo e nenhum lugar unia todas: este
        # painel usava duas, `identidade.py` usava outra. Uma so agora.
        if warehouse.table_exists(con, "master_ticker"):
            ponte = con.execute("""
                SELECT ticker, cnpj FROM master_ticker WHERE cnpj IS NOT NULL
            """).df()
        else:
            ponte = con.execute("""
                SELECT DISTINCT Codigo_Negociacao AS ticker, CNPJ_Companhia AS cnpj
                FROM cvm_ponte_ticker
            """).df()

        # Uma linha por CNPJ e data de referencia, ficando com a versao mais recente
        # do documento (a CVM republica o FRE com correcoes).
        acoes = con.execute("""
            SELECT CNPJ_Companhia AS cnpj,
                   Data_Referencia AS data_ref,
                   arg_max(Quantidade_Acoes_Ordinarias, Versao)    AS acoes_on,
                   arg_max(Quantidade_Acoes_Preferenciais, Versao) AS acoes_pn,
                   arg_max(Quantidade_Total_Acoes, Versao)         AS acoes_total
            FROM cvm_capital_social
            WHERE Data_Referencia IS NOT NULL
            GROUP BY 1, 2
        """).df()

    if ponte.empty or acoes.empty:
        return pd.DataFrame()

    acoes["data_ref"] = pd.to_datetime(acoes["data_ref"])
    acoes["disponivel_em"] = acoes["data_ref"] + pd.DateOffset(months=MESES_DEFASAGEM_FRE)
    acoes = acoes.sort_values("disponivel_em")

    base = px.merge(ponte, on="ticker", how="inner")
    if base.empty:
        return pd.DataFrame()

    # Para cada pregao, o FRE mais recente que JA estava disponivel naquele dia.
    base = base.sort_values("data")
    casado = pd.merge_asof(
        base, acoes[["cnpj", "disponivel_em", "acoes_on", "acoes_pn", "acoes_total"]],
        left_on="data", right_on="disponivel_em", by="cnpj", direction="backward",
    )

    sufixo = casado["ticker"].str.extract(r"([0-9]+)$", expand=False)
    casado["acoes_da_classe"] = np.where(
        sufixo == "3", casado["acoes_on"],
        np.where(sufixo.isin(["4", "5", "6", "7", "8"]), casado["acoes_pn"], np.nan))
    casado["valor_mercado_classe"] = casado["acoes_da_classe"] * casado["fechamento"]

    # Tamanho da EMPRESA: soma das classes no mesmo dia. So e considerado completo quando
    # toda classe com acoes registradas tambem negociou naquele pregao -- senao o numero
    # subestima o tamanho de um jeito que ninguem perceberia.
    por_empresa = (casado.dropna(subset=["valor_mercado_classe"])
                   .groupby(["cnpj", "data"], as_index=False)
                   .agg(valor_mercado_empresa=("valor_mercado_classe", "sum"),
                        classes_no_dia=("ticker", "nunique")))
    casado = casado.merge(por_empresa, on=["cnpj", "data"], how="left")

    return casado[["ticker", "data", "cnpj", "acoes_da_classe",
                   "valor_mercado_classe", "valor_mercado_empresa"]]


def construir(ano_inicio: int = 2005) -> int:
    fatores = _fatores_de_evento()

    with warehouse.connect() as con:
        con.execute("DROP TABLE IF EXISTS acoes_diario")
        con.execute(f"""
            CREATE TABLE acoes_diario AS
            SELECT
                ticker,
                data::DATE          AS data,
                {SQL_CLASSE}        AS classe,
                {SQL_REGIME}        AS regime,
                nome_res            AS empresa,
                isin,
                -- PRECO POR ACAO. O COTAHIST cota parte da base por LOTE DE MIL, e
                -- `fator_cotacao` diz qual. Verificado na base inteira: a mediana de
                -- fechamento/(volume/quantidade) e exatamente o fator_cotacao em cada
                -- faixa. 238 papeis do painel atravessam uma virada de unidade -- LREN3,
                -- ELET3, SBSP3, CMIG4, BRKM5, CPLE6, PCAR4, AMBV4 -- quase todos entre
                -- 2005 e 2007, quando a B3 migrou de cotacao por-mil para por-acao.
                -- Sem dividir, o nivel de preco fica 1000x errado nesses trechos e todo
                -- filtro de preco minimo, penny stock ou tick vira ficcao ali.
                fechamento / fator_cotacao AS fechamento,      -- NOMINAL, por acao
                fechamento                 AS fechamento_cotado,  -- como a B3 publica
                fator_cotacao,            -- a quantas acoes a cotacao se refere
                abertura / fator_cotacao AS abertura,
                maxima   / fator_cotacao AS maxima,
                minima   / fator_cotacao AS minima,
                -- Melhor oferta de compra e venda no fechamento. Entram porque o spread
                -- e a maior parcela do custo em papel pouco liquido -- ignora-lo faz
                -- estrategia de small cap parecer lucrativa quando nao e -- e porque
                -- spread relativo e proxy padrao de liquidez na literatura.
                melhor_compra / fator_cotacao AS melhor_compra,
                melhor_venda  / fator_cotacao AS melhor_venda,
                -- SPREAD RELATIVO no fechamento. Sai daqui, e nao da camada de analise,
                -- porque depende do bid e do ask normalizados pela unidade de cotacao --
                -- que so este bloco conhece.
                --
                -- E a variavel que decide se um edge de capital pequeno e real. Medido na
                -- base (2015+): spread mediano de 0,175% em papel acima de R$10 mi/dia e
                -- de 3,279% abaixo de R$100 mil/dia. Dezenove vezes. Ida e volta na cauda
                -- iliquida custa 6,6% -- mais do que quase toda anomalia publicada rende.
                CASE WHEN melhor_compra > 0 AND melhor_venda > melhor_compra
                     THEN (melhor_venda - melhor_compra)
                          / ((melhor_venda + melhor_compra) / 2) END AS spread_relativo,
                volume,                   -- financeiro, em reais (nao depende da unidade)
                quantidade,               -- acoes negociadas
                negocios
            FROM b3_cotahist
            WHERE codbdi IN {SQL_BDI}     -- lote padrao + regimes especiais
              AND tpmerc = '010'          -- mercado a vista
              AND fechamento > 0
              AND fator_cotacao > 0
              AND year(data) >= {ano_inicio}
              AND {SQL_CLASSE} IN ('on', 'pn', 'unit_etf_fii')
            ORDER BY ticker, data
        """)

        con.register("_fat", fatores)
        # fator do dia: 1 quando nao houve evento
        con.execute("""
            ALTER TABLE acoes_diario ADD COLUMN fator_dia DOUBLE DEFAULT 1.0
        """)
        con.execute("""
            UPDATE acoes_diario a
               SET fator_dia = f.fator_sugerido
              FROM _fat f
             WHERE f.ticker = a.ticker AND f.data::DATE = a.data
        """)
        # Acumulado retroativo: produto dos fatores de todo evento POSTERIOR ao dia.
        # O proprio dia ex fica de fora porque o preco daquele dia ja vem dividido pelo
        # mercado -- incluir seria ajustar duas vezes.
        con.execute("""
            CREATE OR REPLACE TABLE acoes_diario AS
            WITH com_fator AS (
                SELECT * EXCLUDE (fator_dia),
                       COALESCE(exp(sum(ln(fator_dia)) OVER (
                           PARTITION BY ticker ORDER BY data
                           ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING
                       )), 1.0)           AS fator_acum,
                       (fator_dia <> 1.0) AS tem_evento
                FROM acoes_diario
            )
            SELECT * EXCLUDE (fator_acum, tem_evento),
                   -- As series ficam materializadas lado a lado, e nao uma como coluna e
                   -- as outras como conta que alguem precisa lembrar de fazer. Esquecer
                   -- de dividir e erro silencioso: o numero sai, so sai errado.
                   fechamento / fator_acum AS fechamento_ajustado,
                   fator_acum, tem_evento
            FROM com_fator
            ORDER BY ticker, data
        """)
        con.unregister("_fat")

        # ---------------- terceira serie: retorno total ----------------
        px = con.execute("SELECT ticker, data, fechamento, empresa FROM acoes_diario").df()
        px["data"] = pd.to_datetime(px["data"])

    prov = _fatores_de_provento(px)

    with warehouse.connect() as con:
        con.register("_prov", prov)
        con.execute("ALTER TABLE acoes_diario ADD COLUMN razao_prov DOUBLE DEFAULT 1.0")
        if not prov.empty:
            con.execute("""
                UPDATE acoes_diario a SET razao_prov = p.razao
                  FROM _prov p
                 WHERE p.ticker = a.ticker AND p.data::DATE = a.data
            """)
        con.execute("""
            CREATE OR REPLACE TABLE acoes_diario AS
            WITH acum AS (
                SELECT * EXCLUDE (razao_prov),
                       COALESCE(exp(sum(ln(razao_prov)) OVER (
                           PARTITION BY ticker ORDER BY data
                           ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING
                       )), 1.0) AS fator_prov_acum,
                       (razao_prov <> 1.0) AS tem_provento
                FROM acoes_diario
            )
            SELECT * EXCLUDE (fator_prov_acum, tem_provento),
                   fechamento_ajustado * fator_prov_acum AS fechamento_retorno_total,
                   fator_prov_acum, tem_provento
            FROM acum
            ORDER BY ticker, data
        """)
        con.unregister("_prov")

        # ---------------- retorno: a primitiva ----------------
        # INVERSAO DE QUEM E O DADO PRIMARIO. Ate aqui a base guardava preco ajustado por
        # FATOR ACUMULADO RETROATIVO -- quando um evento novo acontece hoje, todo o passado
        # da serie muda. Um backtest rodado em marco e o mesmo backtest rodado em setembro
        # davam numeros diferentes, e nao havia como saber se a diferenca era o codigo ou
        # o dado. E o desenho do CRSP, a base que a literatura usa, e o inverso: o RETORNO
        # e a primitiva e o preco ajustado e derivado dele.
        #
        # A propriedade que isso da, e que e o ponto todo:
        #
        #     R(t) = [ P(t) x F(t) + D(t) ] / P(t-1) - 1
        #
        # depende SO de t e t-1. Nenhum evento posterior entra na conta. Entao o retorno
        # de ontem nunca muda por causa de um evento de hoje -- a serie vira append-only e
        # o backtest fica reproduzivel.
        #
        # A forma abaixo e algebricamente a mesma coisa, escrita sobre as series ja
        # materializadas: F(t) = fator_acum(t-1)/fator_acum(t) por construcao do produto
        # retroativo, e a razao de provento entra como divisor. Preferida por ser curta e
        # por nao depender de recalcular fator_dia, que ja foi consumido.
        #
        # As tres series de preco continuam lado a lado (regra 7 do projeto: "nao existe
        # o preco"). O que muda e a hierarquia: preco ajustado passa a ser vista do
        # retorno, e nao o contrario.
        con.execute(f"""
            CREATE OR REPLACE TABLE acoes_diario AS
            SELECT *, {SQL_RETORNOS}
            FROM acoes_diario
            ORDER BY ticker, data
        """)

        # ---------------- valor de mercado ----------------
        px2 = con.execute("SELECT ticker, data, isin, fechamento FROM acoes_diario").df()
        px2["data"] = pd.to_datetime(px2["data"])

    vm = _valor_de_mercado(px2)

    with warehouse.connect() as con:
        if vm.empty:
            con.execute("ALTER TABLE acoes_diario ADD COLUMN cnpj VARCHAR")
            con.execute("ALTER TABLE acoes_diario ADD COLUMN acoes_da_classe DOUBLE")
            con.execute("ALTER TABLE acoes_diario ADD COLUMN valor_mercado_classe DOUBLE")
            con.execute("ALTER TABLE acoes_diario ADD COLUMN valor_mercado_empresa DOUBLE")
        else:
            con.register("_vm", vm)
            con.execute("""
                CREATE OR REPLACE TABLE acoes_diario AS
                SELECT a.*, v.cnpj, v.acoes_da_classe,
                       v.valor_mercado_classe, v.valor_mercado_empresa
                FROM acoes_diario a
                LEFT JOIN _vm v ON v.ticker = a.ticker AND v.data::DATE = a.data
                ORDER BY a.ticker, a.data
            """)
            con.unregister("_vm")

        # ---------------- saida do papel: motivo e retorno de delisting ----------------
        # SEM ISTO O BACKTEST E OTIMISTA POR CONSTRUCAO. 669 dos 1.035 papeis ON/PN da
        # base morrem -- 25% do volume. Se a serie so termina, a carteira "vende no ultimo
        # preco" e nunca leva a perda final. E o vies de delisting que Shumway documentou
        # no CRSP nos anos 90, e cuja correcao mudou a magnitude do efeito tamanho na
        # literatura.
        #
        # CONVENCAO, decidida pelo Joao em 09/09/2026 e escrita aqui de proposito:
        #   liquidada / cancelamento de oficio -> -100%. Nao ha sucessor nem oferta, e a
        #       posicao fica sem mercado. E a hipotese conservadora.
        #   incorporada / fechou capital -> ultimo preco, com delisting_observado = FALSE.
        #       O acionista recebeu dinheiro ou acao do comprador; QUANTO recebeu exige ler
        #       o edital da OPA caso a caso, e isso ficou para outro projeto. O campo fica
        #       pronto para receber o valor observado depois, sem refazer nada.
        #   sucessao de ticker -> NAO e delisting. EMBR3 vira EMBJ3 e a posicao continua;
        #       marcar perda ali inventaria um prejuizo que nao houve.
        #
        # Regra 8 do projeto: serie com buraco nao e proibida, serie com buraco nao
        # declarado e. Por isso `delisting_observado` existe -- ele diz que o numero e
        # convencao, nao medida.
        con.execute(f"""
            CREATE OR REPLACE TABLE acoes_diario AS
            WITH fim_da_base AS (SELECT max(data) AS d FROM acoes_diario),
            ultimo AS (
                SELECT ticker, max(data) AS ultima_data FROM acoes_diario GROUP BY 1
            ),
            -- Sucessao: outro ticker do MESMO CNPJ que estreia ate 10 dias corridos
            -- depois do fim deste. E o criterio de continuidade de pregao ja usado em
            -- master/auditoria.py.
            com_sucessor AS (
                SELECT DISTINCT u.ticker
                FROM ultimo u
                JOIN acoes_diario a ON a.ticker = u.ticker AND a.data = u.ultima_data
                JOIN master_ticker mt ON mt.ticker = u.ticker AND mt.cnpj IS NOT NULL
                JOIN master_ticker ms ON ms.cnpj = mt.cnpj AND ms.ticker <> u.ticker
                WHERE ms.primeiro_pregao > u.ultima_data
                  AND datediff('day', u.ultima_data, ms.primeiro_pregao) <= 10
            ),
            marcado AS (
                SELECT a.*,
                       CASE
                         WHEN a.data <> u.ultima_data THEN NULL
                         WHEN u.ultima_data >= (SELECT d FROM fim_da_base) - 5 THEN NULL
                         WHEN cs.ticker IS NOT NULL THEN 'sucessao_de_ticker'
                         -- Empresa segue registrada na CVM mas o PAPEL parou de negociar:
                         -- conversao de classe (VALE5 -> VALE3), saida da B3 sem cancelar
                         -- o registro, migracao de segmento. Nao e delisting da companhia,
                         -- e o rotulo 'ativa' aqui confundiria motivo de saida do papel
                         -- com situacao da empresa.
                         WHEN me.destino = 'ativa' THEN 'papel_encerrado_empresa_ativa'
                         ELSE COALESCE(me.destino, 'desconhecido')
                       END AS motivo_saida
                FROM acoes_diario a
                JOIN ultimo u ON u.ticker = a.ticker
                LEFT JOIN com_sucessor cs ON cs.ticker = a.ticker
                LEFT JOIN master_ticker mt ON mt.ticker = a.ticker
                LEFT JOIN master_empresa me ON me.cnpj = mt.cnpj
            )
            SELECT *,
                   CASE WHEN motivo_saida IN ('liquidada', 'cancelamento_de_oficio')
                        THEN {RETORNO_DELISTING_LITERATURA} END AS retorno_delisting,
                   CASE WHEN motivo_saida IN ('liquidada', 'cancelamento_de_oficio')
                        THEN -1.0 END AS retorno_delisting_conservador,
                   CASE WHEN motivo_saida IS NULL THEN NULL ELSE FALSE END
                        AS delisting_observado
            FROM marcado
            ORDER BY ticker, data
        """) if warehouse.table_exists(con, "master_empresa") else None

        return con.execute("SELECT count(*) FROM acoes_diario").fetchone()[0]


def resumo() -> pd.DataFrame:
    with warehouse.connect(read_only=True) as con:
        return con.execute("""
            SELECT classe,
                   count(DISTINCT ticker) AS tickers,
                   count(*)               AS linhas,
                   min(data)              AS inicio,
                   max(data)              AS fim
            FROM acoes_diario
            GROUP BY 1 ORDER BY linhas DESC
        """).df()


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    n = construir()
    print(f"acoes_diario: {n:,} linhas\n")
    print(resumo().to_string(index=False))
