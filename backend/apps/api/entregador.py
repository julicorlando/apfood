"""API do app ApFood Entregador: /api/entregador/...

Login com telefone + PIN (4 a 6 dígitos, definido pela loja no cadastro; o
entregador troca no app). O mesmo telefone pode estar cadastrado em mais de uma
loja: a sessão vale para todas em que o PIN confere.

Sessão = token assinado (Authorization: Entregador <token>), válido por 60 dias
e invalidado quando o PIN muda."""

from __future__ import annotations

import calendar
import hashlib
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from apfood_core.entrega import distancia_km
from apfood_core.enums import StatusPedido as S
from django.core import signing
from django.core.cache import cache
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.clientes.models import Entregador
from apps.core.excecoes import ErroNegocio
from apps.pedidos import acertos, chamadas, cobranca_entrega
from apps.pedidos.models import Pedido

SAL = "apfood.entregador"
VALIDADE_S = 60 * 24 * 3600
PIN = re.compile(r"^\d{4,6}$")
EM_ANDAMENTO = (S.RECEBIDO, S.EM_PREPARO, S.PRONTO, S.SAIU_PARA_ENTREGA)


def digitos(telefone: str) -> str:
    d = re.sub(r"\D", "", telefone or "")
    return d[2:] if len(d) > 11 and d.startswith("55") else d


def _assinatura(es) -> str:
    return hashlib.sha256("|".join(sorted(e.pin_hash for e in es)).encode()).hexdigest()[:16]


def token_para(es) -> str:
    return signing.dumps({"ids": sorted(str(e.id) for e in es), "h": _assinatura(es)}, salt=SAL)


def _validos():
    return (Entregador.objects.ativos().filter(ativo=True, loja__ativa=True, loja__empresa__ativa=True)
            .exclude(pin_hash="").select_related("loja", "loja__empresa"))


def entregadores_da(request) -> list[Entregador]:
    cab = request.headers.get("Authorization", "")
    if not cab.startswith("Entregador "):
        raise AuthenticationFailed("entre com telefone e PIN")
    try:
        dados = signing.loads(cab.split(" ", 1)[1], salt=SAL, max_age=VALIDADE_S)
    except signing.BadSignature as exc:
        raise AuthenticationFailed("sessão expirada: entre de novo") from exc
    es = [e for e in _validos().filter(pk__in=dados.get("ids") or []) if e.loja.empresa.liberada]
    if not es or _assinatura(es) != dados.get("h"):
        raise AuthenticationFailed("sessão expirada: entre de novo")
    return es


