"""Painel mensal por EMISSOR -- a unidade em que teste de cross-section se faz.

POR QUE ESTA CAMADA EXISTE

`acoes_diario` e por PAPEL, e tem que ser: e o papel que se compra, e o custo, o lote e o
spread sao dele. Mas teste de cross-section nao se faz por papel, e sim por EMPRESA.

ON e PN da mesma companhia nao sao dois ativos independentes. Num sort por tamanho ou
valor, ITUB3 e ITUB4 entram como duas observacoes da MESMA firma: isso infla o N efetivo,
quebra a hipotese de independencia que o erro-padrao de Fama-MacBeth assume, e deixa uma
empresa ocupar duas vagas no mesmo decil. No Brasil o problema pesa mais que nos EUA --
temos muita companhia com duas classes negociando junto.

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


def construir() -> int:
    with warehouse.connect() as con:
        if not warehouse.table_exists(con, "acoes_diario"):
            raise RuntimeError("acoes_diario nao existe")

        con.execute(f"DROP TABLE IF EXISTS {TABELA}")
        con.execute(f"""
            CREATE TABLE {TABELA} AS
            WITH diario AS (
                -- So acao. Unit e ETF tem dinamica propria e nao entram em sort de
                -- caracteristica de empresa.
                SELECT a.*, strftime(a.data, '%Y-%m') AS ano_mes
                FROM acoes_diario a
                WHERE a.classe IN ('on', 'pn') AND a.cnpj IS NOT NULL
            ),
            -- Um registro por (empresa, classe, mes): o retorno composto do mes, a
            -- liquidez e o que mais o teste vai precisar.
            por_ticker AS (
                SELECT cnpj, ticker, ano_mes,
                       count(*)                                      AS pregoes_no_mes,
                       sum(volume)                                   AS volume_mes,
                       median(volume)                                AS volume_mediano,
                       last(fechamento ORDER BY data)                AS preco_fim,
                       last(valor_mercado_empresa ORDER BY data)     AS valor_mercado_empresa,
                       last(regime ORDER BY data)                    AS regime,
                       last(empresa ORDER BY data)                   AS nome,
                       last(motivo_saida ORDER BY data)              AS motivo_saida,
                       last(retorno_delisting ORDER BY data)         AS retorno_delisting,
                       last(retorno_delisting_conservador ORDER BY data)
                                                                     AS retorno_delisting_conservador,
                       -- Retorno composto do mes, a partir da primitiva diaria.
                       exp(sum(ln(1 + retorno_qtd)) FILTER (WHERE retorno_qtd > -1)) - 1
                                                                     AS retorno_qtd,
                       exp(sum(ln(1 + retorno_total)) FILTER (WHERE retorno_total > -1)) - 1
                                                                     AS retorno_total,
                       bool_or(tem_evento)                           AS teve_evento,
                       bool_or(tem_provento)                         AS teve_provento
                FROM diario
                GROUP BY cnpj, ticker, ano_mes
            ),
            -- A ESCOLHA DA CLASSE, POINT-IN-TIME E ESTAVEL.
            --
            -- Ordena pela liquidez dos 12 MESES ANTERIORES, nao pela do mes anterior.
            -- Duas razoes, e a segunda foi medida:
            --
            -- (1) point-in-time: em 1o de janeiro ninguem sabia qual classe seria a mais
            --     liquida em janeiro. Usar a liquidez do proprio mes e look-ahead, e pior,
            --     e look-ahead CORRELACIONADO com o resultado -- a classe que teve a
            --     noticia negociou mais naquele mes.
            -- (2) estabilidade: com janela de um mes, empresa iliquida troca de classe na
            --     metade dos meses. Medido: IGUACU CAFE 50,9%, ALFA HOLDING 49,8%,
            --     TELEMIG 42,9%. As duas classes mal negociam e "a mais liquida" vira
            --     ruido, produzindo um giro que nenhuma carteira real suportaria.
            --
            -- Janela longa e sticky por construcao, sem precisar de regra de buffer.
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
                           ORDER BY COALESCE(volume_mes_anterior, -1) DESC,
                                    volume_mes DESC, ticker
                       ) AS posicao,
                       count(*) OVER (PARTITION BY cnpj, ano_mes) AS classes_no_mes,
                       (volume_mes_anterior IS NULL)              AS escolha_sem_historico
                FROM com_liquidez_anterior
            )
            SELECT cnpj, ano_mes, ticker, nome, regime,
                   pregoes_no_mes, classes_no_mes, escolha_sem_historico,
                   preco_fim, volume_mes, volume_mediano, valor_mercado_empresa,
                   retorno_qtd, retorno_total,
                   teve_evento, teve_provento,
                   motivo_saida, retorno_delisting, retorno_delisting_conservador,
                   ticker <> lag(ticker) OVER (PARTITION BY cnpj ORDER BY ano_mes)
                     AS trocou_de_classe
            FROM ranqueado
            WHERE posicao = 1
            ORDER BY cnpj, ano_mes
        """)
        return con.execute(f"SELECT count(*) FROM {TABELA}").fetchone()[0]


def resumo() -> pd.DataFrame:
    with warehouse.connect(read_only=True) as con:
        return con.execute(f"""
            SELECT count(*)                                   AS linhas,
                   count(DISTINCT cnpj)                       AS emissores,
                   count(DISTINCT ticker)                     AS papeis_usados,
                   min(ano_mes)                               AS inicio,
                   max(ano_mes)                               AS fim,
                   round(100.0 * count(*) FILTER (WHERE classes_no_mes > 1)
                         / count(*), 1)                       AS pct_com_2_classes,
                   round(100.0 * count(*) FILTER (WHERE trocou_de_classe)
                         / count(*), 2)                       AS pct_trocou_de_classe,
                   round(100.0 * count(valor_mercado_empresa) / count(*), 1)
                                                              AS pct_com_valor_mercado,
                   round(100.0 * count(retorno_total) / count(*), 1)
                                                              AS pct_com_retorno_total
            FROM {TABELA}
        """).df()


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    n = construir()
    print(f"{TABELA}: {n:,} linhas (empresa-mes)\n")
    print(resumo().to_string(index=False))
