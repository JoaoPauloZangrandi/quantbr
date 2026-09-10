"""Utilitarios comuns de ingestao.

Principios (valem para TODO coletor deste diretorio):
  1. Idempotente: rodar duas vezes nao duplica nem corrompe nada.
  2. Cache em disco: o arquivo original baixado fica em data/raw/<fonte>/ e nunca e editado.
  3. Toda linha carregada no warehouse carrega _source_file e _downloaded_at (o `as_of`).
     Sem procedencia, o dado nao entra.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

import config


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=30))
def _get(url: str, timeout: int = 180) -> requests.Response:
    resp = requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return resp


def download(url: str, dest: Path, *, force: bool = False) -> Path:
    """Baixa `url` para `dest` se ainda nao existir. Retorna o caminho local.

    force=True refaz o download (usado para o arquivo do ano corrente, que muda todo dia).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    resp = _get(url)
    tmp.write_bytes(resp.content)
    tmp.replace(dest)  # atomico: nunca deixa arquivo meio-baixado com nome final
    return dest


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class RespostaNaoJson(RuntimeError):
    """A API respondeu 200 mas o corpo nao e JSON.

    Armadilha real, verificada ao vivo na API do BCB: em vez de devolver 5xx, o servidor
    as vezes entrega uma pagina HTML de erro com status 200. Sem esta checagem, a serie
    sumiria em silencio e ninguem notaria ate a analise dar errado.
    """


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=2, max=40))
def get_json(url: str, timeout: int = 120):
    resp = _get(url, timeout=timeout)
    corpo = resp.content.lstrip()
    if not corpo[:1] in (b"[", b"{"):
        raise RespostaNaoJson(f"corpo nao-JSON ({corpo[:60]!r}) em {url}")
    return resp.json()
