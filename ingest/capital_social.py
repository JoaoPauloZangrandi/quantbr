"""Quantidade de acoes em circulacao, da CVM -- a base do valor de mercado.

DE ONDE VEM

Formulario de Referencia (FRE), dois arquivos por ano, desde 2010:

  fre_cia_aberta_capital_social         -> Quantidade_Acoes_Ordinarias,
                                           Quantidade_Acoes_Preferenciais,
                                           Quantidade_Total_Acoes
  fre_cia_aberta_distribuicao_capital   -> as mesmas quantidades, mas EM CIRCULACAO
                                           (free float)

Conferido na Petrobras, FRE 2023: 7.442.454.142 ON + 5.602.042.788 PN = 13.044.496.930
no total, e 8.268.206.423 em circulacao (63,4%).

POR QUE AS DUAS MEDIDAS

  valor de mercado TOTAL      -> tamanho economico da empresa. E o que a literatura de
                                 asset pricing usa em size sorts e no fator SMB.
  valor de mercado FREE FLOAT -> o que da para efetivamente comprar. E o criterio dos
                                 provedores de indice, e o que importa para capacidade
                                 de estrategia.

Guardar as duas evita ter que escolher agora por um paper que ainda nao lemos.

FREQUENCIA E PONTO NO TEMPO

O FRE e ANUAL, com `Data_Referencia` em 31/12. Isso e mais grosso que o ideal, mas e o
padrao da maior parte da literatura, que usa contagem anual defasada. A defasagem correta
e aplicada em `painel.py`, nao aqui: o numero de acoes de 31/12/2023 so pode ser usado
depois que o documento foi entregue, senao entra look-ahead.

A PONTE ATE O TICKER

O FRE e chaveado por CNPJ e o painel por ticker, entao e preciso um vinculo. Ele sai do
FCA (`fca_cia_aberta_valor_mobiliario`), que traz CNPJ e Codigo_Negociacao no mesmo
registro. Limitacao conhecida e ja medida: esse campo esta vazio em cerca de metade das
linhas, e as vezes traz lixo ("4030", "NAO HA"). A cobertura resultante e reportada em vez
de mascarada -- casar por nome seria pior, porque "KLABIN S/A" casa com tres empresas
diferentes na CVM, duas delas canceladas.
"""
from __future__ import annotations

import io
import zipfile

import pandas as pd

import config
import warehouse
from ingest.base import download, now_utc

RAW_DIR = config.RAW / "cvm_fre"
URL_FRE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/fre_cia_aberta_{ano}.zip"
URL_FCA = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{ano}.zip"

ANO_INICIAL = 2010

COLS_CAPITAL = ["CNPJ_Companhia", "Data_Referencia", "Versao", "Nome_Companhia",
                "Tipo_Capital", "Quantidade_Acoes_Ordinarias",
                "Quantidade_Acoes_Preferenciais", "Quantidade_Total_Acoes"]
COLS_FLOAT = ["CNPJ_Companhia", "Data_Referencia", "Versao", "Nome_Companhia",
              "Quantidade_Acoes_Ordinarias_Circulacao",
              "Quantidade_Acoes_Preferenciais_Circulacao",
              "Quantidade_Total_Acoes_Circulacao",
              "Percentual_Total_Acoes_Circulacao"]


def _ler_do_zip(caminho, fragmento: str) -> pd.DataFrame:
    with zipfile.ZipFile(caminho) as zf:
        alvo = [n for n in zf.namelist() if fragmento in n]
        if not alvo:
            return pd.DataFrame()
        return pd.read_csv(io.BytesIO(zf.read(alvo[0])), sep=";",
                           encoding="latin-1", dtype=str)


