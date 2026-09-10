"""Painel mensal por EMISSOR -- a unidade em que teste de cross-section se faz.

POR QUE ESTA CAMADA EXISTE

`acoes_diario` e por PAPEL, e tem que ser: e o papel que se compra, e o custo, o lote e o
spread sao dele. Mas teste de cross-section nao se faz por papel, e sim por EMPRESA.

ON e PN da mesma companhia nao sao dois ativos independentes. Num sort por tamanho ou
valor, ITUB3 e ITUB4 entram como duas observacoes da MESMA firma: isso infla o N efetivo,
quebra a hipotese de independencia que o erro-padrao de Fama-MacBeth assume, e deixa uma
empresa ocupar duas vagas no mesmo decil. No Brasil o problema pesa mais que nos EUA --
30,7% dos meses-empresa da nossa base tem duas classes negociando.

A convencao vem da literatura brasileira: "Lottery-type stocks in Brazil: Evidence from a
survivorship-bias-corrected universe" (Revista Brasileira de Financas, 24, 2026) monta o
painel a partir do COTAHIST e diz: "the unit of analysis in all reported results is the
issuer: in each month I retain the most liquid share class for issuers with multiple
classes".

ONDE ESTE MODULO DISCORDA DO PAPER, DE PROPOSITO

O paper escolhe a classe mais liquida DO MES e usa o retorno DAQUELE MES. Isso e
look-ahead, e do tipo pior: a escolha correlaciona com o que aconteceu no mes -- a classe
que teve a noticia negociou mais. Aqui a classe sai da liquidez dos 12 MESES ANTERIORES.

A janela de 12 meses nao e so por causa do look-ahead; foi medida. Com janela de um mes,
empresa iliquida troca de classe na metade dos meses (IGUACU CAFE 50,9%, ALFA HOLDING
49,8%): as duas classes mal negociam e "a mais liquida" vira ruido. Com 12 meses o giro
cai de 4,11% para 1,75% dos meses-empresa, e a ITAUSA, que oscilava entre ITSA3 e ITSA4,
fica em ITSA4 nos 261 meses.

O que sobra de troca esta inteiro em microcap, e isso foi verificado, nao suposto:

    troca < 5% dos meses     491 empresas   volume mensal mediano  R$ 54,6 milhoes
    troca 5-20%               34 empresas   volume mensal mediano  R$ 48,7 mil
    troca >= 20%              11 empresas   volume mensal mediano  R$ 11,6 mil

Quatro mil vezes menos liquido. Qualquer filtro de negociabilidade tira esses papeis, e a
coluna `trocou_de_classe` deixa o custo a vista para quem nao filtrar.

O BALANCO ENTRA POINT-IN-TIME, E ISSO E O CENTRO DA CAMADA

Sem contabilidade nao existe book-to-market, nao existe E/P, nao existe qualidade -- ou
seja, metade da tabela de fatores que qualquer paper de cross-section usa. Mas dado
contabil e onde look-ahead entra mais facil, porque o balanco descreve 31 de dezembro e
so fica publico meses depois.

O padrao da literatura e defasar 6 meses no atacado (Fama-French). Aqui da para fazer
melhor: a CVM informa `DT_RECEB`, a data em que o documento efetivamente chegou. Medido:
mediana de 88 dias apos a referencia, p90 de 125, **maximo de 964**. A defasagem fixa
erraria justamente nas empresas que atrasam balanco -- que sao as em dificuldade, e as que
mais importam num teste de valor. Cada mes recebe o que ja estava entregue no ultimo dia
dele, na versao mais recente disponivel naquela data.

O QUE ESTE MODULO NAO FAZ

Nao filtra. O paper exige minimo de 10 pregoes no mes e 12 meses de historico; aqui essas
quantidades viram COLUNA (`pregoes_no_mes`), e o filtro fica com quem for rodar o teste --
regra 6 do projeto: auditoria mede, nao conserta. Filtro embutido em base e filtro que
ninguem ve.
"""
from __future__ import annotations

import pandas as pd

import warehouse

TABELA = "emissor_mensal"

