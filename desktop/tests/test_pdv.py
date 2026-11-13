import json

import pytest

from apfood_core.cupom import comprovante_venda
from apfood_pdv import impressao
from apfood_pdv.api import ApiClient, ErroApi, SemConexao
from apfood_pdv.config import Config
from apfood_pdv.local_db import BancoLocal
from apfood_pdv.operacoes import PDV
from apfood_pdv.sync import Sincronizador


class Servidor:
    """Servidor falso: rotas (método, caminho) → função(corpo) → (status, json)."""

    def __init__(self):
        self.online = True
        self.rotas = {}
        self.chamadas = []

    def __call__(self, metodo, url, headers, corpo, timeout):
        if not self.online:
            raise SemConexao("offline")
        caminho = url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
        dados = json.loads(corpo) if corpo else None
        self.chamadas.append((metodo, "/" + caminho, dados, headers))
        fn = self.rotas.get((metodo, "/" + caminho))
        if fn is None:
            return 404, b'{"detail": "nao encontrado"}'
        status, resp = fn(dados) if callable(fn) else fn
        return status, json.dumps(resp).encode()


@pytest.fixture
def srv():
    s = Servidor()
    s.rotas[("POST", "/api/auth/token/")] = (200, {"access": "a1", "refresh": "r1"})
    s.rotas[("GET", "/api/eu/")] = (200, {"username": "caixa", "lojas": [{"id": "L1"}]})
    return s


@pytest.fixture
def pdv(srv):
    api = ApiClient("http://srv", transporte=srv)
    api.login("caixa", "x")
    api.loja_id = "L1"
    banco = BancoLocal()
    banco.aplicar_pull("produtos", [{"id": "p1", "nome": "Lata", "tipo": "VENDA", "preco_centavos": 700,
                                     "categoria": "c1", "atualizado_em": "2026-01-01T00:00:00Z"}])
    return PDV(api, banco, terminal="C1")


def test_login_e_headers(srv, pdv):
    metodo, caminho, _, headers = srv.chamadas[-1]
    assert caminho == "/api/eu/" and headers["Authorization"] == "Bearer a1"
    pdv.api.get("/api/eu/")
    assert srv.chamadas[-1][3]["X-Loja"] == "L1"


def test_renova_token_no_401(srv, pdv):
    estado = {"n": 0}

    def eu(_):
        estado["n"] += 1
        return (401, {"detail": "expirado"}) if estado["n"] == 1 else (200, {"ok": True})

    srv.rotas[("GET", "/api/eu/")] = eu
    srv.rotas[("POST", "/api/auth/token/refresh/")] = (200, {"access": "a2", "refresh": "r2"})
    assert pdv.api.get("/api/eu/") == {"ok": True}
    assert pdv.api.access == "a2"


def test_erro_de_negocio_vira_mensagem(srv, pdv):
    srv.rotas[("POST", "/api/turnos/abrir/")] = (400, {"detail": "você já tem um caixa aberto"})
    with pytest.raises(ErroApi, match="já tem um caixa"):
        pdv.abrir_caixa(1000)


def test_online_envia_direto(srv, pdv):
    srv.rotas[("POST", "/api/pedidos/")] = lambda d: (201, {"id": d["id"], "numero": 7, "total_centavos": 1400})
    r = pdv.criar_pedido({"canal": "BALCAO", "tipo_atendimento": "RETIRADA",
                          "itens": [{"produto_id": "p1", "quantidade": 2}]})
    assert r["numero"] == 7 and not r["offline"] and pdv.banco.total_pendentes() == 0


def test_offline_enfileira_em_ordem_e_sincroniza(srv, pdv):
    srv.online = False
    p = pdv.criar_pedido({"canal": "BALCAO", "tipo_atendimento": "RETIRADA",
                          "itens": [{"produto_id": "p1", "quantidade": 2}]})
    assert p["offline"] and p["total_centavos"] == 1400 and p["codigo_local"] == "C1-0001"
    pg = pdv.pagar(p["id"], "DINHEIRO", 1400, 2000)
    assert pg["offline"] and pg["troco_centavos"] == 600

    srv.online = True
    # com fila pendente, mesmo online vai para a fila (não fura a ordem)
    pdv.mudar_status(p["id"], "PRONTO")
    assert pdv.banco.total_pendentes() == 3

    recebidas = []

    def push(corpo):
        recebidas.extend(o["operacao"] for o in corpo["operacoes"])
        res = [{"id": o["id"], "ok": o["operacao"] != "pedido.status", "erro": "transição inválida",
                "resultado": {}} for o in corpo["operacoes"]]
        return 200, {"resultados": res}

    srv.rotas[("POST", "/api/sync/push/")] = push
    srv.rotas[("GET", "/api/sync/pull/")] = (200, {"entidades": {"mesas": {"registros": [
        {"id": "m1", "nome": "Mesa 1", "atualizado_em": "2026-11-12T10:00:00Z"}], "cursor": "x"}}})
    rejeitadas = []
    s = Sincronizador(pdv.banco, pdv.api)
    s.ao_rejeitar = lambda i, op, erro: rejeitadas.append((op, erro))
    assert s.ciclo() == {"enviados": 2, "recebidos": 1}
    assert recebidas == ["pedido.criar", "pedido.pagamento", "pedido.status"]
    assert rejeitadas == [("pedido.status", "transição inválida")]
    assert pdv.banco.total_pendentes() == 0 and len(pdv.banco.rejeitadas()) == 1
    assert pdv.banco.listar("mesas")[0]["nome"] == "Mesa 1"


