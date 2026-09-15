"""Gabarito de evento de quantidade, publicado pela CVM.

O QUE E, E POR QUE ELE MUDA O JOGO

`master/eventos.py` DETECTA desdobramento e grupamento a partir do preco, porque a B3
apaga o historico de evento de quem sai da bolsa. Detectar do preco funciona, mas paga um
preco: o detector precisa provar cada evento com fracao redonda, tolerancia calibrada e
tres confirmacoes indiretas -- e ainda assim erra nos dois extremos (papel de centavos,
evento no mesmo dia de um provento).

Este arquivo e a fonte que dispensa a prova, para os casos em que ela existe:

  fre_cia_aberta_capital_social_desdobramento_AAAA.csv   (dentro do zip do FRE da CVM)

Cada linha traz TIPO declarado (Grupamento / Desdobramento / Bonificacao), DATA DE
APROVACAO e a QUANTIDADE DE ACOES ANTES E DEPOIS -- ou seja, o FATOR EXATO, medido fora
da B3 e fora do preco. O arquivo ja era baixado pelo coletor de capital social desde o
inicio do projeto e nunca tinha sido aberto.

O CASO QUE OBRIGOU A CONSTRUIR ISTO (14/09/2026)

A RLOG3 estava marcada como possivel grupamento residual: razao de preco 3,88x, abaixo do
corte de 5x, sem corroboracao de volume, e por isso NAO ajustada. Ela carregava +372% de
retorno mensal em junho/2016, dentro do universo eligivel. O gabarito responde sem
ambiguidade:

  COSAN LOGISTICA S.A. | Grupamento | aprovado em 14/03/2016
  1.460.402.269 -> 365.100.567 acoes | razao exatamente 4,000

O QUE ESTE MODULO NAO FAZ

Nao substitui o detector, e nao pode. Tres limites, todos medidos:

  1. **Cobertura**: o FRE comeca em 2010 e so existe para quem estava aberto na CVM.
     Metade do backtest (2005-2009) nao tem gabarito nenhum.
  2. **A data e a da APROVACAO (AGE/RCA), nao a data ex da B3.** Entre uma e outra passam
     dias ou meses. O gabarito diz QUE houve e QUAL o fator; o preco continua sendo quem
     diz QUANDO.
  3. **Nao e por classe de papel na tabela principal.** ON e PN vem somados; o arquivo
     `_classe_acao` desagrega a parte preferencial e por isso tambem e lido.

Entao a arquitetura e: **o gabarito entra como quarta evidencia independente**, nao como
substituto. Quem cria o candidato continua sendo o salto de preco.
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

ANO_INICIAL = 2010

COLS = ["CNPJ_Companhia", "Data_Referencia", "Versao", "ID_Documento", "Nome_Companhia",
        "ID_Capital_Social_Desdobramento", "Data_Aprovacao", "Tipo_Evento",
        "Quantidade_Acoes_Ordinarias_Antes_Aprovacao",
        "Quantidade_Acoes_Preferenciais_Antes_Aprovacao",
        "Quantidade_Total_Acoes_Antes_Aprovacao",
        "Quantidade_Acoes_Ordinarias_Depois_Aprovacao",
        "Quantidade_Acoes_Preferenciais_Depois_Aprovacao",
        "Quantidade_Total_Acoes_Depois_Aprovacao"]


def _ler_do_zip(caminho, nome_exato: str) -> pd.DataFrame:
    with zipfile.ZipFile(caminho) as zf:
        if nome_exato not in zf.namelist():
            return pd.DataFrame()
        return pd.read_csv(io.BytesIO(zf.read(nome_exato)), sep=";",
                           encoding="latin-1", dtype=str)


def _numerico(df: pd.DataFrame, prefixo: str = "Quantidade") -> pd.DataFrame:
    for c in df.columns:
        if c.startswith(prefixo):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def coletar(anos: list[int] | None = None) -> pd.DataFrame:
    """Le o gabarito de todos os anos e devolve UM registro por evento distinto.

    A deduplicacao e a parte que exige cuidado. O mesmo evento aparece em varios FREs: a
    Telebras declara em 2016 um grupamento aprovado em 2010, e volta a declara-lo em 2017,
    2018... Contar as linhas daria a impressao de milhares de eventos onde ha centenas. A
    chave de identidade e (CNPJ, data de aprovacao, tipo, quantidade antes, quantidade
    depois) -- nao o `ID_Capital_Social_Desdobramento`, que e ID DE DOCUMENTO e muda a cada
    entrega. Entre as repeticoes fica a MAIS RECENTE (maior ano do FRE, depois maior
    versao), que e a versao corrigida caso a empresa tenha retificado.
    """
    anos = anos or list(range(ANO_INICIAL, pd.Timestamp.today().year + 1))
    partes = []
    for ano in anos:
        try:
            caminho = download(URL_FRE.format(ano=ano), RAW_DIR / f"fre_{ano}.zip",
                               force=(ano == pd.Timestamp.today().year))
        except Exception as exc:
            print(f"  FRE {ano}: indisponivel ({type(exc).__name__})")
            continue

        df = _ler_do_zip(caminho, f"fre_cia_aberta_capital_social_desdobramento_{ano}.csv")
        if not df.empty:
            df = df[[c for c in COLS if c in df.columns]].copy()
            df["ano_fre"] = ano
            partes.append(df)
        print(f"  FRE {ano}: {len(df):>5} linhas de evento")

    if not partes:
        return pd.DataFrame()

    todo = _numerico(pd.concat(partes, ignore_index=True))
    todo["Versao"] = pd.to_numeric(todo["Versao"], errors="coerce").fillna(0).astype(int)
    todo["cnpj"] = (todo["CNPJ_Companhia"].str.replace(r"[^0-9]", "", regex=True)
                    .str.zfill(14))
    todo["data_aprovacao"] = pd.to_datetime(todo["Data_Aprovacao"], errors="coerce")
    todo["tipo_evento"] = todo["Tipo_Evento"].str.strip()

    chave = ["cnpj", "data_aprovacao", "tipo_evento",
             "Quantidade_Total_Acoes_Antes_Aprovacao",
             "Quantidade_Total_Acoes_Depois_Aprovacao"]
    todo = (todo.sort_values(["ano_fre", "Versao"])
                .drop_duplicates(subset=chave, keep="last")
                .reset_index(drop=True))

    # Fator por classe, e nao so o total. Importa porque o painel e por TICKER: um evento
    # que so atinge a PN (ou uma recompra de ON no mesmo ato) tem fator total diferente do
    # fator que o preco da ON viu.
    def _fator(depois: str, antes: str) -> pd.Series:
        r = todo[depois] / todo[antes].where(todo[antes] > 0)
        return r.where(r > 0)

    todo["fator_total"] = _fator("Quantidade_Total_Acoes_Depois_Aprovacao",
                                 "Quantidade_Total_Acoes_Antes_Aprovacao")
    todo["fator_on"] = _fator("Quantidade_Acoes_Ordinarias_Depois_Aprovacao",
                              "Quantidade_Acoes_Ordinarias_Antes_Aprovacao")
    todo["fator_pn"] = _fator("Quantidade_Acoes_Preferenciais_Depois_Aprovacao",
                              "Quantidade_Acoes_Preferenciais_Antes_Aprovacao")

    saida = todo[["cnpj", "Nome_Companhia", "tipo_evento", "data_aprovacao",
                  "Quantidade_Total_Acoes_Antes_Aprovacao",
                  "Quantidade_Total_Acoes_Depois_Aprovacao",
                  "Quantidade_Acoes_Ordinarias_Antes_Aprovacao",
                  "Quantidade_Acoes_Ordinarias_Depois_Aprovacao",
                  "Quantidade_Acoes_Preferenciais_Antes_Aprovacao",
                  "Quantidade_Acoes_Preferenciais_Depois_Aprovacao",
                  "fator_total", "fator_on", "fator_pn",
                  "ano_fre", "Versao", "ID_Documento"]].copy()
    saida.columns = ["cnpj", "empresa", "tipo_evento", "data_aprovacao",
                     "qtd_total_antes", "qtd_total_depois",
                     "qtd_on_antes", "qtd_on_depois",
                     "qtd_pn_antes", "qtd_pn_depois",
                     "fator_total", "fator_on", "fator_pn",
                     "ano_fre", "versao", "id_documento"]
    return saida


def gravar(df: pd.DataFrame) -> int:
    df = df.copy()
    df["_source_file"] = "cvm/FRE/capital_social_desdobramento"
    df["_downloaded_at"] = now_utc()
    with warehouse.connect() as con:
        con.execute("DROP TABLE IF EXISTS cvm_eventos_anunciados")
        con.register("_ev", df)
        con.execute("CREATE TABLE cvm_eventos_anunciados AS SELECT * FROM _ev")
        con.unregister("_ev")
    return len(df)


if __name__ == "__main__":
    ev = coletar()
    if ev.empty:
        raise SystemExit("nenhum evento lido")
    n = gravar(ev)
    print()
    print(f"{n:,} eventos distintos, {ev['cnpj'].nunique():,} empresas, "
          f"{ev['data_aprovacao'].min():%Y-%m-%d} a {ev['data_aprovacao'].max():%Y-%m-%d}")
    print()
    print(ev["tipo_evento"].value_counts().to_string())