# Tudo ate `base` vale com ou sem balanco; o bloco contabil e opcional.
SQL_BASE = """
WITH diario AS (
    -- So acao. Unit e ETF tem dinamica propria e nao entram em sort de caracteristica
    -- de empresa.
    SELECT a.*, strftime(a.data, '%Y-%m') AS ano_mes
    FROM acoes_diario a
    WHERE a.classe IN ('on', 'pn') AND a.cnpj IS NOT NULL
),
-- Um registro por (empresa, classe, mes).
por_ticker AS (
    SELECT cnpj, ticker, ano_mes,
           count(*)                                  AS pregoes_no_mes,
           sum(volume)                               AS volume_mes,
           median(volume)                            AS volume_mediano,
           last(fechamento ORDER BY data)            AS preco_fim,
           last(valor_mercado_empresa ORDER BY data) AS valor_mercado_empresa,
           last(regime ORDER BY data)                AS regime,
           last(empresa ORDER BY data)               AS nome,
           last(motivo_saida ORDER BY data)          AS motivo_saida,
           last(retorno_delisting ORDER BY data)     AS retorno_delisting,
           last(retorno_delisting_conservador ORDER BY data)
                                                     AS retorno_delisting_conservador,
           -- Retorno composto do mes, a partir da primitiva diaria.
           exp(sum(ln(1 + retorno_qtd)) FILTER (WHERE retorno_qtd > -1)) - 1
                                                     AS retorno_qtd,
           exp(sum(ln(1 + retorno_total)) FILTER (WHERE retorno_total > -1)) - 1
                                                     AS retorno_total,
           bool_or(tem_evento)                       AS teve_evento,
           bool_or(tem_provento)                     AS teve_provento
    FROM diario
    GROUP BY cnpj, ticker, ano_mes
),
-- A ESCOLHA DA CLASSE, POINT-IN-TIME E ESTAVEL: liquidez dos 12 meses ANTERIORES.
com_liquidez_anterior AS (
    SELECT *,
           sum(volume_mes) OVER (
               PARTITION BY cnpj, ticker ORDER BY ano_mes
               ROWS BETWEEN 12 PRECEDING AND 1 PRECEDING
           ) AS volume_mes_anterior
    FROM por_ticker
),
ranqueado AS (
    SELECT *,
           row_number() OVER (
               PARTITION BY cnpj, ano_mes
               ORDER BY COALESCE(volume_mes_anterior, -1) DESC, volume_mes DESC, ticker
           ) AS posicao,
           count(*) OVER (PARTITION BY cnpj, ano_mes) AS classes_no_mes,
           (volume_mes_anterior IS NULL)              AS escolha_sem_historico
    FROM com_liquidez_anterior
),
base AS (
    SELECT cnpj, ano_mes, ticker, nome, regime,
           pregoes_no_mes, classes_no_mes, escolha_sem_historico,
           preco_fim, volume_mes, volume_mediano, valor_mercado_empresa,
           retorno_qtd, retorno_total, teve_evento, teve_provento,
           motivo_saida, retorno_delisting, retorno_delisting_conservador,
           ticker <> lag(ticker) OVER (PARTITION BY cnpj ORDER BY ano_mes)
             AS trocou_de_classe,
           (date_trunc('month', strptime(ano_mes, '%Y-%m'))
              + INTERVAL 1 MONTH - INTERVAL 1 DAY)::DATE AS fim_do_mes
    FROM ranqueado
    WHERE posicao = 1
)
"""

