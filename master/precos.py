"""MODULO MORTO -- NAO USE. Aguarda decisao do Joao para ser removido.

Ele le `eventos_detectados` e `b3_eventos_caixa`, tabelas apagadas na limpeza de escopo
de 02/09/2026. Nao roda. Quem constroi as tres series de preco hoje e `painel.py`, que
chama `master.eventos.detectar()` ao vivo.

Fica aqui por dois motivos: a docstring abaixo e o registro escrito da regra "nao existe
'o preco'", e apagar arquivo e acao destrutiva -- regra do projeto e que isso e decisao
humana. O que valia dele ja foi absorvido pelo painel.
"""

"""As tres series de preco, lado a lado.

Regra do projeto, definida explicitamente: NAO existe "o preco". Existem tres, e qual
usar depende do teste. Este modulo entrega as tres e nunca elege uma como padrao --
a escolha vira campo obrigatorio do pre-registro na camada de protocolo.

  fechamento_cru
      Exatamente o que negociou, sem tocar em nada. Serve para checagem contra fonte
      externa, para modelo de custo (corretagem incide sobre preco de verdade) e para
      qualquer coisa em que o nivel nominal importe.

  fechamento_ajustado_qtd
      Corrigido so por evento de QUANTIDADE (desdobramento, grupamento). Nao e opcional:
      sem isso um desdobramento 2:1 aparece como -50% de retorno, o que e simplesmente
      falso. E o default sensato para sinal de preco (momento, reversao, volatilidade).

  fechamento_retorno_total
      Corrigido tambem por provento (dividendo, JCP). E o retorno que o acionista de fato
      teve. Necessario quando o teste envolve carregar a posicao por muito tempo ou
      comparar com indice de retorno total. Cobertura INCOMPLETA e desigual -- ver abaixo.

Sobre a cobertura de provento, com todas as letras: a B3 apaga o historico de proventos
de quem sai da bolsa. Entao a serie de retorno total e boa para empresa viva e fraca ou
ausente para empresa morta -- justamente o oposto do que um estudo sem survivorship
precisa. Por isso cada linha carrega `cobertura_provento`, e qualquer resultado que use
esta serie tem que reportar a cobertura do universo junto. Serie com buraco nao e
proibida; serie com buraco nao declarado e.

Convencao de ajuste: retroativo (backward). O trecho mais recente fica com fator 1 e o
passado e corrigido, de modo que o preco de hoje na serie ajustada e igual ao preco de
hoje de verdade.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import warehouse

# Confiancas do detector que entram no ajuste. 'baixa' fica de fora de proposito:
# ajustar por evento duvidoso estraga a serie de um jeito dificil de perceber depois.
CONFIANCAS_ACEITAS = ("alta", "media")


def _eventos_quantidade(con) -> pd.DataFrame:
    ev = con.execute(f"""
        SELECT ticker, data::DATE AS data_ex, fator_sugerido AS fator, confianca
        FROM eventos_detectados
        WHERE confianca IN {CONFIANCAS_ACEITAS}
          AND fator_sugerido IS NOT NULL AND fator_sugerido > 0
    """).df()
    return ev


def _proventos(con) -> pd.DataFrame:
    """Proventos da B3, com a data-ex derivada da ultima data COM direito."""
    try:
        prov = con.execute("""
            SELECT isin,
                   try_strptime(ultima_data_com, '%d/%m/%Y')::DATE AS data_com,
                   TRY_CAST(replace(valor_por_acao, ',', '.') AS DOUBLE) AS valor,
                   tipo
            FROM b3_eventos_caixa
            WHERE _snapshot = (SELECT max(_snapshot) FROM b3_eventos_caixa)
        """).df()
    except Exception:
        return pd.DataFrame(columns=["isin", "data_com", "valor", "tipo"])
    return prov.dropna(subset=["data_com", "valor"]).query("valor > 0")


def construir() -> int:
    with warehouse.connect(read_only=True) as con:
        px = con.execute("""
            SELECT ticker, isin, data::DATE AS data, fechamento, abertura, maxima, minima,
                   quantidade, volume, negocios
            FROM b3_cotahist
            WHERE codbdi = '02' AND tpmerc = '010' AND fechamento > 0
            ORDER BY ticker, data
        """).df()
        ev = _eventos_quantidade(con)
        prov = _proventos(con)

    px["data"] = pd.to_datetime(px["data"])

    # ---------- fator de quantidade, acumulado retroativamente ----------
    # cum(d) = produto dos fatores de todo evento com data_ex > d. Assim o trecho mais
    # recente fica com 1 e o passado e que se ajusta.
    if ev.empty:
        px["fator_qtd_acum"] = 1.0
    else:
        ev["data_ex"] = pd.to_datetime(ev["data_ex"])
        ev = ev.groupby(["ticker", "data_ex"], as_index=False)["fator"].prod()
        marca = px.merge(ev, left_on=["ticker", "data"], right_on=["ticker", "data_ex"],
                         how="left")["fator"].fillna(1.0).to_numpy()
        px["_fator_no_dia"] = marca
        # produto acumulado de tras para frente, EXCLUINDO o proprio dia:
        # o preco do dia ex ja vem dividido pelo mercado.
        def _acum(s: pd.Series) -> pd.Series:
            invertido = s.iloc[::-1]
            return invertido.shift(1).fillna(1.0).cumprod().iloc[::-1]
        px["fator_qtd_acum"] = px.groupby("ticker", sort=False)["_fator_no_dia"].transform(_acum)
        px = px.drop(columns=["_fator_no_dia"])

    px["fechamento_ajustado_qtd"] = px["fechamento"] / px["fator_qtd_acum"]

    # ---------- provento ----------
    # O ajuste por provento entra como RAZAO usando o preco contemporaneo:
    #   r = (P_ant - D) / P_ant
    # Isso e livre de escala, entao nao precisa corrigir o dividendo historico por
    # desdobramento posterior -- armadilha classica quando se soma valor em vez de razao.
    px["fech_ant"] = px.groupby("ticker", sort=False)["fechamento"].shift(1)
    if prov.empty:
        px["fator_prov_acum"] = 1.0
        px["cobertura_provento"] = False
    else:
        prov["data_com"] = pd.to_datetime(prov["data_com"])
        por_isin = prov.groupby(["isin", "data_com"], as_index=False)["valor"].sum()

        # data ex = primeiro pregao do papel APOS a ultima data com direito
        px = px.sort_values(["isin", "data"])
        casado = pd.merge_asof(
            por_isin.sort_values("data_com"),
            px[["isin", "data"]].sort_values("data"),
            left_on="data_com", right_on="data", by="isin", direction="forward",
            allow_exact_matches=False,
        ).rename(columns={"data": "data_ex"}).dropna(subset=["data_ex"])

        # Duas datas-com distintas podem cair no MESMO pregao seguinte (dividendo e JCP
        # aprovados em dias diferentes, ou feriado no meio). Sem consolidar aqui, o merge
        # abaixo multiplica linhas do painel de precos -- o sintoma foi o painel ganhar
        # 2 linhas do nada. Somar e o tratamento certo: no dia ex o papel perde os dois.
        casado = casado.groupby(["isin", "data_ex"], as_index=False)["valor"].sum()

        px = px.sort_values(["ticker", "data"])
        div = px.merge(casado[["isin", "data_ex", "valor"]],
                       left_on=["isin", "data"], right_on=["isin", "data_ex"],
                       how="left")["valor"].to_numpy()
        px["_dividendo"] = div
        razao = 1.0 - (px["_dividendo"] / px["fech_ant"])
        # Provento maior que o preco do dia anterior indica dado ruim (ou evento especial
        # que nao e dividendo comum). Nao ajusta e deixa registrado em vez de gerar preco
        # negativo silenciosamente.
        px["_provento_suspeito"] = razao.notna() & (razao <= 0)
        px["_razao_prov"] = razao.where(razao > 0, 1.0).fillna(1.0)

        def _acum_prov(s: pd.Series) -> pd.Series:
            invertido = s.iloc[::-1]
            return invertido.shift(1).fillna(1.0).cumprod().iloc[::-1]
        px["fator_prov_acum"] = px.groupby("ticker", sort=False)["_razao_prov"].transform(_acum_prov)

        # Cobertura: o ISIN aparece em algum provento? Se nunca aparece, a serie de
        # retorno total daquele papel e igual a de quantidade -- e isso NAO significa que
        # a empresa nunca pagou dividendo, significa que nos nao sabemos.
        com_dado = set(prov["isin"].dropna())
        px["cobertura_provento"] = px["isin"].isin(com_dado)

    px["fechamento_retorno_total"] = px["fechamento_ajustado_qtd"] * px["fator_prov_acum"]

    # ---------- retornos ----------
    g = px.groupby("ticker", sort=False)
    for origem, destino in (("fechamento", "retorno_cru"),
                            ("fechamento_ajustado_qtd", "retorno_qtd"),
                            ("fechamento_retorno_total", "retorno_total")):
        px[destino] = g[origem].pct_change()

    cols = ["ticker", "isin", "data",
            "fechamento", "fechamento_ajustado_qtd", "fechamento_retorno_total",
            "retorno_cru", "retorno_qtd", "retorno_total",
            "fator_qtd_acum", "fator_prov_acum", "cobertura_provento",
            "abertura", "maxima", "minima", "quantidade", "volume", "negocios"]
    if "_provento_suspeito" in px.columns:
        px["provento_suspeito"] = px["_provento_suspeito"].fillna(False)
        cols.append("provento_suspeito")
    saida = px[cols].sort_values(["ticker", "data"]).reset_index(drop=True)

    with warehouse.connect() as con:
        con.execute("DROP TABLE IF EXISTS precos_diarios")
        con.register("_px", saida)
        con.execute("CREATE TABLE precos_diarios AS SELECT * FROM _px")
        con.unregister("_px")
    return len(saida)


if __name__ == "__main__":
    n = construir()
    print(f"{n:,} linhas em precos_diarios")
    with warehouse.connect(read_only=True) as con:
        print()
        print(con.execute("""
            SELECT count(DISTINCT ticker) tickers,
                   count(*) FILTER (WHERE fator_qtd_acum <> 1)  linhas_com_ajuste_qtd,
                   count(*) FILTER (WHERE cobertura_provento)   linhas_com_provento
            FROM precos_diarios
        """).df().to_string(index=False))
