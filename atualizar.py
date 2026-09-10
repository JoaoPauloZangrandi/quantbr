"""Atualizacao diaria da base.

COMO FUNCIONA

A B3 publica dois arquivos com o mesmo conteudo e tamanhos muito diferentes:

    COTAHIST_A2026.ZIP      o ano inteiro, ~80 MB, reescrito todo dia
    COTAHIST_D02092026.ZIP  so aquele pregao, ~600 KB

Baixar o anual todo dia funcionaria, mas seria 130 vezes mais dado para a mesma
informacao. Entao a rotina diaria usa o arquivo do dia e so pega o que falta.

O procedimento e o mesmo toda vez:

  1. olha qual foi o ultimo pregao ja carregado
  2. percorre os dias uteis dali ate hoje
  3. baixa o arquivo de cada um; 404 significa que nao houve pregao (feriado), nao erro
  4. substitui as linhas daquelas datas e reconstroi o painel `acoes_diario`

Duas propriedades que importam para rodar sem supervisao:

  IDEMPOTENTE  -- rodar duas vezes no mesmo dia nao duplica nada. As linhas da data sao
                  apagadas antes de inserir, entao o resultado e sempre o mesmo.
  RECUPERA SOZINHA -- se a maquina ficar uma semana desligada, a proxima execucao pega
                  os pregoes todos de uma vez. Nao precisa rodar todo dia para funcionar.

O arquivo anual continua sendo a fonte para carga historica e para uma reconciliacao
periodica: a B3 as vezes CORRIGE pregao antigo, e so o anual reflete a correcao. Por isso
existe `--reconciliar`, que rebaixa o ano inteiro e compara com o que temos.

USO

    python atualizar.py                # rotina diaria
    python atualizar.py --reconciliar  # rebaixa o ano e confere (semanal/mensal)
    python atualizar.py --dias 30      # forca reprocessar os ultimos 30 dias
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import zipfile

import pandas as pd
import requests

import config
import emissor
import painel
import warehouse
from ingest import cotahist
from ingest.base import download, now_utc

URL_DIARIO = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D{ddmmaaaa}.ZIP"
RAW_DIR = config.RAW / "b3_cotahist_diario"
LOG = config.ROOT / "atualizacao.log"


def _registrar(msg: str) -> None:
    carimbo = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = f"[{carimbo}] {msg}"
    print(linha)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(linha + "\n")


def ultimo_pregao_carregado() -> dt.date:
    with warehouse.connect(read_only=True) as con:
        return con.execute("SELECT max(data)::DATE FROM b3_cotahist").fetchone()[0]


def _dias_uteis(inicio: dt.date, fim: dt.date):
    d = inicio
    while d <= fim:
        if d.weekday() < 5:   # feriado nao da para saber de antemao; o 404 resolve
            yield d
        d += dt.timedelta(days=1)


def baixar_pregao(dia: dt.date) -> pd.DataFrame | None:
    """Devolve o pregao do dia, ou None quando nao houve pregao.

    HTTP 404 aqui e resposta legitima: feriado, fim de semana ou arquivo ainda nao
    publicado. Tratar isso como erro faria a rotina falhar em todo feriado nacional.
    """
    destino = RAW_DIR / f"COTAHIST_D{dia:%d%m%Y}.ZIP"
    try:
        caminho = download(URL_DIARIO.format(ddmmaaaa=f"{dia:%d%m%Y}"), destino)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        raise
    except Exception:
        return None

    try:
        df = cotahist.parse(caminho)
    except zipfile.BadZipFile:
        # arquivo truncado no meio do download: apaga para a proxima tentativa refazer
        caminho.unlink(missing_ok=True)
        _registrar(f"  {dia:%Y-%m-%d}: zip invalido, descartado para retentar depois")
        return None
    return df if not df.empty else None


def aplicar(quadros: list[pd.DataFrame]) -> int:
    if not quadros:
        return 0
    df = pd.concat(quadros, ignore_index=True)
    df["ano"] = df["data"].dt.year
    df["_source_file"] = "COTAHIST_D"
    df["_downloaded_at"] = now_utc()
    datas = sorted(df["data"].dt.date.unique())

    with warehouse.connect() as con:
        con.register("_novo", df)
        # Apaga por DATA, nao por ano: o `replace_partition` usado na carga historica
        # limparia 2026 inteiro para inserir um unico pregao.
        con.execute("DELETE FROM b3_cotahist WHERE data::DATE IN "
                    f"({', '.join(repr(str(d)) for d in datas)})")
        con.execute("INSERT INTO b3_cotahist BY NAME SELECT * FROM _novo")
        con.unregister("_novo")
    return len(df)


def rotina_diaria(dias_forcados: int | None = None) -> int:
    hoje = dt.date.today()
    if dias_forcados:
        inicio = hoje - dt.timedelta(days=dias_forcados)
    else:
        ultimo = ultimo_pregao_carregado()
        inicio = ultimo + dt.timedelta(days=1)
        _registrar(f"ultimo pregao na base: {ultimo}")

    if inicio > hoje:
        _registrar("base ja esta em dia, nada a fazer")
        return 0

    quadros, sem_pregao = [], []
    for dia in _dias_uteis(inicio, hoje):
        df = baixar_pregao(dia)
        if df is None:
            sem_pregao.append(dia)
            continue
        quadros.append(df)
        _registrar(f"  {dia:%Y-%m-%d}: {len(df):,} linhas")

    if sem_pregao:
        _registrar(f"  sem pregao (feriado ou nao publicado): "
                   f"{', '.join(f'{d:%Y-%m-%d}' for d in sem_pregao)}")

    n = aplicar(quadros)
    if n:
        linhas_painel = painel.construir()
        # O painel por emissor deriva do diario: se um nao acompanha o outro, um teste
        # rodado amanha usa universo de ontem sem ninguem perceber.
        emissor.construir()
        _registrar(f"{n:,} linhas novas; painel reconstruido com {linhas_painel:,} linhas")
    else:
        _registrar("nenhum pregao novo")
    return n


def reconciliar() -> None:
    """Rebaixa o arquivo anual e compara com o que temos.

    Existe porque a B3 as vezes corrige pregao ja publicado, e a correcao so aparece no
    arquivo anual. Sem esta checagem, um erro corrigido na fonte ficaria para sempre na
    nossa base sem ninguem saber.
    """
    ano = dt.date.today().year
    _registrar(f"reconciliando {ano} contra o arquivo anual...")
    with warehouse.connect(read_only=True) as con:
        antes = con.execute(
            "SELECT count(*), round(sum(fechamento), 2) FROM b3_cotahist WHERE ano = ?",
            [ano]).fetchone()

    n = cotahist.carregar(ano, force_download=True)

    with warehouse.connect(read_only=True) as con:
        depois = con.execute(
            "SELECT count(*), round(sum(fechamento), 2) FROM b3_cotahist WHERE ano = ?",
            [ano]).fetchone()

    if antes == depois:
        _registrar(f"  sem divergencia ({n:,} linhas)")
    else:
        _registrar(f"  DIVERGENCIA: antes linhas={antes[0]:,} soma={antes[1]:,} | "
                   f"depois linhas={depois[0]:,} soma={depois[1]:,}")
        _registrar("  o arquivo anual venceu (a B3 e a fonte). Vale investigar o que mudou.")
    painel.construir()
    emissor.construir()


DIAS_ENTRE_ATUALIZACOES_DE_PAPERS = 7
# O balanco do ano corrente muda conforme as empresas entregam; os anos fechados nao mudam
# mais. Baixar tudo todo dia seria 17 arquivos para reler o mesmo dado.
DIAS_ENTRE_ATUALIZACOES_CONTABEIS = 30


def _dias_desde_ultimo_paper() -> float | None:
    with warehouse.connect(read_only=True) as con:
        if not warehouse.table_exists(con, "papers_ssrn"):
            return None
        ultimo = con.execute("SELECT max(_downloaded_at) FROM papers_ssrn").fetchone()[0]
    if ultimo is None:
        return None
    return (dt.datetime.now(dt.timezone.utc) - ultimo).total_seconds() / 86400


def rotina_papers(forcar: bool = False) -> None:
    """Atualiza o corpus de papers, mas so uma vez por semana.

    Vive dentro da rotina diaria de proposito, em vez de virar uma segunda tarefa
    agendada: uma tarefa a menos para manter, e sem precisar de outra elevacao de
    administrador. A propria tabela diz quando foi a ultima vez, entao a frequencia se
    controla sozinha mesmo que a maquina fique dias desligada.
    """
    dias = _dias_desde_ultimo_paper()
    if not forcar and dias is not None and dias < DIAS_ENTRE_ATUALIZACOES_DE_PAPERS:
        _registrar(f"papers atualizados ha {dias:.1f} dias, pulando "
                   f"(intervalo: {DIAS_ENTRE_ATUALIZACOES_DE_PAPERS} dias)")
        return

    from ingest import papers

    _registrar("atualizando corpus de papers...")
    conhecidos = papers.ids_conhecidos("papers_ssrn", "ssrn_id")
    novos = papers.coletar_ssrn(papers.SORT_RECENTES, papers.SSRN_TETO_INDICE, conhecidos)
    n = papers._gravar("papers_ssrn", novos, "ssrn_id")
    _registrar(f"  SSRN: {n:,} papers novos ou com download atualizado")

    desde = (dt.date.today() - dt.timedelta(days=45)).isoformat()
    m = papers.coletar_openalex(desde)
    _registrar(f"  OpenAlex: {m:,} trabalhos desde {desde}")


def _dias_desde_ultimo_balanco() -> float:
    with warehouse.connect(read_only=True) as con:
        if not warehouse.table_exists(con, "cvm_dfp"):
            return 1e9
        ultimo = con.execute("SELECT max(_downloaded_at) FROM cvm_dfp").fetchone()[0]
    if ultimo is None:
        return 1e9
    return (now_utc() - ultimo).total_seconds() / 86400


def rotina_contabil(forcar: bool = False) -> int:
    """Rebaixa so o ano corrente do DFP -- o unico que ainda muda.

    Fica num try proprio no `main`, como a de papers: falha na CVM nao pode derrubar a
    atualizacao de preco, que e a parte critica.
    """
    dias = _dias_desde_ultimo_balanco()
    if not forcar and dias < DIAS_ENTRE_ATUALIZACOES_CONTABEIS:
        _registrar(f"balanco atualizado ha {dias:.1f} dias, pulando "
            f"(intervalo: {DIAS_ENTRE_ATUALIZACOES_CONTABEIS} dias)")
        return 0
    from ingest import dfp
    ano = dt.date.today().year
    n = dfp.carregar_ano(ano, force=True)
    _registrar(f"  DFP {ano}: {n:,} linhas")
    if n:
        emissor.construir()
    return n


def main() -> int:
    p = argparse.ArgumentParser(description="Atualiza a base de acoes da B3")
    p.add_argument("--papers", action="store_true",
                   help="forca a atualizacao do corpus de papers agora")
    p.add_argument("--sem-papers", action="store_true",
                   help="so precos, sem tocar no corpus de papers")
    p.add_argument("--reconciliar", action="store_true",
                   help="rebaixa o ano inteiro e compara (semanal/mensal)")
    p.add_argument("--dias", type=int, default=None,
                   help="forca reprocessar os ultimos N dias corridos")
    args = p.parse_args()

    _registrar("-" * 60)
    try:
        if args.papers:
            rotina_papers(forcar=True)
            return 0
        if args.reconciliar:
            reconciliar()
        else:
            rotina_diaria(args.dias)
    except Exception as exc:
        _registrar(f"FALHOU: {type(exc).__name__}: {exc}")
        return 1

    # Papers vem depois dos precos e num try proprio: falha de rede na SSRN ou no
    # OpenAlex nao pode derrubar a atualizacao de preco, que e a parte critica.
    if not args.sem_papers and not args.reconciliar:
        try:
            rotina_papers()
        except Exception as exc:
            _registrar(f"papers falharam (precos ok): {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