class Base(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get_authenticate_header(self, request):
        return 'Entregador realm="ApFood"'  # sessão inválida responde 401 (o app volta ao login)


# ----------------------------------------------------------------------------- login e conta
class EntrarView(Base):
    def post(self, request):
        tel = digitos(request.data.get("telefone", ""))
        pin = str(request.data.get("pin", "")).strip()
        if len(tel) < 10 or not PIN.match(pin):
            raise ValidationError({"detail": "Informe o telefone com DDD e o PIN (4 a 6 números)."})
        chave = f"entregador-login-{tel}"
        if cache.get(chave, 0) >= 8:
            raise ValidationError({"detail": "Muitas tentativas. Espere 15 minutos ou peça à loja para redefinir o PIN."})
        es = [e for e in _validos() if digitos(e.telefone) == tel and e.loja.empresa.liberada and e.confere_pin(pin)]
        if not es:
            cache.set(chave, cache.get(chave, 0) + 1, 15 * 60)
            raise ValidationError({"detail": "Telefone ou PIN incorretos."})
        cache.delete(chave)
        return Response({"token": token_para(es), "nome": es[0].nome, "trocar_pin": not all(e.pin_trocado for e in es),
                         "lojas": [e.loja.nome for e in es]})


class PinView(Base):
    def post(self, request):
        es = entregadores_da(request)
        atual, novo = str(request.data.get("atual", "")), str(request.data.get("novo", ""))
        if not es[0].confere_pin(atual):
            raise ValidationError({"detail": "PIN atual incorreto."})
        if not PIN.match(novo):
            raise ValidationError({"detail": "O novo PIN deve ter de 4 a 6 números."})
        if len(set(novo)) == 1 or novo in "0123456789" or novo in "9876543210":
            raise ValidationError({"detail": "Escolha um PIN menos óbvio (sem números repetidos ou em sequência)."})
        for e in es:
            e.definir_pin(novo, trocado=True)
            e.save(update_fields=["pin_hash", "pin_trocado", "atualizado_em"])
        return Response({"token": token_para(es)})


class PushView(Base):
    def post(self, request):
        from apps.integracoes import push

        es = entregadores_da(request)
        push.registrar(str(request.data.get("token", "")), "entregador", entregador=es[0])
        return Response({"ok": True, "ativo": push.ativo()})


class OnlineView(Base):
    """Disponível/indisponível + posição (o app manda a cada ~15 s enquanto disponível)."""

    def post(self, request):
        es = entregadores_da(request)
        campos = {"online": bool(request.data.get("online")), "online_em": timezone.now()}
        try:
            lat, lng = Decimal(str(request.data["latitude"])), Decimal(str(request.data["longitude"]))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                campos.update(latitude=round(lat, 7), longitude=round(lng, 7), localizacao_em=timezone.now())
        except (KeyError, InvalidOperation, TypeError, ValueError):
            pass
        Entregador.objects.filter(pk__in=[e.pk for e in es]).update(**campos)
        if not campos["online"]:  # ficou indisponível: passa a oferta adiante
            ch = chamadas.oferta_para(es)
            if ch is not None:
                chamadas.recusar(ch.id, next(e for e in es if e.id == ch.entregador_atual_id))
        return Response({"online": campos["online"]})


class PlantaoView(Base):
    """Serviço nativo do APK (celular bloqueado ou app fechado), a cada ~5 s: mantém o entregador
    disponível, atualiza a posição e devolve a chamada que está com ele. Não liga quem está indisponível."""

    def post(self, request):
        es = entregadores_da(request)
        ligados = [e for e in es if e.online]
        if ligados:
            campos = {"online_em": timezone.now()}
            try:
                lat, lng = Decimal(str(request.data["latitude"])), Decimal(str(request.data["longitude"]))
                if -90 <= lat <= 90 and -180 <= lng <= 180:
                    campos.update(latitude=round(lat, 7), longitude=round(lng, 7), localizacao_em=timezone.now())
            except (KeyError, InvalidOperation, TypeError, ValueError):
                pass
            Entregador.objects.filter(pk__in=[e.pk for e in ligados]).update(**campos)
        ch = chamadas.oferta_para(es) if ligados else None
        return Response({"online": bool(ligados), "oferta": _oferta(ch, es) if ch else None})


# ----------------------------------------------------------------------------- estado (polling do app)
def _endereco(p: Pedido) -> str:
    return ", ".join(x for x in [f"{p.entrega_logradouro} {p.entrega_numero}".strip(), p.entrega_complemento,
                                  p.entrega_bairro, p.entrega_cidade] if x)


def _endereco_loja(l) -> str:
    return ", ".join(x for x in [f"{getattr(l, 'logradouro', '')} {getattr(l, 'numero', '')}".strip(),
                                  getattr(l, "bairro", ""), getattr(l, "cidade", "")] if x)


def _mapa(lat, lng, endereco: str) -> str:
    if lat is not None and lng is not None:
        return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}"
    return f"https://www.google.com/maps/dir/?api=1&destination={quote(endereco)}"


def _km(a_lat, a_lng, b_lat, b_lng):
    if None in (a_lat, a_lng, b_lat, b_lng):
        return None
    return round(distancia_km(float(a_lat), float(a_lng), float(b_lat), float(b_lng)), 1)


