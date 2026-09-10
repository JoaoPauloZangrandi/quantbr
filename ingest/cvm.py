"""CVM Dados Abertos: cadastro de companhias e formulario cadastral (FCA).

Estas duas tabelas resolvem, juntas, o problema de identidade que nenhuma fonte de
preco resolve sozinha.

`cvm_cadastro` (cad_cia_aberta.csv)
    Uma linha por companhia, chaveada por CNPJ, com SIT (ATIVO/CANCELADA), DT_CANCEL e
    MOTIVO_CANCEL. Ao contrario do cadastro da B3 -- que so mostra empresa viva, checado
    ao vivo: 3.506 empresas, todas com status "A" -- a CVM mantem registro cancelado.
    Sao ~1.900 companhias canceladas, ~30 por ano. E esse fluxo que o yfinance apaga.
    ATENCAO: e um retrato de HOJE. O nome e a situacao sao os atuais, nao os da epoca.

`cvm_fca_valores` (FCA, um arquivo por ano)
    A ponte ticker <-> CNPJ COM DATA. Como existe um arquivo por ano, o nome empresarial
    e o codigo de negociacao ficam registrados como eram naquele ano. Exemplo real:
    CNPJ 02.998.611/0001-04 aparece como "CTEEP" com TRPL3/TRPL4 no FCA de 2023, e como
    "ISA ENERGIA BRASIL" com ISAE3/ISAE4 no de 2026. Agrupando por CNPJ, a cadeia de
    sucessao de ticker sai sozinha -- e o trabalho que antes era manual, um papel por vez.
"""
from __future__ import annotations

import io
import zipfile

import pandas as pd

import config
import warehouse
from ingest.base import download, now_utc

RAW_DIR = config.RAW / "cvm"
URL_CADASTRO = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
URL_FCA = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{ano}.zip"

COLS_CADASTRO = [
    "CNPJ_CIA", "DENOM_SOCIAL", "DENOM_COMERC", "DT_REG", "DT_CONST", "DT_CANCEL",
    "MOTIVO_CANCEL", "SIT", "DT_INI_SIT", "CD_CVM", "SETOR_ATIV", "TP_MERC",
    "CATEG_REG", "SIT_EMISSOR", "CONTROLE_ACIONARIO",
]


def carregar_cadastro() -> int:
    # Retrato do dia: sempre rebaixa, e guarda como snapshot datado.
    path = download(URL_CADASTRO, RAW_DIR / "cad_cia_aberta.csv", force=True)
    df = pd.read_csv(path, sep=";", encoding="latin-1", dtype=str)
    df = df[[c for c in COLS_CADASTRO if c in df.columns]].drop_duplicates()
    for c in ("DT_REG", "DT_CONST", "DT_CANCEL", "DT_INI_SIT"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")

    agora = now_utc()
    df["_source_file"] = path.name
    df["_downloaded_at"] = agora
    df["_snapshot"] = agora.date().isoformat()

    with warehouse.connect() as con:
        warehouse.replace_partition(con, "cvm_cadastro", df,
                                    key="_snapshot", value=agora.date().isoformat())
    return len(df)


def carregar_fca_ano(ano: int, *, force: bool = False) -> int:
    """Carrega o FCA de um ano. Anos passados nao mudam mais; so o corrente precisa force."""
    dest = RAW_DIR / f"fca_cia_aberta_{ano}.zip"
    try:
        path = download(URL_FCA.format(ano=ano), dest, force=force)
    except Exception as exc:
        print(f"  {ano}: indisponivel ({type(exc).__name__})")
        return 0

    with zipfile.ZipFile(path) as zf:
        alvo = [n for n in zf.namelist() if "valor_mobiliario" in n]
        if not alvo:
            print(f"  {ano}: zip sem valor_mobiliario")
            return 0
        df = pd.read_csv(io.BytesIO(zf.read(alvo[0])), sep=";", encoding="latin-1", dtype=str)

    df.columns = [c.strip() for c in df.columns]
    for c in ("Data_Inicio_Negociacao", "Data_Fim_Negociacao",
              "Data_Inicio_Listagem", "Data_Fim_Listagem", "Data_Referencia"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")

    df["ano_fca"] = ano
    df["_source_file"] = path.name
    df["_downloaded_at"] = now_utc()

    with warehouse.connect() as con:
        return warehouse.replace_partition(con, "cvm_fca_valores", df,
                                           key="ano_fca", value=ano)


if __name__ == "__main__":
    import sys

    print(f"cadastro: {carregar_cadastro():,} companhias")
    anos = [int(a) for a in sys.argv[1:]] or list(range(2010, 2027))
    total = 0
    for ano in anos:
        n = carregar_fca_ano(ano, force=(ano == pd.Timestamp.today().year))
        if n:
            print(f"  FCA {ano}: {n:,} valores mobiliarios")
        total += n
    print(f"FCA total: {total:,} linhas")
