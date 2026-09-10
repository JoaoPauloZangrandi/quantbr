"""Canario das fontes de dados gratuitas.

Roda no CI todo dia util. Nao carrega nada no warehouse: so pergunta a cada fonte se
ela continua respondendo e no formato esperado. Falha ruidosamente quando algo muda.

Desde 02/09/2026 o escopo do projeto e so a base de acoes da B3, entao o canario vigia
so o que ainda usamos: o arquivo ANUAL (carga historica e reconciliacao) e o arquivo
DIARIO (atualizacao de todo dia). As checagens de NEFIN, BCB e CVM foram removidas
junto com os dados -- vigiar fonte que ninguem consome so gera alarme falso.
"""
from __future__ import annotations

import datetime as dt
import sys

import requests

UA = {"User-Agent": "quantbr/0.1 (canario de fontes)"}


def _falha(msg: str, erros: list[str]) -> None:
    print(f"  FALHA: {msg}")
    erros.append(msg)


def main() -> int:
    erros: list[str] = []
    hoje = dt.date.today()
    ano = hoje.year

    print("COTAHIST (B3)")
    url = f"https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{ano}.ZIP"
    try:
        r = requests.head(url, headers=UA, timeout=120, allow_redirects=True)
        tamanho = int(r.headers.get("Content-Length", 0))
        if r.status_code != 200:
            _falha(f"COTAHIST_A{ano} devolveu HTTP {r.status_code}", erros)
        elif tamanho < 1_000_000:
            _falha(f"COTAHIST_A{ano} com {tamanho} bytes, pequeno demais", erros)
        else:
            print(f"  ok: {tamanho/1e6:.1f} MB")
    except Exception as exc:
        _falha(f"COTAHIST inacessivel: {type(exc).__name__}: {exc}", erros)

    print("COTAHIST diario (usado na atualizacao de todo dia)")
    d = hoje - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    url = f"https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D{d:%d%m%Y}.ZIP"
    try:
        r = requests.head(url, headers=UA, timeout=120, allow_redirects=True)
        if r.status_code != 200:
            # 404 num feriado e normal; o alerta e para quando a URL muda de formato
            print(f"  aviso: {d:%Y-%m-%d} devolveu HTTP {r.status_code} (feriado?)")
        else:
            print(f"  ok: {d:%Y-%m-%d} disponivel")
    except Exception as exc:
        _falha(f"COTAHIST diario inacessivel: {type(exc).__name__}: {exc}", erros)

    print()
    if erros:
        print(f"{len(erros)} fonte(s) com problema.")
        return 1
    print("Todas as fontes de pe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