def _oferta(ch, es) -> dict:
    p, l = ch.pedido, ch.loja
    e = next(x for x in es if x.id == ch.entregador_atual_id)
    todos = [p, *chamadas.juntos_validos(ch)]
    bairros = list(dict.fromkeys(x.entrega_bairro for x in todos if x.entrega_bairro))
    return {
        "chamada": str(ch.id), "numero": p.numero, "loja": l.nome, "loja_endereco": _endereco_loja(l),
        "bairro": " + ".join(bairros) if bairros else p.entrega_bairro, "cidade": p.entrega_cidade,
        "entregas": len(todos), "numeros": [x.numero for x in todos],
        "ate_loja_km": _km(e.latitude, e.longitude, l.latitude, l.longitude),
        "entrega_km": _km(l.latitude, l.longitude, p.entrega_latitude, p.entrega_longitude),
        "ganho_centavos": sum(e.ganho(x) for x in todos) if e.remuneracao != "NENHUM" else None,
        "segundos": max(0, int((ch.oferta_ate - timezone.now()).total_seconds())) if ch.oferta_ate else 0,
        "total_segundos": chamadas.OFERTA_S,
    }


def _cobranca(p: Pedido, e: Entregador) -> dict | None:
    """O que o entregador registrou na porta (para o app mostrar e não cobrar duas vezes)."""
    feitos = [pg for pg in p.pagamentos.all() if pg.entregador_id == e.id and pg.cobrado_em is not None
              and pg.status in ("PENDENTE", "CONFIRMADO")]
    pix = next((pg for pg in p.pagamentos.all() if pg.entregador_id == e.id and pg.forma == "PIX"
                and pg.status == "PENDENTE" and pg.pago_online and pg.dados_externos.get("qr_code")), None)
    return {
        "feitos": [{"forma": pg.forma, "forma_rotulo": pg.get_forma_display(), "valor_centavos": pg.valor_centavos,
                    "recebido_centavos": pg.valor_recebido_centavos, "troco_centavos": pg.troco_centavos,
                    "com_voce": pg.status == "PENDENTE"} for pg in feitos],
        "pix": {"qr_code": pix.dados_externos.get("qr_code", ""), "qr_code_base64": pix.dados_externos.get("qr_code_base64", ""),
                "valor_centavos": pix.valor_centavos} if pix else None,
    }


def _entrega(p: Pedido, e: Entregador) -> dict:
    pago = sum(pg.valor_centavos for pg in p.pagamentos.all()
               if pg.status == "CONFIRMADO" or (pg.status == "PENDENTE" and pg.cobrado_em is not None))
    pendente = next((pg for pg in p.pagamentos.all() if pg.status == "PENDENTE" and pg.cobrado_em is None), None)
    end, l = _endereco(p), p.loja
    saiu = p.status == S.SAIU_PARA_ENTREGA
    return {
        "id": str(p.id), "numero": p.numero, "status": p.status, "loja": l.nome,
        "loja_endereco": _endereco_loja(l), "loja_telefone": l.whatsapp or l.telefone,
        "loja_mapa": _mapa(l.latitude, l.longitude, _endereco_loja(l)),
        "pronto": p.status in (S.PRONTO, S.SAIU_PARA_ENTREGA), "saiu": saiu,
        "cliente": p.nome_cliente, "telefone": p.telefone_cliente if saiu else "",
        "endereco": end, "referencia": p.entrega_referencia,
        "mapa": _mapa(p.entrega_latitude, p.entrega_longitude, end),
        "cobrar_centavos": max(0, p.total_centavos - pago),
        "forma": pendente.get_forma_display() if pendente else "",
        "forma_prevista": pendente.forma if pendente else "",
        "pix_automatico": cobranca_entrega.tem_gateway(l),
        "cobranca": _cobranca(p, e),
        "troco_para_centavos": p.troco_para_centavos,
        "ganho_centavos": e.ganho(p) if e.remuneracao != "NENHUM" else None,
    }