# Bloco contabil: so entra se `cvm_dfp` existir.
SQL_COM_BALANCO = SQL_BASE + """,
-- BALANCO: uma linha por (empresa, referencia, versao), contas lado a lado.
-- O consolidado tem preferencia -- e o que a literatura usa e o que descreve a empresa
-- inteira. So quando a companhia nunca entregou consolidado o individual entra, e a
-- coluna `contabil_consolidado` registra qual foi.
dfp_wide AS (
    SELECT cnpj, dt_refer, dt_receb, versao,
           bool_or(consolidado) AS contabil_consolidado,
           max(valor) FILTER (WHERE conta = 'patrimonio_liquido') AS patrimonio_liquido,
           max(valor) FILTER (WHERE conta = 'ativo_total')        AS ativo_total,
           max(valor) FILTER (WHERE conta = 'lucro_liquido')      AS lucro_liquido,
           max(valor) FILTER (WHERE conta = 'receita')            AS receita,
           max(valor) FILTER (WHERE conta = 'dividendos')         AS dividendos,
           max(valor) FILTER (WHERE conta = 'jcp')                AS jcp
    FROM cvm_dfp
    WHERE dt_receb IS NOT NULL
      AND (consolidado OR cnpj NOT IN (SELECT cnpj FROM cvm_dfp WHERE consolidado))
    GROUP BY cnpj, dt_refer, dt_receb, versao
),
com_balanco AS (
    SELECT b.*,
           c.patrimonio_liquido, c.ativo_total, c.lucro_liquido, c.receita,
           c.dividendos, c.jcp,
           c.dt_refer AS contabil_dt_refer,
           c.dt_receb AS contabil_dt_receb,
           c.versao   AS contabil_versao,
           c.contabil_consolidado
    FROM base b
    LEFT JOIN LATERAL (
        -- O que ja era PUBLICO no ultimo dia do mes. Entre versoes, a mais recente ja
        -- entregue ate essa data -- nunca a definitiva, que so existiu depois.
        SELECT * FROM dfp_wide d
        WHERE d.cnpj = b.cnpj AND d.dt_receb <= b.fim_do_mes
        ORDER BY d.dt_refer DESC, d.versao DESC
        LIMIT 1
    ) c ON TRUE
)
SELECT * EXCLUDE (fim_do_mes),
       -- Montados aqui porque o denominador (valor de mercado) e desta tabela e o
       -- numerador so existe depois do casamento point-in-time.
       patrimonio_liquido / nullif(valor_mercado_empresa, 0) AS book_to_market,
       lucro_liquido      / nullif(valor_mercado_empresa, 0) AS lucro_sobre_preco,
       lucro_liquido      / nullif(patrimonio_liquido, 0)    AS roe,
       lucro_liquido      / nullif(ativo_total, 0)           AS roa,
       -- DIVIDEND YIELD com a cobertura que a B3 nao da. O endpoint de provento da B3
       -- so conhece empresa viva; a DMPL da CVM alcanca quem entregou formulario, morta
       -- ou nao. E anual e por empresa (nao por acao), o que basta para o yield ser
       -- caracteristica de cross-section -- para ajustar retorno continua valendo a
       -- data-ex de `acoes_diario`, que esta e nao tem.
       (COALESCE(dividendos, 0) + COALESCE(jcp, 0))
         / nullif(valor_mercado_empresa, 0)                  AS dividend_yield,
       -- JCP tem 15% de IRRF na fonte para pessoa fisica. As duas versoes convivem, e a
       -- escolha vira campo do pre-registro -- mesma logica de "nao existe o preco".
       (COALESCE(dividendos, 0) + 0.85 * COALESCE(jcp, 0))
         / nullif(valor_mercado_empresa, 0)                  AS dividend_yield_liquido,
       date_diff('day', contabil_dt_refer, contabil_dt_receb) AS contabil_dias_ate_entrega,
       -- Idade do balanco usado. Serve de filtro: acima de ~450 dias a empresa esta
       -- atrasando entrega, e isso e informacao por si so.
       date_diff('day', contabil_dt_refer, fim_do_mes)        AS contabil_idade_dias
FROM com_balanco
ORDER BY cnpj, ano_mes
"""

SQL_SEM_BALANCO = SQL_BASE + """
SELECT * EXCLUDE (fim_do_mes) FROM base ORDER BY cnpj, ano_mes
"""


def construir() -> int:
    with warehouse.connect() as con:
        if not warehouse.table_exists(con, "acoes_diario"):
            raise RuntimeError("acoes_diario nao existe")
        tem_dfp = warehouse.table_exists(con, "cvm_dfp")
        if not tem_dfp:
            # Sem balanco o painel continua util para preco, retorno e tamanho; as
            # colunas contabeis simplesmente nao existem. Melhor do que falhar.
            print("  aviso: cvm_dfp nao existe -- painel sem colunas contabeis")
        sql = SQL_COM_BALANCO if tem_dfp else SQL_SEM_BALANCO
        con.execute(f"DROP TABLE IF EXISTS {TABELA}")
        con.execute(f"CREATE TABLE {TABELA} AS {sql}")
        return con.execute(f"SELECT count(*) FROM {TABELA}").fetchone()[0]


def resumo() -> pd.DataFrame:
    with warehouse.connect(read_only=True) as con:
        colunas = {c[0] for c in con.execute(f"DESCRIBE {TABELA}").fetchall()}
        extra = ""
        if "patrimonio_liquido" in colunas:
            extra = """,
                   round(100.0 * count(patrimonio_liquido) / count(*), 1)
                                                   AS pct_com_balanco,
                   round(100.0 * count(book_to_market) / count(*), 1)
                                                   AS pct_com_book_to_market"""
        return con.execute(f"""
            SELECT count(*)                        AS linhas,
                   count(DISTINCT cnpj)            AS emissores,
                   min(ano_mes)                    AS inicio,
                   max(ano_mes)                    AS fim,
                   round(100.0 * count(*) FILTER (WHERE classes_no_mes > 1)
                         / count(*), 1)            AS pct_com_2_classes,
                   round(100.0 * count(*) FILTER (WHERE trocou_de_classe)
                         / count(*), 2)            AS pct_trocou_de_classe,
                   round(100.0 * count(valor_mercado_empresa) / count(*), 1)
                                                   AS pct_com_valor_mercado{extra}
            FROM {TABELA}
        """).df()


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    n = construir()
    print(f"{TABELA}: {n:,} linhas (empresa-mes)\n")
    print(resumo().to_string(index=False))
