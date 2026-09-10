"""Eventos corporativos da B3 (proventos, desdobramentos, grupamentos, subscricoes).

Papel desta fonte no projeto: ela NAO e a fonte primaria de eventos. E o GABARITO.

Motivo, verificado ao vivo e nao suposto: a B3 apaga o historico de eventos quando a
empresa sai da bolsa. AESB3 (AES Brasil, comprada pela Auren em 2024) devolve listas
vazias; RRRP3 (3R Petroleum) devolve corpo vazio; e uma consulta por "TRPL" devolve os
dados de um FUNDO IMOBILIARIO chamado FII TRPL, que nao tem nada a ver com a CTEEP.
Ou seja: incompleta para quem morreu, e capaz de casar errado.

Entao o desenho e o inverso do obvio. Os eventos sao DETECTADOS do proprio COTAHIST
(que nunca apaga ninguem), e esta tabela serve para medir se o detector acerta, nas
empresas em que a B3 ainda tem a resposta. Calibrar onde existe verdade, aplicar onde
nao existe.

Efeito colateral util: como cada carga grava um snapshot datado e nada e sobrescrito,
com o tempo o nosso proprio historico vira o arquivo que a B3 nao mantem.
"""
from __future__ import annotations

import base64
import json
import time

import pandas as pd
import requests

import warehouse
from ingest.base import now_utc

BASE = ("https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/"
        "CompanyCall/GetListedSupplementCompany/")
HEADERS = {
    "User-Agent": "Mozilla/5.0 quantbr/0.1",
    "Accept": "application/json, text/plain, */*",
}
PAUSA = 0.35  # cortesia com o servidor da B3


def _param(d: dict) -> str:
    return base64.b64encode(json.dumps(d).encode()).decode()


def buscar_emissor(codigo: str) -> dict | None:
    """Devolve o bloco do emissor, ou None quando a B3 nao tem nada.

    Corpo vazio com status 200 e resposta legitima aqui: significa "nao conheco este
    emissor", tipicamente porque ele saiu da bolsa. Nao e erro, e ausencia -- e a
    diferenca entre as duas coisas precisa ficar registrada.
    """
    r = requests.get(BASE + _param({"issuingCompany": codigo, "language": "pt-br"}),
                     headers=HEADERS, timeout=60)
    if r.status_code != 200 or not r.content.strip():
        return None
    try:
        dados = r.json()
    except ValueError:
        return None
    return dados[0] if isinstance(dados, list) and dados else None


def _linhas(bloco: dict, codigo: str) -> tuple[list[dict], list[dict]]:
    """Extrai eventos de caixa e de quantidade de acoes do bloco do emissor."""
    caixa, quantidade = [], []

    for ev in bloco.get("cashDividends") or []:
        caixa.append({
            "emissor": codigo,
            "isin": ev.get("isinCode"),
            "tipo": (ev.get("label") or "").strip(),
            # lastDatePrior = ultimo dia COM direito. O ex e o pregao seguinte.
            # Guardamos o campo cru, sem converter, para nao embutir a convencao aqui.
            "ultima_data_com": ev.get("lastDatePrior"),
            "data_pagamento": ev.get("paymentDate"),
            "data_aprovacao": ev.get("approvedOn"),
            "valor_por_acao": ev.get("rate"),
            "referente_a": ev.get("relatedTo"),
        })

    for ev in bloco.get("stockDividends") or []:
        quantidade.append({
            "emissor": codigo,
            "isin": ev.get("isinCode"),
            "tipo": (ev.get("label") or "").strip(),   # DESDOBRAMENTO / GRUPAMENTO / BONIFICACAO
            "ultima_data_com": ev.get("lastDatePrior"),
            "data_aprovacao": ev.get("approvedOn"),
            # percentual de acoes NOVAS por acao existente. 100 = 1 nova para cada 1
            # antiga = fator 2. A conversao para fator fica no master/, nao aqui.
            "percentual": ev.get("factor"),
        })

    return caixa, quantidade


def carregar(emissores: list[str]) -> dict[str, int]:
    caixa, quantidade, cobertura = [], [], []
    for i, cod in enumerate(emissores, 1):
        try:
            bloco = buscar_emissor(cod)
        except Exception as exc:
            cobertura.append({"emissor": cod, "resposta": f"erro:{type(exc).__name__}",
                              "n_caixa": 0, "n_quantidade": 0})
            continue
        finally:
            time.sleep(PAUSA)

        if bloco is None:
            cobertura.append({"emissor": cod, "resposta": "sem_dados",
                              "n_caixa": 0, "n_quantidade": 0})
            continue

        c, q = _linhas(bloco, cod)
        caixa.extend(c)
        quantidade.extend(q)
        cobertura.append({
            "emissor": cod,
            "resposta": "ok",
            "n_caixa": len(c),
            "n_quantidade": len(q),
            # Guardado para auditoria: a B3 casa por prefixo e ja devolveu um FII quando
            # perguntamos por TRPL. Comparar este nome com o do master pega o falso par.
            "trading_name_b3": (bloco.get("tradingName") or "").strip(),
        })
        if i % 100 == 0:
            print(f"  {i}/{len(emissores)} emissores")

    agora = now_utc()
    snap = agora.date().isoformat()
    resultado = {}
    with warehouse.connect() as con:
        for nome, dados in (("b3_eventos_caixa", caixa),
                            ("b3_eventos_quantidade", quantidade),
                            ("b3_eventos_cobertura", cobertura)):
            df = pd.DataFrame(dados)
            if df.empty:
                resultado[nome] = 0
                continue
            df["_source_file"] = "b3/GetListedSupplementCompany"
            df["_downloaded_at"] = agora
            df["_snapshot"] = snap
            resultado[nome] = warehouse.replace_partition(
                con, nome, df, key="_snapshot", value=snap)
    return resultado


def emissores_do_master() -> list[str]:
    with warehouse.connect(read_only=True) as con:
        return [r[0] for r in con.execute("""
            SELECT DISTINCT emissor_isin
            FROM master_ticker
            WHERE classe_papel = 'acao' AND emissor_isin IS NOT NULL
            ORDER BY 1
        """).fetchall()]


if __name__ == "__main__":
    codigos = emissores_do_master()
    print(f"consultando {len(codigos)} emissores na B3...")
    for tabela, n in carregar(codigos).items():
        print(f"{tabela:<26} {n:>7,} linhas")
