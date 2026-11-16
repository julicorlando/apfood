"""Ponte de impressão: só a origem do servidor configurado imprime."""

import json
import socket
import urllib.error
import urllib.request

import pytest

from apfood_pdv.config import Config
from apfood_pdv.impressao import ErroImpressao
from apfood_pdv.ponte import Ponte

ORIGEM = "https://apfood.exemplo.com.br"


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def ponte():
    cfg = Config(api_url=ORIGEM + "/", impressora_caixa="arquivo:/tmp/x", impressora_cozinha_padrao="10.0.0.9:9100")
    impressos = []

    def falso(destino, linhas, **kw):
        if destino == "quebrada:9100":
            raise ErroImpressao("impressora não respondeu")
        impressos.append((destino, linhas, kw))
        return destino

    p = Ponte(lambda: cfg, lambda: {"192.168.0.77:9100"}, porta=porta_livre(), imprimir_fn=falso)
    assert p.iniciar()
    p.impressos, p.cfg = impressos, cfg
    yield p
    p.parar()


def chamar(p, metodo, caminho, corpo=None, origem=ORIGEM):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{p.porta}{caminho}", data=dados, method=metodo)
    if origem:
        req.add_header("Origin", origem)
    if dados:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, dict(r.headers), json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), json.loads(e.read() or b"{}")


def test_status_e_impressao_no_caixa(ponte):
    st, cab, corpo = chamar(ponte, "GET", "/status")
    assert st == 200 and corpo["app"] == "ApFoodPDV" and corpo["caixa"]
    assert cab["Access-Control-Allow-Origin"] == ORIGEM
    st, _, corpo = chamar(ponte, "POST", "/imprimir", {"linhas": [{"texto": "Olá"}], "abrir_gaveta": True})
    assert st == 200 and corpo["ok"]
    destino, linhas, kw = ponte.impressos[0]
    assert destino == "arquivo:/tmp/x" and linhas == [{"texto": "Olá"}] and kw["abrir_gaveta"] and kw["largura"] == 48


def test_cozinha_usa_setor_conhecido_ou_padrao(ponte):
    chamar(ponte, "POST", "/imprimir", {"linhas": ["x"], "destino": "cozinha", "impressora": "192.168.0.77:9100"})
    chamar(ponte, "POST", "/imprimir", {"linhas": ["x"], "destino": "cozinha", "impressora": "8.8.8.8:9100"})
    assert [d for d, *_ in ponte.impressos] == ["192.168.0.77:9100", "10.0.0.9:9100"]


def test_outra_origem_e_recusada(ponte):
    assert chamar(ponte, "POST", "/imprimir", {"linhas": ["x"]}, origem="https://site-malicioso.com")[0] == 403
    assert chamar(ponte, "POST", "/imprimir", {"linhas": ["x"]}, origem=None)[0] == 403
    st, cab, _ = chamar(ponte, "OPTIONS", "/imprimir", origem="https://site-malicioso.com")
    assert st == 403 and "Access-Control-Allow-Origin" not in cab
    assert ponte.impressos == []


def test_preflight_libera_rede_privada(ponte):
    st, cab, _ = chamar(ponte, "OPTIONS", "/imprimir")
    assert st == 204 and cab["Access-Control-Allow-Private-Network"] == "true"


def test_erros(ponte):
    assert chamar(ponte, "POST", "/imprimir", {"linhas": []})[0] == 400
    ponte.cfg.impressora_caixa = "quebrada:9100"
    st, _, corpo = chamar(ponte, "POST", "/imprimir", {"linhas": ["x"]})
    assert st == 502 and "não respondeu" in corpo["erro"]
    ponte.cfg.impressora_caixa = ""
    assert chamar(ponte, "POST", "/imprimir", {"linhas": ["x"]})[0] == 502


def test_porta_zero_desliga():
    assert not Ponte(lambda: Config(), porta=0).iniciar()
