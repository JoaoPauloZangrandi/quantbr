"""Corpus de papers: SSRN (Financial Economics Network) + OpenAlex.

POR QUE DUAS FONTES

Nenhuma sozinha resolve, e elas se encaixam bem:

  SSRN, api.ssrn.com
      Da o numero de DOWNLOADS, que e a metrica de relevancia da propria SSRN e nao
      existe em nenhum outro lugar. Cobre o binding 203 (Financial Economics Network),
      276 mil papers.
      LIMITE DURO: o parametro `index` trava em 9.999 -- acima disso a API responde
      HTTP 500. Entao da para pegar o top ~9.800 por download e os ~9.800 mais recentes,
      e nada alem disso por essa via.

  OpenAlex, api.openalex.org
      Indexa a SSRN inteira (1,67 milhao de trabalhos) com paginacao por cursor, sem
      teto. Da citacoes e topicos ja classificados. Filtrando por subfield Finance e
      2025 em diante sao 20.601 papers -- e isso cobre o buraco que o teto da SSRN deixa.
      NAO serve para abstract: so 2% dos registros da SSRN tem (a SSRN nao deposita
      abstract de preprint no Crossref).

CHAVE DE LIGACAO: o DOI do OpenAlex e `10.2139/ssrn.{id}`, e esse id e o mesmo
`abstract_id` da SSRN. As duas fontes casam sem ambiguidade.

O QUE NAO DA PARA FAZER, e ja foi testado: raspar as paginas de paper da SSRN. Tanto
requests quanto WebFetch levam 403 do Cloudflare. Por isso nao ha abstract em massa, e a
triagem se apoia em titulo mais topicos do OpenAlex.

ATUALIZACAO: `--novos` pega so os mais recentes e para assim que encontra o que ja temos.
E o modo da rotina agendada.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import time

import pandas as pd
import requests

import warehouse
from ingest.base import now_utc

# --- SSRN ---
SSRN_API = "https://api.ssrn.com/content/v1/bindings/{binding}/papers"
FEN = 203                 # Financial Economics Network
SSRN_TETO_INDICE = 9_800  # abaixo do teto real de 9.999, com folga
SSRN_POR_PAGINA = 200
SORT_RECENTES = 0
SORT_DOWNLOADS = 2

# --- OpenAlex ---
OA_API = "https://api.openalex.org/works"
OA_FONTE_SSRN = "S4210172589"
OA_SUBFIELD_FINANCAS = "subfields/2003"

CABECALHO = {"User-Agent": "quantbr/0.1 (research; mailto:joaozangrandii@gmail.com)"}
PAUSA = 0.25


# --------------------------------------------------------------------------- SSRN
def _pagina_ssrn(binding: int, indice: int, sort: int, count: int) -> list[dict]:
    r = requests.get(SSRN_API.format(binding=binding), headers=CABECALHO, timeout=90,
                     params={"index": indice, "count": count, "sort": sort})
    if r.status_code != 200:
        return []
    try:
        return r.json().get("papers") or []
    except ValueError:
        return []


def _linha_ssrn(p: dict) -> dict:
    return {
        "ssrn_id": str(p.get("id")),
        "titulo": (p.get("title") or "").strip(),
        "autores": "; ".join(
            f"{a.get('first_name','')} {a.get('last_name','')}".strip()
            for a in (p.get("authors") or [])),
        "n_autores": len(p.get("authors") or []),
        "data_aprovacao": p.get("approved_date"),
        "downloads": p.get("downloads"),
        "downloads_ano": p.get("downloads_this_year"),
        "downloads_mes": p.get("downloads_last_month"),
        "paginas": p.get("page_count"),
        "situacao": p.get("publication_status"),
        "url": p.get("url"),
    }


def coletar_ssrn(sort: int, limite: int, conhecidos: set[str] | None = None) -> list[dict]:
    """Percorre o binding do FEN. Para cedo se `conhecidos` for dado e a pagina inteira
    ja for conhecida -- e o que torna a atualizacao diaria barata."""
    linhas, indice = [], 0
    while indice < min(limite, SSRN_TETO_INDICE):
        pagina = _pagina_ssrn(FEN, indice, sort, SSRN_POR_PAGINA)
        if not pagina:
            break
        novos = [_linha_ssrn(p) for p in pagina]
        if conhecidos is not None and all(l["ssrn_id"] in conhecidos for l in novos):
            print(f"  pagina em {indice} toda conhecida, parando")
            break
        linhas.extend(novos)
        indice += SSRN_POR_PAGINA
        if indice % 2000 == 0:
            print(f"  {indice:,} papers percorridos")
        time.sleep(PAUSA)
    return linhas


# ----------------------------------------------------------------------- OpenAlex
def _texto_do_abstract(invertido: dict | None) -> str | None:
    """OpenAlex guarda o abstract como indice invertido (palavra -> posicoes)."""
    if not invertido:
        return None
    palavras = sorted(((p, i) for p, pos in invertido.items() for i in pos),
                      key=lambda x: x[1])
    return " ".join(p for p, _ in palavras)


def coletar_openalex(desde: str, gravar_a_cada: int = 2000) -> int:
    """Percorre o corpus e grava em LOTES.

    Gravar em lote nao e detalhe: a coleta inteira leva mais de dez minutos e a conexao
    ja caiu no meio uma vez (ConnectionResetError depois de 12 mil registros), perdendo
    tudo. Com lote e retentativa, uma queda custa no maximo um lote.
    """
    filtro = (f"primary_location.source.id:{OA_FONTE_SSRN},"
              f"from_publication_date:{desde},"
              f"topics.subfield.id:{OA_SUBFIELD_FINANCAS}")
    campos = ("id,doi,title,publication_date,cited_by_count,topics,"
              "abstract_inverted_index,authorships")

    lote, cursor, total = [], "*", 0
    while cursor:
        j = None
        for tentativa in range(5):
            try:
                r = requests.get(OA_API, headers=CABECALHO, timeout=120,
                                 params={"filter": filtro, "per-page": 200,
                                         "cursor": cursor, "select": campos})
                if r.status_code == 200:
                    j = r.json()
                    break
                time.sleep(2 * (tentativa + 1))
            except Exception as exc:
                print(f"    rede falhou ({type(exc).__name__}), tentativa {tentativa+1}/5")
                time.sleep(3 * (tentativa + 1))
        if j is None:
            print("    desistindo desta pagina; o que ja foi coletado esta gravado")
            break

        for w in j.get("results", []):
            doi = w.get("doi") or ""
            m = re.search(r"ssrn\.(\d+)", doi)
            topicos = [t.get("display_name") for t in (w.get("topics") or [])]
            lote.append({
                "ssrn_id": m.group(1) if m else None,
                "openalex_id": (w.get("id") or "").split("/")[-1],
                "titulo_oa": w.get("title"),
                "data_publicacao": w.get("publication_date"),
                "citacoes": w.get("cited_by_count"),
                "topicos": " | ".join(t for t in topicos if t),
                "topico_principal": topicos[0] if topicos else None,
                "abstract": _texto_do_abstract(w.get("abstract_inverted_index")),
            })

        cursor = (j.get("meta") or {}).get("next_cursor")
        if len(lote) >= gravar_a_cada or not cursor:
            total += _gravar("papers_openalex", lote, "ssrn_id")
            print(f"  {total:,} gravados")
            lote = []
        time.sleep(PAUSA)
    return total


# -------------------------------------------------------------------------- carga
def _gravar(tabela: str, linhas: list[dict], chave: str) -> int:
    if not linhas:
        return 0
    df = pd.DataFrame(linhas).dropna(subset=[chave]).drop_duplicates(subset=[chave])
    df["_downloaded_at"] = now_utc()

    with warehouse.connect() as con:
        if not warehouse.table_exists(con, tabela):
            con.register("_p", df)
            con.execute(f"CREATE TABLE {tabela} AS SELECT * FROM _p")
            con.unregister("_p")
        else:
            # Upsert: o mesmo paper reaparece com contagem de download atualizada, e a
            # contagem NOVA e que vale. Apagar antes de inserir mantem uma linha por id.
            con.register("_p", df)
            con.execute(f"DELETE FROM {tabela} WHERE {chave} IN (SELECT {chave} FROM _p)")
            con.execute(f"INSERT INTO {tabela} BY NAME SELECT * FROM _p")
            con.unregister("_p")
    return len(df)


def ids_conhecidos(tabela: str, chave: str) -> set[str]:
    with warehouse.connect(read_only=True) as con:
        if not warehouse.table_exists(con, tabela):
            return set()
        return {r[0] for r in con.execute(f"SELECT {chave} FROM {tabela}").fetchall()}


def main() -> int:
    p = argparse.ArgumentParser(description="Coleta o corpus de papers")
    p.add_argument("--relevantes", action="store_true",
                   help="top por downloads na SSRN (os mais relevantes de todos os tempos)")
    p.add_argument("--recentes", action="store_true", help="os mais novos da SSRN")
    p.add_argument("--openalex", action="store_true",
                   help="corpus completo de financas desde --desde, via OpenAlex")
    p.add_argument("--desde", default="2025-01-01")
    p.add_argument("--novos", action="store_true",
                   help="modo da rotina agendada: recentes + openalex do ultimo mes")
    args = p.parse_args()

    if not any([args.relevantes, args.recentes, args.openalex, args.novos]):
        args.relevantes = args.recentes = args.openalex = True

    if args.relevantes:
        print("SSRN, mais baixados de todos os tempos:")
        n = _gravar("papers_ssrn", coletar_ssrn(SORT_DOWNLOADS, SSRN_TETO_INDICE), "ssrn_id")
        print(f"  {n:,} papers\n")

    if args.recentes or args.novos:
        print("SSRN, mais recentes:")
        conhecidos = ids_conhecidos("papers_ssrn", "ssrn_id") if args.novos else None
        n = _gravar("papers_ssrn", coletar_ssrn(SORT_RECENTES, SSRN_TETO_INDICE, conhecidos),
                    "ssrn_id")
        print(f"  {n:,} papers\n")

    if args.openalex or args.novos:
        desde = args.desde
        if args.novos:
            desde = (dt.date.today() - dt.timedelta(days=45)).isoformat()
        print(f"OpenAlex, financas desde {desde}:")
        print(f"  {coletar_openalex(desde):,} trabalhos\n")

    with warehouse.connect(read_only=True) as con:
        for t in ("papers_ssrn", "papers_openalex"):
            if warehouse.table_exists(con, t):
                print(f"{t:<18} {con.execute(f'SELECT count(*) FROM {t}').fetchone()[0]:>8,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
