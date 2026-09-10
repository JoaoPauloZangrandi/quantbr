"""Ponte complementar ticker -> CNPJ, para o que o FCA nao cobre.

O FCA da CVM resolve 580 dos 1.035 tickers de acao, e o que sobra inclui nomes grandes:
B3SA3, CSNA3, KLBN3/4, MBRF3, CMIN3. A causa e conhecida e medida -- o campo
`Codigo_Negociacao` do FCA esta vazio em cerca de metade das linhas.

O caminho aqui NAO e casar por nome. Casar por nome erra feio e em silencio: "KLABIN S/A"
casa com Klabin S.A., IKPC Klabin Papel Celulose e Klabin Segall, sendo duas delas
canceladas. O caminho e deterministico, em duas pernas:

    ticker -> emissor do ISIN (BRCSNAACNOR6 -> CSNA)
    emissor -> codeCVM, via GetListedSupplementCompany da B3
    codeCVM -> CNPJ, via cad_cia_aberta da CVM

GUARDA CONTRA FALSO PAR: a consulta da B3 casa por prefixo e ja devolveu um FUNDO
IMOBILIARIO ("FII TRPL") quando perguntamos por TRPL, que e a CTEEP. Por isso o vinculo so
e aceito quando o `tradingName` que a B3 devolve bate com o nome que o proprio COTAHIST
registra para aquele ticker. Se os nomes divergem, o par e descartado e fica contado como
nao resolvido -- e melhor faltar dado do que ter dado errado.
"""
from __future__ import annotations

import base64
import json
import time
import unicodedata

import pandas as pd
import requests

import config
import warehouse
from ingest.base import download, now_utc

BASE = ("https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/"
        "CompanyCall/GetListedSupplementCompany/")
HEADERS = {"User-Agent": "Mozilla/5.0 quantbr/0.1",
           "Accept": "application/json, text/plain, */*"}
URL_CADASTRO = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
PAUSA = 0.30


def _normalizar(texto: str) -> str:
    """Tira acento, pontuacao e espaco extra, para comparar nome com nome."""
    if not isinstance(texto, str):
        return ""
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "".join(ch for ch in t.upper() if ch.isalnum())


def _param(d: dict) -> str:
    return base64.b64encode(json.dumps(d).encode()).decode()


def emissores_sem_ponte() -> pd.DataFrame:
    with warehouse.connect(read_only=True) as con:
        return con.execute("""
            WITH tk AS (
                SELECT ticker, substr(any_value(isin), 3, 4) AS emissor,
                       any_value(empresa) AS empresa, count(*) AS pregoes
                FROM acoes_diario WHERE classe IN ('on','pn') GROUP BY ticker
            ),
            p AS (SELECT DISTINCT Codigo_Negociacao AS tk FROM cvm_ponte_ticker)
            SELECT emissor, any_value(empresa) AS empresa, sum(pregoes) AS pregoes
            FROM tk LEFT JOIN p ON p.tk = tk.ticker
            WHERE p.tk IS NULL AND tk.emissor IS NOT NULL
            GROUP BY emissor ORDER BY pregoes DESC
        """).df()


def carregar_cadastro_cvm() -> pd.DataFrame:
    caminho = download(URL_CADASTRO, config.RAW / "cvm_fre" / "cad_cia_aberta.csv",
                       force=True)
    df = pd.read_csv(caminho, sep=";", encoding="latin-1", dtype=str)
    return df[["CNPJ_CIA", "DENOM_SOCIAL", "CD_CVM", "SIT"]].dropna(subset=["CD_CVM"])


def construir() -> int:
    faltantes = emissores_sem_ponte()
    cadastro = carregar_cadastro_cvm()
    por_cvm = dict(zip(cadastro["CD_CVM"].str.strip().str.lstrip("0"),
                       cadastro["CNPJ_CIA"]))

    linhas, descartados = [], 0
    for i, r in enumerate(faltantes.itertuples(), 1):
        try:
            resp = requests.get(BASE + _param({"issuingCompany": r.emissor,
                                               "language": "pt-br"}),
                                headers=HEADERS, timeout=60)
            time.sleep(PAUSA)
            if resp.status_code != 200 or not resp.content.strip():
                continue
            bloco = resp.json()
            bloco = bloco[0] if isinstance(bloco, list) and bloco else None
        except Exception:
            continue
        if not bloco:
            continue

        nome_b3 = (bloco.get("tradingName") or "").strip()
        # GUARDA: o nome que a B3 devolve tem que bater com o do COTAHIST.
        if _normalizar(nome_b3) != _normalizar(r.empresa):
            descartados += 1
            continue

        cvm = str(bloco.get("codeCVM") or "").strip().lstrip("0")
        cnpj = por_cvm.get(cvm)
        if not cnpj:
            continue
        linhas.append({"emissor": r.emissor, "empresa": r.empresa,
                       "codigo_cvm": cvm, "cnpj": cnpj, "nome_b3": nome_b3})
        if i % 100 == 0:
            print(f"  {i}/{len(faltantes)} emissores, {len(linhas)} resolvidos")

    df = pd.DataFrame(linhas)
    print(f"\n  resolvidos: {len(df)} de {len(faltantes)} emissores sem ponte")
    print(f"  descartados por nome divergente: {descartados} "
          f"(guarda contra falso par tipo 'FII TRPL')")
    if df.empty:
        return 0
    df["_source_file"] = "b3/GetListedSupplementCompany + cvm/CAD"
    df["_downloaded_at"] = now_utc()

    with warehouse.connect() as con:
        con.execute("DROP TABLE IF EXISTS ponte_emissor_cnpj")
        con.register("_pe", df)
        con.execute("CREATE TABLE ponte_emissor_cnpj AS SELECT * FROM _pe")
        con.unregister("_pe")
    return len(df)


if __name__ == "__main__":
    print(f"{construir():,} emissores vinculados por ISIN -> codeCVM -> CNPJ")
