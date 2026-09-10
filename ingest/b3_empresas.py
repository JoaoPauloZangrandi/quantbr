"""Cadastro de empresas listadas da B3 (GetInitialCompanies).

Serve de ponte entre o mundo do COTAHIST (ticker, ISIN) e o mundo dos eventos
corporativos da B3 (issuingCompany, tradingName, codeCVM). Sem essa ponte nao da pra
perguntar "quais foram os proventos da AESB3".

Limite verificado ao vivo: pageSize maximo aceito e 120; acima disso a API devolve
corpo vazio com status 200 (a mesma armadilha do BCB, em outra roupa).

Aviso importante sobre survivorship: este cadastro reflete o que a B3 mostra HOJE.
Empresa que saiu da bolsa pode ter sido removida. Por isso a tabela guarda snapshots
com `_downloaded_at` e nunca sobrescreve o passado -- com o tempo, o nosso proprio
historico de snapshots vira a fonte que a B3 nao mantem.
"""
from __future__ import annotations

import base64
import json

import pandas as pd

import warehouse
from ingest.base import get_json, now_utc

BASE = ("https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/"
        "CompanyCall/GetInitialCompanies/")
PAGE_SIZE = 120  # teto real da API


def _param(d: dict) -> str:
    return base64.b64encode(json.dumps(d).encode()).decode()


def buscar() -> pd.DataFrame:
    linhas, pagina, total_paginas = [], 1, None
    while total_paginas is None or pagina <= total_paginas:
        j = get_json(BASE + _param(
            {"language": "pt-br", "pageNumber": pagina, "pageSize": PAGE_SIZE}))
        if total_paginas is None:
            total_paginas = j["page"]["totalPages"]
            print(f"  {j['page']['totalRecords']:,} empresas em {total_paginas} paginas")
        linhas.extend(j.get("results", []))
        pagina += 1
    return pd.DataFrame(linhas)


def carregar() -> int:
    df = buscar()
    df.columns = [c.strip() for c in df.columns]
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].astype("string").str.strip()
    agora = now_utc()
    df["_source_file"] = "b3/GetInitialCompanies"
    df["_downloaded_at"] = agora
    df["_snapshot"] = agora.date().isoformat()

    with warehouse.connect() as con:
        warehouse.replace_partition(
            con, "b3_empresas", df, key="_snapshot", value=agora.date().isoformat())
    return len(df)


if __name__ == "__main__":
    print(f"{carregar():,} empresas carregadas")
