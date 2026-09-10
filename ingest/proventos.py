"""Proventos em dinheiro (dividendo e JCP) da B3.

POR QUE ESTE ENDPOINT E NAO O OUTRO

Existem dois na B3 e a diferenca e grande. O `GetListedSupplementCompany`, usado numa
primeira tentativa, devolve so um punhado de registros recentes: 24 para a Petrobras.
O `GetListedCashDividends`, paginado, devolve **343 para a Petrobras, 956 para o Itau,
152 para a Vale**. E o unico dos dois que serve para montar serie historica.

Teto de pagina medido: 120. Acima disso a resposta volta vazia com status 200 -- a mesma
armadilha ja vista no cadastro de empresas e na API do BCB.

CHAVE DE CONSULTA

O endpoint e chaveado por `tradingName`, nao por ticker. Felizmente o campo `nome_res` do
COTAHIST e exatamente esse nome ("PETROBRAS", "ITAUUNIBANCO", "ACO ALTONA"), entao a ponte
sai do proprio dado que ja temos, sem depender de cadastro externo.

Cada registro traz `typeStock` (ON, PN, PNA...), que mapeia para o sufixo do ticker pela
convencao da B3: 3=ON, 4=PN, 5=PNA, 6=PNB, 7=PNC, 8=PND, 11=UNT.

LIMITACAO QUE PRECISA FICAR REGISTRADA

A cobertura de empresa que saiu da bolsa e PARCIAL. AES Brasil devolve 4 registros,
3R Petroleum devolve 1, Sequoia devolve zero. Sao empresas que pagaram provento por anos.
Ou seja: a serie de retorno total e boa para quem esta vivo e fraca para quem morreu --
exatamente o oposto do que um estudo sem survivorship precisa.

Isso NAO invalida a serie, mas obriga a reportar cobertura junto de qualquer resultado que
a use. Serie com buraco nao e proibida; serie com buraco nao declarado e.
"""
from __future__ import annotations

import base64
import json
import time

import pandas as pd
import requests

import config
import warehouse
from ingest.base import now_utc

BASE = ("https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/"
        "CompanyCall/GetListedCashDividends/")
HEADERS = {"User-Agent": "Mozilla/5.0 quantbr/0.1",
           "Accept": "application/json, text/plain, */*"}
PAGE_SIZE = 120   # teto real, medido
PAUSA = 0.30      # cortesia com o servidor da B3

# typeStock da B3 -> sufixo do ticker
SUFIXO_POR_TIPO = {
    "ON": "3", "PN": "4", "PNA": "5", "PNB": "6", "PNC": "7", "PND": "8",
    "UNT": "11", "ON ED": "3", "PN ED": "4",
}


def _param(d: dict) -> str:
    return base64.b64encode(json.dumps(d).encode()).decode()


def buscar_empresa(nome: str) -> list[dict]:
    linhas, pagina, total_paginas = [], 1, None
    while total_paginas is None or pagina <= total_paginas:
        url = BASE + _param({"language": "pt-br", "pageNumber": pagina,
                             "pageSize": PAGE_SIZE, "tradingName": nome})
        r = requests.get(url, headers=HEADERS, timeout=90)
        if r.status_code != 200 or not r.content.strip():
            break
        try:
            j = r.json()
        except ValueError:
            break
        if total_paginas is None:
            total_paginas = (j.get("page") or {}).get("totalPages") or 0
            if not total_paginas:
                break
        for reg in j.get("results") or []:
            reg["empresa"] = nome
            linhas.append(reg)
        pagina += 1
        time.sleep(PAUSA)
    return linhas


def empresas_do_painel() -> list[str]:
    with warehouse.connect(read_only=True) as con:
        return [r[0] for r in con.execute("""
            SELECT DISTINCT empresa FROM acoes_diario
            WHERE empresa IS NOT NULL AND trim(empresa) <> ''
            ORDER BY 1
        """).fetchall()]


