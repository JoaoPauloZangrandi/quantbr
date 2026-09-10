"""NEFIN (Center for Research in Financial Economics, USP).

Fonte oficial e academica dos fatores de risco brasileiros. Serve para tres coisas
distintas no quantbr:

  1. `nefin_fatores`  -> benchmark obrigatorio. Todo sinal novo tem que provar que
     sobrevive a controle por Rm-Rf, SMB, HML, WML e IML. Serie diaria desde 2001.
  2. `nefin_aluguel`  -> condicao AGREGADA de aluguel (taxa media e short interest medio).
     Nao substitui disponibilidade por papel (isso vem do BTB da B3, ver TODO abaixo),
     mas ja permite tratar "mercado de aluguel apertado" como regime.
  3. `nefin_carteiras` -> carteiras de referencia ordenadas por tamanho, B/M, momento e
     iliquidez. Usadas na calibracao da Fase 2: se o nosso motor nao reproduz essas
     carteiras a partir do COTAHIST, o motor esta errado, nao o NEFIN.

TODO(Fase 2): disponibilidade de aluguel POR PAPEL exige o arquivo diario de posicoes
em aberto de emprestimo de ativos (BTB) da B3. O agregado do NEFIN nao fecha o gate de
viabilidade de short sozinho.
"""
from __future__ import annotations

import pandas as pd

import config
import warehouse
from ingest.base import download, now_utc

BASE = "https://nefin.com.br"
RAW_DIR = config.RAW / "nefin"

ARQUIVOS = {
    "nefin_fatores": "/resources/risk_factors/nefin_factors.csv",
    "nefin_short_interest": "/resources/stock_loans/average_short_interest.csv",
    "nefin_loan_fee": "/resources/stock_loans/average_loan_fee.csv",
    "nefin_days_to_cover": "/resources/stock_loans/average_days_to_cover.csv",
    "nefin_dividend_yield": "/resources/Predictability/dividend_yield.csv",
}


def carregar_um(tabela: str, caminho: str) -> int:
    dest = RAW_DIR / caminho.rsplit("/", 1)[-1]
    # Series diarias sao reescritas a cada atualizacao do NEFIN: sempre force.
    path = download(BASE + caminho, dest, force=True)

    df = pd.read_csv(path)
    # nefin_factors.csv traz uma coluna de indice sem nome ("1","2",...)
    df = df.loc[:, ~df.columns.str.match(r"^Unnamed|^$")]
    df.columns = [c.strip().lower() for c in df.columns]
    col_data = "date" if "date" in df.columns else df.columns[0]
    df = df.rename(columns={col_data: "data"})
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df = df.dropna(subset=["data"]).reset_index(drop=True)

    df["_source_file"] = path.name
    df["_downloaded_at"] = now_utc()

    with warehouse.connect() as con:
        con.execute(f"DROP TABLE IF EXISTS {tabela}")
        con.register("_incoming", df)
        con.execute(f"CREATE TABLE {tabela} AS SELECT * FROM _incoming")
        con.unregister("_incoming")
    return len(df)


def carregar_tudo() -> dict[str, int]:
    return {tab: carregar_um(tab, cam) for tab, cam in ARQUIVOS.items()}


if __name__ == "__main__":
    for tab, n in carregar_tudo().items():
        print(f"{tab:<24} {n:>7,} linhas")
