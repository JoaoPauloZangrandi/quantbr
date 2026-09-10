"""Auditoria do securities master.

Este modulo existe por um pedido explicito: dado nao e algo que se confere uma vez e
declara pronto. O que ele mede nao e "passou/nao passou", e sim COBERTURA -- de quanto
do universo a gente consegue afirmar identidade, e de quanto nao consegue. Estrategia
rodada sobre a parte nao coberta nao esta errada, esta ENVIESADA, e a diferenca so
aparece se alguem medir e reportar.

Regra do projeto: nenhuma auditoria aqui tenta "consertar" o dado. Ela mede e reporta.
Conserto e decisao humana, e vira crosswalk versionado no repositorio.
"""
from __future__ import annotations

import pandas as pd

import warehouse


def _q(con, sql: str) -> pd.DataFrame:
    return con.execute(sql).df()


def cobertura_identidade() -> dict[str, pd.DataFrame]:
    """Quanto do universo de ACOES tem identidade resolvida."""
    with warehouse.connect(read_only=True) as con:
        por_classe = _q(con, """
            SELECT classe_papel,
                   situacao_vinculo,
                   count(*)                     AS tickers,
                   COALESCE(sum(n_pregoes), 0)  AS pregoes
            FROM master_ticker
            GROUP BY 1, 2
            ORDER BY 1, 4 DESC
        """)

        resumo_acoes = _q(con, """
            SELECT
                COALESCE(sum(n_pregoes) FILTER (WHERE situacao_vinculo = 'ok'), 0)      AS pregoes_com_cnpj,
                COALESCE(sum(n_pregoes) FILTER (WHERE situacao_vinculo <> 'ok'), 0)     AS pregoes_sem_cnpj,
                count(*) FILTER (WHERE situacao_vinculo = 'ok')                          AS tickers_com_cnpj,
                count(*) FILTER (WHERE situacao_vinculo <> 'ok')                         AS tickers_sem_cnpj
            FROM master_ticker
            WHERE classe_papel = 'acao'
        """)

        # Os sem-vinculo que mais doem sao os liquidos e longevos: um papel com 5.000
        # pregoes fora do universo distorce muito mais que 50 papeis com 20 pregoes.
        piores = _q(con, """
            SELECT ticker, emissor_isin, n_pregoes, primeiro_pregao, ultimo_pregao
            FROM master_ticker
            WHERE classe_papel = 'acao' AND situacao_vinculo = 'sem_vinculo_cvm'
            ORDER BY n_pregoes DESC NULLS LAST
            LIMIT 25
        """)
        return {"por_classe": por_classe, "resumo_acoes": resumo_acoes, "piores": piores}


def sucessoes_detectadas() -> pd.DataFrame:
    """Cadeias ticker->ticker cuja continuidade de pregao confirma a sucessao.

    O criterio nao e a CVM dizer que sao a mesma empresa: e a serie de pregoes encaixar.
    Se o ticker novo comeca a negociar dentro de poucos dias uteis do fim do antigo, a
    sucessao e real. Se ha meses de buraco, e outra coisa (reestruturacao, suspensao) e
    fica marcada como suspeita em vez de emendada em silencio.
    """
    with warehouse.connect(read_only=True) as con:
        return _q(con, """
            WITH pares AS (
                SELECT a.cnpj, e.nome_atual,
                       a.ticker AS ticker_anterior, a.ultimo_pregao  AS fim_anterior,
                       b.ticker AS ticker_seguinte, b.primeiro_pregao AS inicio_seguinte,
                       datediff('day', a.ultimo_pregao, b.primeiro_pregao) AS dias_de_buraco,
                       e.destino
                FROM master_ticker a
                JOIN master_ticker b
                  ON a.cnpj = b.cnpj AND a.ticker <> b.ticker
                 AND a.tipo_papel = b.tipo_papel
                 AND a.ultimo_pregao < b.primeiro_pregao
                LEFT JOIN master_empresa e ON e.cnpj = a.cnpj
                WHERE a.n_pregoes IS NOT NULL AND b.n_pregoes IS NOT NULL
            )
            SELECT *,
                   CASE WHEN dias_de_buraco <= 10 THEN 'sucessao_confirmada'
                        WHEN dias_de_buraco <= 90 THEN 'provavel'
                        ELSE 'suspeita' END AS veredito
            FROM pares
            ORDER BY dias_de_buraco
        """)


def delistings_por_ano() -> pd.DataFrame:
    """Quantas acoes deixaram de negociar por ano. Se der zero, o survivorship voltou."""
    with warehouse.connect(read_only=True) as con:
        return _q(con, """
            SELECT year(ultimo_pregao) AS ano_saida,
                   count(*)            AS tickers_que_pararam
            FROM master_ticker
            WHERE classe_papel = 'acao'
              AND n_pregoes >= 60
              AND ultimo_pregao < (SELECT max(data)::DATE - INTERVAL 30 DAY FROM b3_cotahist)
            GROUP BY 1
            HAVING year(ultimo_pregao) >= 2006
            ORDER BY 1
        """)


def relatorio() -> None:
    pd.set_option("display.width", 200)

    cob = cobertura_identidade()
    print("=" * 74)
    print("COBERTURA DE IDENTIDADE")
    print("=" * 74)
    print(cob["por_classe"].to_string(index=False))

    r = cob["resumo_acoes"].iloc[0]
    total = r["pregoes_com_cnpj"] + r["pregoes_sem_cnpj"]
    pct = 100 * r["pregoes_com_cnpj"] / total if total else 0
    print(f"\nSomente ACOES: {pct:.1f}% dos pregoes tem CNPJ resolvido "
          f"({r['pregoes_com_cnpj']:,.0f} de {total:,.0f}); "
          f"{r['tickers_sem_cnpj']:,} tickers pendentes.")

    print("\nOs 10 pendentes mais custosos (mais pregoes = mais distorcao):")
    print(cob["piores"].head(10).to_string(index=False))

    suc = sucessoes_detectadas()
    print("\n" + "=" * 74)
    print("SUCESSAO DE TICKER")
    print("=" * 74)
    if suc.empty:
        print("nenhuma cadeia encontrada")
    else:
        print(suc["veredito"].value_counts().to_string())
        print("\nConfirmadas (o ticker novo comeca logo apos o antigo parar):")
        conf = suc[suc["veredito"] == "sucessao_confirmada"]
        print(conf[["nome_atual", "ticker_anterior", "fim_anterior",
                    "ticker_seguinte", "inicio_seguinte", "dias_de_buraco",
                    "destino"]].head(15).to_string(index=False))

    print("\n" + "=" * 74)
    print("SAIDAS POR ANO (controle de survivorship)")
    print("=" * 74)
    d = delistings_por_ano()
    print(d.to_string(index=False))
    if (d["tickers_que_pararam"] == 0).any():
        print("\nALERTA: ano com zero saidas. Ou o dado esta incompleto, ou o filtro esta errado.")


if __name__ == "__main__":
    relatorio()