def carregar_fre(anos: list[int]) -> dict[str, int]:
    capital, flutuante = [], []
    for ano in anos:
        try:
            caminho = download(URL_FRE.format(ano=ano), RAW_DIR / f"fre_{ano}.zip",
                               force=(ano == pd.Timestamp.today().year))
        except Exception as exc:
            print(f"  FRE {ano}: indisponivel ({type(exc).__name__})")
            continue

        # "capital_social" casa tambem com capital_social_aumento etc: exigir o nome exato
        cap = _ler_do_zip(caminho, f"capital_social_{ano}.csv")
        if not cap.empty:
            cap = cap[[c for c in COLS_CAPITAL if c in cap.columns]].copy()
            # Capital Integralizado e o que de fato existe emitido e pago.
            if "Tipo_Capital" in cap.columns:
                cap = cap[cap["Tipo_Capital"].str.contains("Integralizado", na=False)]
            cap["ano_fre"] = ano
            capital.append(cap)

        flo = _ler_do_zip(caminho, f"distribuicao_capital_{ano}.csv")
        if not flo.empty:
            flo = flo[[c for c in COLS_FLOAT if c in flo.columns]].copy()
            flo["ano_fre"] = ano
            flutuante.append(flo)
        print(f"  FRE {ano}: {len(cap):>5} capital, {len(flo):>5} free float")

    resultado = {}
    agora = now_utc()
    with warehouse.connect() as con:
        for tabela, partes in (("cvm_capital_social", capital),
                               ("cvm_free_float", flutuante)):
            if not partes:
                resultado[tabela] = 0
                continue
            df = pd.concat(partes, ignore_index=True)
            for c in df.columns:
                if c.startswith("Quantidade") or c.startswith("Percentual"):
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            df["Data_Referencia"] = pd.to_datetime(df["Data_Referencia"], errors="coerce")
            df["_source_file"] = "cvm/FRE"
            df["_downloaded_at"] = agora
            con.execute(f"DROP TABLE IF EXISTS {tabela}")
            con.register("_x", df)
            con.execute(f"CREATE TABLE {tabela} AS SELECT * FROM _x")
            con.unregister("_x")
            resultado[tabela] = len(df)
    return resultado


def carregar_ponte(anos: list[int]) -> int:
    """CNPJ <-> Codigo_Negociacao, do FCA, ano a ano."""
    partes = []
    for ano in anos:
        try:
            caminho = download(URL_FCA.format(ano=ano), RAW_DIR / f"fca_{ano}.zip",
                               force=(ano == pd.Timestamp.today().year))
        except Exception:
            continue
        df = _ler_do_zip(caminho, "valor_mobiliario")
        if df.empty:
            continue
        cols = ["CNPJ_Companhia", "Nome_Empresarial", "Codigo_Negociacao",
                "Valor_Mobiliario", "Data_Inicio_Negociacao", "Data_Fim_Negociacao"]
        df = df[[c for c in cols if c in df.columns]].copy()
        df["ano_fca"] = ano
        partes.append(df)

    if not partes:
        return 0
    todo = pd.concat(partes, ignore_index=True)
    todo["Codigo_Negociacao"] = todo["Codigo_Negociacao"].str.strip().str.upper()
    # Descarta os preenchimentos que nao sao ticker. Ticker da B3 e 4 letras + digitos.
    valido = todo["Codigo_Negociacao"].str.fullmatch(r"[A-Z]{4}[0-9]{1,2}", na=False)
    todo = todo[valido]
    todo["_source_file"] = "cvm/FCA"
    todo["_downloaded_at"] = now_utc()

    with warehouse.connect() as con:
        con.execute("DROP TABLE IF EXISTS cvm_ponte_ticker")
        con.register("_p", todo)
        con.execute("CREATE TABLE cvm_ponte_ticker AS SELECT * FROM _p")
        con.unregister("_p")
    return len(todo)


if __name__ == "__main__":
    anos = list(range(ANO_INICIAL, pd.Timestamp.today().year + 1))
    for tabela, n in carregar_fre(anos).items():
        print(f"{tabela:<22} {n:>7,} linhas")
    print(f"{'cvm_ponte_ticker':<22} {carregar_ponte(anos):>7,} linhas")
