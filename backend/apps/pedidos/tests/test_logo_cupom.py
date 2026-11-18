"""Logo da loja em todos os cupons: linha de logo no topo, ESC/POS (GS v 0) para o app Android e
logo pronta para o PDV do PC."""

import base64
import io

from apfood_core.enums import CanalVenda, TipoAtendimento
from django.core.files.base import ContentFile
from PIL import Image
from rest_framework.test import APIClient

from apps.fiscal import services as fiscal
from apps.pedidos import services as ps


def com_logo(loja, settings, tmp_path, w=600, h=300):
    settings.MEDIA_ROOT = tmp_path
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    img.paste((200, 30, 30, 255), (100, 80, 500, 220))
    b = io.BytesIO()
    img.save(b, "PNG")
    loja.logo.save("logo.png", ContentFile(b.getvalue()), save=True)
    return loja


def test_logo_no_topo_de_todos_os_cupons(loja, cardapio, operador, settings, tmp_path):
    p = ps.criar_pedido(loja, ps.PedidoIn(canal=CanalVenda.BALCAO, tipo_atendimento=TipoAtendimento.CONSUMO_LOCAL,
                                          itens=[ps.ItemIn(str(cardapio["lata"].id), 1)]), operador)
    assert not any(l.get("logo") for l in fiscal.linhas_para_json(fiscal.cupom_venda(p)))  # sem logo: nada muda

    com_logo(loja, settings, tmp_path)
    p.loja.refresh_from_db()
    venda = fiscal.linhas_para_json(fiscal.cupom_venda(p))
    assert venda[0]["logo"] is True and venda[0]["texto"].startswith("http") and venda[0]["texto"].endswith(".png")
    for via in fiscal.cupons_cozinha(p):
        assert via["linhas"][0].get("logo")
    api = APIClient()
    api.force_authenticate(operador)
    assert api.get(f"/api/pedidos/{p.id}/cupom/?loja={loja.id}").data["linhas"][0].get("logo")


def test_escpos_com_a_logo_e_logo_para_o_pc(loja, operador, settings, tmp_path):
    com_logo(loja, settings, tmp_path)
    api = APIClient()
    api.force_authenticate(operador)
    linhas = [{"texto": "http://x/logo.png", "logo": True}, {"texto": "LOJA"}, {"corte": True}]
    b = base64.b64decode(api.post(f"/api/impressao/escpos/?loja={loja.id}", {"linhas": linhas}, format="json").data["base64"])
    assert b"\x1dv0\x00" in b and b.index(b"\x1dv0\x00") < b.index(b"LOJA")  # a logo vem antes do nome

    r = api.get(f"/api/impressao/logo/?loja={loja.id}&largura=32").data
    assert r["tem_logo"] is True and r["largura_px"] <= 224 and r["altura_px"] <= 112 and r["largura_px"] % 8 == 0
    raster = base64.b64decode(r["escpos_base64"])
    assert raster.startswith(b"\x1dv0\x00") and len(raster) == 8 + r["largura_px"] // 8 * r["altura_px"]
    assert Image.open(io.BytesIO(base64.b64decode(r["png_base64"]))).mode == "1"
    r = api.get(f"/api/impressao/logo/?loja={loja.id}").data
    assert r["largura_px"] <= 320 and r["altura_px"] <= 160

    loja.logo.delete(save=True)
    assert api.get(f"/api/impressao/logo/?loja={loja.id}").data == {"tem_logo": False, "versao": ""}