def resumo_ganhos(es) -> dict:
    agora = timezone.localtime()
    hoje = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    semana = hoje - timedelta(days=hoje.weekday())
    mes = hoje.replace(day=1)
    por_id = {e.id: e for e in es}
    feitas = list(Pedido.objects.filter(entregador__in=es, status=S.CONCLUIDO, concluido_em__gte=min(mes, semana))
                  .only("id", "entregador_id", "taxa_entrega_centavos", "concluido_em"))
    def soma(desde):
        ps = [p for p in feitas if p.concluido_em >= desde]
        return len(ps), sum(por_id[p.entregador_id].ganho(p) for p in ps)
    n_hoje, g_hoje = soma(hoje)
    n_sem, g_sem = soma(semana)
    n_mes, g_mes = soma(mes)
    dias_mes = calendar.monthrange(agora.year, agora.month)[1]
    mostrar = any(e.remuneracao != "NENHUM" for e in es)
    return {
        "hoje": {"entregas": n_hoje, "ganhos_centavos": g_hoje},
        "semana": {"entregas": n_sem, "ganhos_centavos": g_sem},
        "mes": {"entregas": n_mes, "ganhos_centavos": g_mes},
        "projecao_mes_centavos": round(g_mes / agora.day * dias_mes) if n_mes else 0,
        "projecao_entregas_mes": round(n_mes / agora.day * dias_mes) if n_mes else 0,
        "total_entregas": Pedido.objects.filter(entregador__in=es, status=S.CONCLUIDO).count(),
        "mostrar_ganhos": mostrar,
        "acordo": [{"loja": e.loja.nome, "regra": e.get_remuneracao_display(),
                    "valor_centavos": e.valor_por_entrega_centavos if e.remuneracao == "FIXO" else None} for e in es],
    }


def rota(pedidos: list[Pedido], es) -> list[Pedido]:
    """Ordem das paradas: primeiro o que falta retirar; depois as entregas pelo caminho mais curto
    (sempre a mais perto de onde ele está), a partir da posição do entregador ou da loja."""
    from apfood_core.entrega import distancia_km

    retirar = [p for p in pedidos if p.status != S.SAIU_PARA_ENTREGA]
    rua = [p for p in pedidos if p.status == S.SAIU_PARA_ENTREGA]
    if len(rua) < 2:
        return retirar + rua
    e = next((x for x in es if x.latitude is not None), None)
    pos = (float(e.latitude), float(e.longitude)) if e else None
    if pos is None and rua[0].loja.latitude is not None:
        pos = (float(rua[0].loja.latitude), float(rua[0].loja.longitude))
    com = [p for p in rua if p.entrega_latitude is not None and p.entrega_longitude is not None]
    sem = [p for p in rua if p not in com]
    ordem = []
    while com and pos is not None:
        prox = min(com, key=lambda p: distancia_km(pos[0], pos[1], float(p.entrega_latitude), float(p.entrega_longitude)))
        ordem.append(prox)
        com.remove(prox)
        pos = (float(prox.entrega_latitude), float(prox.entrega_longitude))
    return retirar + ordem + com + sem


def _paradas(pedidos) -> dict:
    rua = [p for p in pedidos if p.status == S.SAIU_PARA_ENTREGA]
    return {p.id: {"parada": i + 1, "paradas": len(rua)} for i, p in enumerate(rua)} if len(rua) > 1 else {}


class EstadoView(Base):
    def get(self, request):
        es = entregadores_da(request)
        ch = chamadas.oferta_para(es)
        entregas = rota(list(Pedido.objects.filter(entregador__in=es, status__in=EM_ANDAMENTO)
                             .select_related("loja").prefetch_related("pagamentos").order_by("criado_em")), es)
        por_id = {e.id: e for e in es}
        paradas = _paradas(entregas)
        return Response({
            "nome": es[0].nome, "online": any(e.online for e in es), "lojas": [e.loja.nome for e in es],
            "trocar_pin": not all(e.pin_trocado for e in es),
            "oferta": _oferta(ch, es) if ch else None,
            "entregas": [{**_entrega(p, por_id[p.entregador_id]), **paradas.get(p.id, {})} for p in entregas],
            "ganhos": {**resumo_ganhos(es), **acertos.para_app(es)},
            "repasses": cobranca_entrega.para_app(es),
        })