def candidatos_por_cnpj() -> pd.DataFrame:
    """Todos os nomes por que vale tentar cada CNPJ, e de onde cada nome veio.

    POR QUE MAIS DE UM NOME. O endpoint e chaveado por um nome exato, e nenhum campo
    sozinho acerta. Medido ao vivo em 10/09/2026:

        emissor  companyName          registros | tradingName    registros
        ABEV     AMBEV S.A.                  39 | AMBEV S/A              0
        KLBN     KLABIN S.A.                219 | KLABIN S/A             0
        VALE     VALE S.A.                    0 | VALE                 152
        TIMS     TIM S.A.                     0 | TIM                   34
        SUZB     SUZANO S.A.                 72 | SUZANO S.A.           72

    Ora um, ora o outro. E o `nome_res` do COTAHIST, que era a unica fonte usada antes,
    e truncado em 12 caracteres -- "AMBEV S/A" nao existe para o endpoint, e por isso a
    ABEV3 ficou treze anos com ZERO dividendo na base enquanto os 39 registros estavam
    la o tempo todo, atras do nome "AMBEV S.A.".

    O nome_res historico continua entrando: e o unico que alcanca empresa que ja morreu,
    e que por isso sumiu do cadastro da B3.

    Cada linha sai com o CNPJ junto, e e ele -- nao o nome -- que liga o provento ao
    ticker depois. Nome muda; CNPJ nao.

    ARMADILHA, paga uma vez: a B3 devolve o CNPJ SEM o zero a esquerda
    ("7526557000100") e a CVM COM ele ("07.526.557/0001-00" -> "07526557000100"). Sem
    normalizar o comprimento, o casamento falha calado para toda empresa cujo CNPJ comeca
    com zero -- e foi assim que a primeira rodada trouxe a Klabin (CNPJ 896...) e deixou a
    Ambev (CNPJ 075...) de fora outra vez, pelo motivo errado. Daí o `lpad(..., 14, '0')`.
    """
    with warehouse.connect(read_only=True) as con:
        partes = []
        if warehouse.table_exists(con, "b3_empresas"):
            partes.append(con.execute("""
                SELECT DISTINCT
                       lpad(regexp_replace(cnpj, '[^0-9]', '', 'g'), 14, '0') AS cnpj_num,
                       companyName AS nome, 'b3_companyName' AS origem
                FROM b3_empresas
                WHERE _snapshot = (SELECT max(_snapshot) FROM b3_empresas)
                  AND companyName IS NOT NULL AND trim(companyName) <> ''
                UNION
                SELECT DISTINCT
                       lpad(regexp_replace(cnpj, '[^0-9]', '', 'g'), 14, '0'),
                       tradingName, 'b3_tradingName'
                FROM b3_empresas
                WHERE _snapshot = (SELECT max(_snapshot) FROM b3_empresas)
                  AND tradingName IS NOT NULL AND trim(tradingName) <> ''
            """).df())
        if warehouse.table_exists(con, "master_ticker"):
            partes.append(con.execute("""
                SELECT DISTINCT
                       regexp_replace(m.cnpj, '[^0-9]', '', 'g') AS cnpj_num,
                       a.empresa AS nome, 'cotahist_nome_res' AS origem
                FROM master_ticker m
                JOIN acoes_diario a ON a.ticker = m.ticker
                WHERE m.cnpj IS NOT NULL AND a.empresa IS NOT NULL
            """).df())
    if not partes:
        return pd.DataFrame(columns=["cnpj_num", "nome", "origem"])
    df = pd.concat(partes, ignore_index=True)
    df["nome"] = df["nome"].astype(str).str.strip()
    df = df[df["nome"] != ""].drop_duplicates(["cnpj_num", "nome"])

    # So os CNPJs que de fato negociam no painel. O cadastro da B3 tem 3.522 companhias,
    # boa parte emissora de BDR ou sem acao no nosso universo -- consultar todas seria
    # horas de requisicao para dado que nao usamos.
    with warehouse.connect(read_only=True) as con:
        if warehouse.table_exists(con, "master_ticker"):
            do_painel = con.execute("""
                SELECT DISTINCT lpad(regexp_replace(cnpj, '[^0-9]', '', 'g'), 14, '0') AS cnpj_num
                FROM master_ticker WHERE cnpj IS NOT NULL AND n_pregoes IS NOT NULL
            """).df()
            df = df.merge(do_painel, on="cnpj_num", how="inner")
    return df