def test_preco_local_com_sabores_e_adicionais():
    b = BancoLocal()
    b.aplicar_pull("categorias", [{"id": "c", "nome": "Pizzas", "regra_preco_sabores": "MEDIA", "atualizado_em": "1"}])
    b.aplicar_pull("produtos", [{"id": "a", "nome": "A", "categoria": "c", "preco_centavos": 4000, "atualizado_em": "1"},
                                {"id": "b", "nome": "B", "categoria": "c", "preco_centavos": 5000, "atualizado_em": "1"}])
    b.aplicar_pull("variacoes", [{"id": "ag", "produto": "a", "nome": "G", "preco_centavos": 6000, "atualizado_em": "1"},
                                 {"id": "bg", "produto": "b", "nome": "G", "preco_centavos": 7000, "atualizado_em": "1"}])
    b.aplicar_pull("adicionais", [{"id": "x", "grupo": "g", "nome": "Borda", "preco_centavos": 800, "atualizado_em": "1"}])
    pdv = PDV(ApiClient("http://x", transporte=Servidor()), b)
    total = pdv.precificar_item({"produto_id": "a", "variacao_id": "ag", "sabores": ["a", "b"], "quantidade": 2,
                                 "adicionais": [{"adicional_id": "x", "quantidade": 1}]})
    assert total == (6500 + 800) * 2


def test_escpos_e_arquivo(tmp_path):
    linhas = comprovante_venda({"numero": 1, "itens": [{"quantidade": 1, "nome": "Pão de queijo", "total_centavos": 500}],
                                "subtotal_centavos": 500, "total_centavos": 500}, {"nome": "Café"})
    dados = impressao.para_escpos(linhas, abrir_gaveta=True)
    assert dados.startswith(b"\x1b@\x1bt\x03") and impressao.GAVETA in dados
    assert impressao.AVANCA_E_CORTA in dados and "Pão de queijo".encode("cp860") in dados
    arq = impressao.imprimir(f"arquivo:{tmp_path}", linhas)
    assert "NAO E DOCUMENTO FISCAL" in open(arq, encoding="utf-8").read()
    with pytest.raises(impressao.ErroImpressao):
        impressao.imprimir("", linhas)


def test_impressora_de_rede(tmp_path):
    import socket
    import threading

    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    recebido = []

    def aceitar():
        c, _ = srv.accept()
        recebido.append(c.recv(65536))
        c.close()

    t = threading.Thread(target=aceitar)
    t.start()
    impressao.imprimir(f"127.0.0.1:{srv.getsockname()[1]}", [{"texto": "TESTE", "corte": False}])
    t.join(5)
    srv.close()
    assert b"TESTE" in recebido[0]


def test_config_salva_e_carrega(tmp_path):
    c = Config(api_url="https://apfood.app", impressora_caixa="10.0.0.5:9100", largura_bobina=32)
    c.salvar(tmp_path / "c.json")
    c2 = Config.carregar(tmp_path / "c.json")
    assert c2.impressora_caixa == "10.0.0.5:9100" and c2.largura_bobina == 32 and c2.ws_url == "wss://apfood.app"


# --- atualização automática -------------------------------------------------
def test_comparacao_de_versoes():
    from apfood_pdv.atualizador import mais_nova, versao_tupla

    assert versao_tupla("v1.10.0") == (1, 10) and versao_tupla("1.2.0-beta") == (1, 2)
    assert mais_nova("1.10.0", "1.9.9") and not mais_nova("1.0", "1.0.0") and not mais_nova("", "0.1")


def test_verificar_baixar_e_conferir_sha(tmp_path):
    import hashlib

    from apfood_pdv.atualizador import ErroAtualizacao, baixar, script_troca, verificar

    class Api:
        def __init__(self, info):
            self.info = info

        def get(self, caminho):
            assert caminho == "/api/pdv/versao/"
            return self.info

    exe = b"MZ novo executavel"
    sha = hashlib.sha256(exe).hexdigest()
    assert verificar(Api({"versao": "0.1.0", "url": "x", "sha256": sha}), "0.1.0") is None
    at = verificar(Api({"versao": "0.2.0", "url": "https://s/ApFoodPDV.exe", "sha256": sha.upper(),
                        "obrigatoria_ate": "0.2.0"}), "0.1.0")
    assert at and at.obrigatoria and at.sha256 == sha
    destino = baixar(at, destino=tmp_path / "novo.exe", baixador=lambda url: exe)
    assert destino.read_bytes() == exe
    with pytest.raises(ErroAtualizacao, match="não confere"):
        baixar(at, destino=tmp_path / "x.exe", baixador=lambda url: b"adulterado")
    cmd = script_troca(tmp_path / "novo.exe", tmp_path / "ApFoodPDV.exe", 1234)
    assert 'PID eq 1234' in cmd and ".old" in cmd and "start" in cmd


def test_normalizar_servidor():
    from apfood_pdv.config import normalizar_servidor

    assert normalizar_servidor("apfood.axionwebdigital.com.br") == "https://apfood.axionwebdigital.com.br"
    assert normalizar_servidor(" https://apfood.axionwebdigital.com.br/painel/ ") == "https://apfood.axionwebdigital.com.br"
    assert normalizar_servidor("localhost:8000") == "http://localhost:8000"
    assert normalizar_servidor("http://192.168.0.10:8000/") == "http://192.168.0.10:8000"
