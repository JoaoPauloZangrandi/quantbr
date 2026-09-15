"""A curva de capacidade: quanto se paga para caber mais dinheiro.

A PENDENCIA QUE ISTO FECHA (nº3 de 14/09/2026)

O motor passou a reportar capacidade pelo GARGALO -- K <= N x min(capacidade_dia) x 5
pregoes -- e o momento 12-1 caiu de R$512 milhoes para R$6,9 milhoes. O numero ficou
registrado e parado: "a tese de capital pequeno agora tem numero". Numero parado nao e
decisao.

O QUE FALTAVA PERGUNTAR

R$6,9 milhoes nao e uma propriedade da estrategia, e uma consequencia de UMA escolha: o
piso de liquidez de R$500 mil/dia. Subir o piso joga fora o papel fino, e e o papel fino
que fixa o gargalo -- a carteira cabe no MENOS liquido que ela compra. Entao existe uma
curva, e a decisao de alocacao mora nela:

    piso de liquidez  ->  quantos papeis sobram  ->  capacidade  ->  retorno liquido

Se a capacidade sobe 20x e o retorno nao cai, o piso de R$500 mil era so um habito. Se o
retorno desaba junto, entao o edge do momento MORA no papel fino e a tese de capital
pequeno deixa de ser consolo: e a condicao de existencia da estrategia, e o tamanho
maximo do fundo esta medido.

COMO LER (protocolo de leitura de resultado)

Cada linha e uma tentativa a mais no ledger, e todas sao gravadas -- inclusive as ruins.
Sao 6 pisos x 3 estrategias = 18 trials nesta rodada, e o teste multiplo cobra por elas.
A leitura certa nao e "achei o piso otimo", e sim "a curva inteira tem a forma que a
hipotese previa?".

    python -m estrategias.capacidade
"""
from __future__ import annotations

import dataclasses as dc

import pandas as pd

from estrategias import motor, sinais

PISOS = (100_000.0, 500_000.0, 1_000_000.0, 5_000_000.0, 10_000_000.0, 50_000_000.0)


def curva(pisos=PISOS, *, registrar: bool = True) -> pd.DataFrame:
    linhas = []
    for piso in pisos:
        par = dc.replace(motor.Parametros(), liquidez_minima=piso)
        painel = motor._painel(par)
        elegiveis = motor._elegiveis(painel, par)
        por_mes = elegiveis.groupby("ano_mes").size()
        rodadas = {"BENCHMARK equal-weight": motor.benchmark(par),
                   "momento 12-1": motor.rodar(sinais.momento(), par,
                                               nome=f"momento 12-1 piso {piso:.0f}",
                                               registrar=registrar, painel=painel),
                   "armagedom defensivo": motor.rodar(
                       sinais.defensivo_armagedom(), par,
                       nome=f"armagedom piso {piso:.0f}", registrar=registrar,
                       painel=painel)}
        for nome, r in rodadas.items():
            if "erro" in r:
                continue
            linhas.append({
                "piso_liquidez": piso,
                "estrategia": nome,
                "elegiveis_por_mes": float(por_mes.median()),
                "retorno_liquido": r["liquido"].get("retorno_anual"),
                "sobre_cdi": r["liquido"].get("retorno_sobre_cdi"),
                "sharpe": r["liquido"].get("sharpe"),
                "custo_anual": r["custo_anual"],
                "capacidade": r["capacidade_mediana"],
                "capacidade_soma": r.get("capacidade_soma_mediana"),
            })
    return pd.DataFrame(linhas)


def formatar(g: pd.DataFrame) -> str:
    saida = []
    for nome, bloco in g.groupby("estrategia", sort=False):
        saida.append(f"\n{nome}")
        saida.append(f"  {'piso':>12s} {'elegiveis':>10s} {'liquido':>9s} {'s/CDI':>8s}"
                     f" {'sharpe':>7s} {'custo':>7s} {'capacidade':>13s}")
        for _, l in bloco.sort_values("piso_liquidez").iterrows():
            saida.append(
                f"  R$ {l['piso_liquidez'] / 1e3:>7,.0f} mil {l['elegiveis_por_mes']:>10.0f}"
                f" {l['retorno_liquido']:+9.1%} {l['sobre_cdi']:+8.1%}"
                f" {l['sharpe']:7.2f} {l['custo_anual']:7.1%}"
                f"   R$ {l['capacidade'] / 1e6:>6.1f} mi")
    return "\n".join(saida)


if __name__ == "__main__":
    g = curva()
    print(formatar(g))
    print()
    mom = g[g["estrategia"] == "momento 12-1"].sort_values("piso_liquidez")
    if len(mom) > 1:
        base = mom.iloc[1]  # o piso de R$500 mil, que e o default do motor
        for _, l in mom.iterrows():
            if l["piso_liquidez"] <= base["piso_liquidez"]:
                continue
            print(f"piso R$ {l['piso_liquidez'] / 1e6:.1f} mi: capacidade "
                  f"{l['capacidade'] / base['capacidade']:.1f}x a do default, "
                  f"retorno liquido {l['retorno_liquido'] - base['retorno_liquido']:+.1%} "
                  f"em relacao a ele")