class HistoricoView(Base):
    def get(self, request):
        es = entregadores_da(request)
        por_id = {e.id: e for e in es}
        ps = (Pedido.objects.filter(entregador__in=es, status=S.CONCLUIDO).select_related("loja")
              .order_by("-concluido_em")[:50])
        return Response([{"numero": p.numero, "loja": p.loja.nome, "bairro": p.entrega_bairro,
                          "concluido_em": p.concluido_em,
                          "ganho_centavos": por_id[p.entregador_id].ganho(p)} for p in ps])


# ----------------------------------------------------------------------------- ações
class OfertaView(Base):
    def post(self, request, chamada, acao):
        if acao not in ("aceitar", "recusar"):
            raise ValidationError({"detail": "ação inválida"})
        es = entregadores_da(request)
        from apps.pedidos.models import ChamadaEntrega

        ch = ChamadaEntrega.objects.filter(pk=chamada).first()
        e = next((x for x in es if ch and x.id == ch.entregador_atual_id), None)
        if ch is None or e is None:
            raise ErroNegocio("esta entrega não está mais disponível")
        if acao == "aceitar":
            chamadas.aceitar(ch.id, e)
            return Response({"ok": True})
        chamadas.recusar(ch.id, e)
        return Response({"ok": True})


class EntregaView(Base):
    def _dele(self, request, pedido):
        es = entregadores_da(request)
        p = Pedido.objects.filter(pk=pedido, entregador__in=es).first()
        if p is None:
            raise ErroNegocio("pedido não encontrado")
        return p, next(x for x in es if x.id == p.entregador_id)

    def get(self, request, pedido, acao):
        if acao != "pix":
            raise ValidationError({"detail": "ação inválida"})
        p, e = self._dele(request, pedido)
        return Response(cobranca_entrega.situacao_pix(p.id, e))

    def post(self, request, pedido, acao):
        if acao not in ("retirar", "entregar", "cobrar", "pix"):
            raise ValidationError({"detail": "ação inválida"})
        p, e = self._dele(request, pedido)
        codigo = str(request.data.get("codigo", ""))
        if acao == "cobrar":
            d = request.data
            pg = cobranca_entrega.cobrar(p.id, e, str(d.get("forma", "")), recebido=d.get("valor_recebido_centavos"),
                                         troco=d.get("troco_centavos"), bandeira=str(d.get("bandeira") or ""))
            return Response({"ok": True, "status": pg.status})
        if acao == "pix":
            pg = cobranca_entrega.gerar_pix(p.id, e)
            return Response({"qr_code": pg.dados_externos.get("qr_code", ""),
                             "qr_code_base64": pg.dados_externos.get("qr_code_base64", ""),
                             "valor_centavos": pg.valor_centavos}, status=201)
        if acao == "retirar":
            chamadas.retirar(p.id, e, codigo)
        else:
            chamadas.entregar(p.id, e, codigo)
        return Response({"ok": True})



class RepasseView(Base):
    """O entregador declara o dinheiro das entregas que entregou na loja."""

    def post(self, request):
        es = entregadores_da(request)
        eid = str(request.data.get("entregador_id") or "")
        e = next((x for x in es if str(x.id) == eid), es[0] if len(es) == 1 else None)
        if e is None:
            raise ErroNegocio("escolha a loja")
        r = cobranca_entrega.informar(e, request.data.get("valor_centavos"))
        return Response({"ok": True, "repasse": str(r.id)}, status=201)


class FotoEntregaView(Base):
    """Cliente não estava: conclui com a foto do pedido deixado no local (multipart: foto, observacao)."""

    def post(self, request, pedido):
        es = entregadores_da(request)
        p = Pedido.objects.filter(pk=pedido, entregador__in=es).first()
        if p is None:
            raise ErroNegocio("pedido não encontrado")
        e = next(x for x in es if x.id == p.entregador_id)
        chamadas.entregar_com_foto(p.id, e, request.FILES.get("foto"), str(request.data.get("observacao") or ""))
        return Response({"ok": True})