def carregar_por_cnpj(candidatos: pd.DataFrame | None = None) -> int:
    """Baixa provento tentando todos os nomes de cada CNPJ, e grava o CNPJ na linha.

    A deduplicacao e por (cnpj, tipo_acao, data_com, valor, tipo_provento): quando dois
    nomes do mesmo CNPJ devolvem o mesmo pagamento, ele entra uma vez so. Quando devolvem
    periodos diferentes -- que e o caso da Ambev, "AMBEV" ate 2013 e "AMBEV S.A." depois
    --, os dois entram e a serie fica inteira.
    """
    cand = candidatos if candidatos is not None else candidatos_por_cnpj()
    if cand.empty:
        print("  nenhum candidato -- rode ingest.b3_empresas e master.identidade antes")
        return 0

    todos, cnpjs_sem_dado = [], set(cand["cnpj_num"])
    for i, (_, linha) in enumerate(cand.iterrows(), 1):
        try:
            registros = buscar_empresa(linha["nome"])
        except Exception as exc:
            print(f"  aviso: {linha['nome']!r} falhou ({type(exc).__name__})")
            continue
        for reg in registros:
            reg["cnpj"] = linha["cnpj_num"]
            reg["nome_consultado"] = linha["nome"]
            reg["origem_do_nome"] = linha["origem"]
        if registros:
            cnpjs_sem_dado.discard(linha["cnpj_num"])
        todos.extend(registros)
        if i % 200 == 0:
            print(f"  {i}/{len(cand)} nomes, {len(todos):,} proventos ate aqui")

    df = pd.DataFrame(todos)
    if df.empty:
        return 0
    df = df.rename(columns=RENOMEAR)
    manter = ["cnpj", "nome_consultado", "origem_do_nome", "empresa", "tipo_acao",
              "tipo_provento", "ultima_data_com", "valor_por_acao", "cotado_por_acoes",
              "fechamento_b3_data_com", "data_aprovacao", "razao"]
    df["empresa"] = df["nome_consultado"]
    df = df[[c for c in manter if c in df.columns]]
    # O mesmo pagamento chega por mais de um nome do mesmo CNPJ. Chave economica:
    # quem pagou, que classe, quando, quanto e a que titulo.
    df = df.drop_duplicates(["cnpj", "tipo_acao", "ultima_data_com",
                             "valor_por_acao", "tipo_provento"])

    agora = now_utc()
    df["_source_file"] = "b3/GetListedCashDividends"
    df["_downloaded_at"] = agora
    df["_snapshot"] = agora.date().isoformat()

    # O BRUTO VAI PARA O DISCO ANTES DO BANCO. Isto nasceu de um prejuizo concreto:
    # em 10/09/2026 a coleta rodou os 926 nomes por ~30 minutos e morreu na ultima linha,
    # com "Table b3_proventos does not have a column with name cnpj" -- `replace_partition`
    # insere numa tabela existente, e o schema tinha mudado. Trinta minutos de requisicao
    # a B3 foram jogados fora por um erro que so aparece no fim. Gravando antes, uma falha
    # de schema custa um `read_parquet`, nao outra coleta.
    destino = config.RAW / "b3_proventos"
    destino.mkdir(parents=True, exist_ok=True)
    df.to_parquet(destino / f"proventos_{agora.date().isoformat()}.parquet", index=False)

    with warehouse.connect() as con:
        # Schema novo (ganhou cnpj, nome_consultado, origem_do_nome) nao cabe na tabela
        # antiga. O snapshot velho e superado por este -- mesmas empresas, mais nomes --
        # entao a tabela e recriada em vez de receber INSERT.
        if warehouse.table_exists(con, "b3_proventos"):
            atuais = {c[0] for c in con.execute("DESCRIBE b3_proventos").fetchall()}
            if not set(df.columns).issubset(atuais):
                print("  schema mudou -- recriando b3_proventos")
                con.execute("DROP TABLE b3_proventos")
        warehouse.replace_partition(con, "b3_proventos", df,
                                    key="_snapshot", value=agora.date().isoformat())
    print(f"  {len(df):,} proventos de {df['cnpj'].nunique():,} CNPJs")
    print(f"  {len(cnpjs_sem_dado):,} CNPJs sem nenhum provento por nenhum nome")
    return len(df)


RENOMEAR = {
    "typeStock": "tipo_acao",
    "corporateAction": "tipo_provento",
    "lastDatePriorEx": "ultima_data_com",
    "valueCash": "valor_por_acao",
    "quotedPerShares": "cotado_por_acoes",
    "closingPricePriorExDate": "fechamento_b3_data_com",
    "dateApproval": "data_aprovacao",
    "ratio": "razao",
}


def carregar(nomes: list[str] | None = None) -> int:
    nomes = nomes or empresas_do_painel()
    todos, sem_dado = [], 0
    for i, nome in enumerate(nomes, 1):
        try:
            linhas = buscar_empresa(nome)
        except Exception as exc:
            print(f"  aviso: {nome!r} falhou ({type(exc).__name__})")
            continue
        if not linhas:
            sem_dado += 1
        todos.extend(linhas)
        if i % 100 == 0:
            print(f"  {i}/{len(nomes)} empresas, {lenateste:,} proventos ate aqui")

    df = pd.DataFrame(todos)
    if df.empty:
        return 0

    df = df.rename(columns={
        "typeStock": "tipo_acao",
        "corporateAction": "tipo_provento",
        "lastDatePriorEx": "ultima_data_com",
        "valueCash": "valor_por_acao",
        "quotedPerShares": "cotado_por_acoes",
        "closingPricePriorExDate": "fechamento_b3_data_com",
        "dateApproval": "data_aprovacao",
        "ratio": "razao",
    })
    manter = ["empresa", "tipo_acao", "tipo_provento", "ultima_data_com",
              "valor_por_acao", "cotado_por_acoes", "fechamento_b3_data_com",
              "data_aprovacao", "razao"]
    df = df[[c for c in manter if c in df.columns]].drop_duplicates()

    agora = now_utc()
    df["_source_file"] = "b3/GetListedCashDividends"
    df["_downloaded_at"] = agora
    df["_snapshot"] = agora.date().isoformat()

    with warehouse.connect() as con:
        warehouse.replace_partition(con, "b3_proventos", df,
                                    key="_snapshot", value=agora.date().isoformat())
    print(f"\n  {sem_dado} de {len(nomes)} empresas sem nenhum provento registrado")
    return len(df)


if __name__ == "__main__":
    nomes = empresas_do_painel()
    print(f"consultando proventos de {len(nomes)} empresas...")
    print(f"{carregar(nomes):,} proventos carregados")
