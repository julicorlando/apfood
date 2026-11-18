"""Fila de pedidos: online (com alerta sonoro até aceitar), balcão, delivery,
mesa e iFood. Aceitar/recusar, avançar status, despachar com motoboy,
receber, cancelar e reimprimir. Atualiza por WebSocket e, de reserva, a cada 15 s."""

from __future__ import annotations

from apfood_core.cupom import para_texto
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QSplitter, QTableWidget,
    QVBoxLayout, QWidget,
)

from ...api import SemConexao
from ..dialogos import DialogoConfirmarMotivo, DialogoEscolha, DialogoPagamento
from ..util import CANAIS, FORMAS, STATUS, botao, dado_selecionado, erro, preencher_tabela, reais, seguro

PROXIMO = {"PENDENTE": "RECEBIDO", "RECEBIDO": "EM_PREPARO", "EM_PREPARO": "PRONTO"}


class PaginaPedidos(QWidget):
    pendentes_mudou = Signal(int)  # nº de pedidos online aguardando aceite (alerta)

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.pedidos: list[dict] = []
        lay = QVBoxLayout(self)
        topo = QHBoxLayout()
        t = QLabel("Pedidos")
        t.setProperty("papel", "titulo")
        topo.addWidget(t)
        topo.addStretch()
        self.filtro = QComboBox()
        self.filtro.addItem("Em andamento", "abertos")
        self.filtro.addItem("Aguardando aceite", "PENDENTE")
        self.filtro.addItem("Prontos / em entrega", "PRONTO,SAIU_PARA_ENTREGA")
        self.filtro.addItem("Hoje (todos)", "hoje")
        self.filtro.currentIndexChanged.connect(lambda *_: self.atualizar())
        topo.addWidget(self.filtro)
        self.so_canal = QComboBox()
        self.so_canal.addItem("Todos os canais", "")
        for k, v in CANAIS.items():
            self.so_canal.addItem(v, k)
        self.so_canal.currentIndexChanged.connect(lambda *_: self.atualizar())
        topo.addWidget(self.so_canal)
        self.auto_imprimir = QCheckBox("Imprimir cozinha ao aceitar")
        self.auto_imprimir.setChecked(True)
        topo.addWidget(self.auto_imprimir)
        topo.addWidget(botao("Atualizar  [F5]", self.atualizar, atalho="F5"))
        lay.addLayout(topo)

        div = QSplitter(Qt.Horizontal)
        self.tabela = QTableWidget()
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabela.itemSelectionChanged.connect(self._detalhar)
        div.addWidget(self.tabela)
        lado = QWidget()
        ll = QVBoxLayout(lado)
        self.detalhe = QPlainTextEdit()
        self.detalhe.setReadOnly(True)
        self.detalhe.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 12px;")
        ll.addWidget(self.detalhe, 1)
        self.btn_aceitar = botao("Aceitar  [A]", self.aceitar, "primario", "A")
        self.btn_recusar = botao("Recusar", self.recusar, "perigo")
        self.btn_avancar = botao("Avançar status  [Espaço]", self.avancar, atalho="Space")
        self.btn_despachar = botao("Saiu para entrega", self.despachar)
        self.btn_chamar = botao("🛵 Chamar entregador (app)", self.chamar_entregador, "primario")
        self.lbl_chamada = QLabel("")
        self.lbl_chamada.setWordWrap(True)
        self.lbl_chamada.setStyleSheet("padding:6px;border-radius:6px")
        ll.addWidget(self.lbl_chamada)
        self.btn_concluir = botao("Concluir", self.concluir)
        self.btn_receber = botao("Receber pagamento", self.receber)
        self.btn_cancelar = botao("Cancelar pedido", self.cancelar, "perigo")
        g1, g2, g3 = QHBoxLayout(), QHBoxLayout(), QHBoxLayout()
        for b in (self.btn_aceitar, self.btn_recusar):
            g1.addWidget(b)
        for b in (self.btn_avancar, self.btn_chamar, self.btn_despachar, self.btn_concluir):
            g2.addWidget(b)
        for b in (self.btn_receber, botao("Reimprimir cupom", self.reimprimir),
                  botao("Via cozinha", self.reimprimir_cozinha), self.btn_cancelar):
            g3.addWidget(b)
        for g in (g1, g2, g3):
            ll.addLayout(g)
        div.addWidget(lado)
        div.setStretchFactor(0, 3)
        div.setStretchFactor(1, 2)
        lay.addWidget(div, 1)

        self.timer = QTimer(self)
        self.timer.setInterval(15000)
        self.timer.timeout.connect(self.atualizar)
        self.timer_chamada = QTimer(self)  # andamento da chamada do entregador (30 s por entregador, até 2 min)
        self.timer_chamada.setInterval(2500)
        self.timer_chamada.timeout.connect(self._acompanhar_chamada)
        self._chamada_pedido = None
        self._botoes(None)

    def ao_mostrar(self):
        self.atualizar()
        self.timer.start()

    # ----------------------------------------------------------------- dados
    def atualizar(self):
        f = self.filtro.currentData()
        params = {"limit": 200, "ordering": "-criado_em"}
        if f == "abertos":
            params["abertos"] = 1
        elif f == "hoje":
            from datetime import date

            params["data"] = date.today().isoformat()
        else:
            params["status"] = f.split(",")
        if self.so_canal.currentData():
            params["canal"] = self.so_canal.currentData()
        try:
            r = self.ctx.api.get("/api/pedidos/", **params)
        except SemConexao:
            self.ctx.status("Sem internet: a fila online não pode ser atualizada (pedidos locais seguem na fila de envio)")
            return
        except Exception as e:  # noqa: BLE001
            self.ctx.status(f"Erro ao carregar pedidos: {e}")
            return
        selecionado = (dado_selecionado(self.tabela) or {}).get("id")
        self.pedidos = r["results"] if isinstance(r, dict) else r
        linhas = []
        for p in self.pedidos:
            pago = sum(pg["valor_centavos"] for pg in p.get("pagamentos", []) if pg["status"] == "CONFIRMADO")
            situacao = "PAGO" if pago >= p["total_centavos"] else ("na entrega" if any(
                pg["status"] == "PENDENTE" for pg in p.get("pagamentos", [])) else "A RECEBER")
            quem = p.get("nome_cliente") or (f"Mesa {p['mesa']}" if p.get("mesa") else "") or p.get("senha") or ""
            if p.get("agendado_para"):
                quem = f"📅 {p['agendado_para'][8:10]}/{p['agendado_para'][5:7]} {p['agendado_para'][11:16]} · {quem}"
            linhas.append([f"#{p.get('numero') or p.get('codigo_local')}", p["criado_em"][11:16],
                           CANAIS.get(p["canal"], p["canal"]) + (" ⚠" if p["status"] == "PENDENTE" else ""),
                           quem, STATUS.get(p["status"], p["status"]), reais(p["total_centavos"]), situacao])
        preencher_tabela(self.tabela, ["Nº", "Hora", "Canal", "Cliente/Mesa", "Status", "Total", "Pagamento"],
                         linhas, self.pedidos)
        for r_, p in enumerate(self.pedidos):
            if p["status"] == "PENDENTE":
                for c in range(self.tabela.columnCount()):
                    self.tabela.item(r_, c).setBackground(Qt.yellow)
            if p["id"] == selecionado:
                self.tabela.selectRow(r_)
        self.pendentes_mudou.emit(sum(1 for p in self.pedidos if p["status"] == "PENDENTE"))

    def selecionado(self) -> dict | None:
        return dado_selecionado(self.tabela)

    def _detalhar(self):
        p = self.selecionado()
        self._botoes(p)
        if not p:
            self.detalhe.clear()
            return
        from apfood_core.cupom import comprovante_venda

        itens = [{"quantidade": i["quantidade"], "nome": i["nome_produto"], "variacao": i.get("nome_variacao", ""),
                  "total_centavos": i["total_centavos"], "observacao": i.get("observacao", ""),
                  "sabores": [s["nome"] for s in i.get("sabores", [])] if len(i.get("sabores", [])) > 1 else [],
                  "adicionais": i.get("adicionais", [])} for i in p.get("itens", [])]
        endereco = ""
        if p.get("entrega_logradouro"):
            endereco = f"{p['entrega_logradouro']}, {p['entrega_numero']} - {p.get('entrega_bairro', '')}"
            if p.get("entrega_referencia"):
                endereco += f" ({p['entrega_referencia']})"
        prev = {**p, "itens": itens, "endereco": endereco, "data": None,
                "pagamentos": [{"forma": pg["forma"], "valor_centavos": pg["valor_centavos"],
                                "troco_centavos": pg.get("troco_centavos", 0)}
                               for pg in p.get("pagamentos", []) if pg["status"] == "CONFIRMADO"]}
        from datetime import datetime

        prev["data"] = datetime.fromisoformat(p["criado_em"].replace("Z", "+00:00"))
        texto = para_texto(comprovante_venda(prev, self.ctx.loja_para_cupom(), 44), 44)
        pend = [pg for pg in p.get("pagamentos", []) if pg["status"] == "PENDENTE"]
        if pend:
            texto += "\n\nPAGAR NA ENTREGA: " + ", ".join(f"{FORMAS.get(pg['forma'], pg['forma'])} {reais(pg['valor_centavos'])}"
                                                       for pg in pend)
        extra = []
        if p.get("agendado_para"):
            extra.append(f"📅 AGENDADO PARA {p['agendado_para'][8:10]}/{p['agendado_para'][5:7]} às {p['agendado_para'][11:16]}")
        if p.get("tipo_atendimento") == "ENTREGA":
            if p.get("entregador_nome"):
                extra.append(f"🛵 Entregador: {p['entregador_nome']}")
            if p.get("entregador") and p["status"] in ("RECEBIDO", "EM_PREPARO", "PRONTO"):
                extra.append(f"🔑 CÓDIGO DE RETIRADA: {p.get('codigo_retirada', '')}  (o entregador digita no app ao pegar)")
        if extra:
            texto = "\n".join(extra) + "\n" + "=" * 44 + "\n" + texto
        self.detalhe.setPlainText(texto)
        if self._chamada_pedido != p["id"]:
            self.lbl_chamada.clear()
            self.lbl_chamada.setStyleSheet("padding:6px;border-radius:6px")

    def _botoes(self, p):
        st = p["status"] if p else None
        self.btn_aceitar.setEnabled(st == "PENDENTE")
        self.btn_recusar.setEnabled(st == "PENDENTE")
        self.btn_avancar.setEnabled(st in ("RECEBIDO", "EM_PREPARO"))
        self.btn_despachar.setEnabled(st in ("RECEBIDO", "EM_PREPARO", "PRONTO") and p.get("tipo_atendimento") == "ENTREGA")
        self.btn_chamar.setEnabled(st in ("RECEBIDO", "EM_PREPARO", "PRONTO") and p.get("tipo_atendimento") == "ENTREGA"
                                   and not p.get("entregador"))
        self.btn_concluir.setEnabled(st in ("PRONTO", "SAIU_PARA_ENTREGA"))
        self.btn_receber.setEnabled(bool(p) and st not in ("CANCELADO", "RECUSADO") and self._falta(p) > 0)
        self.btn_cancelar.setEnabled(st not in (None, "CONCLUIDO", "CANCELADO", "RECUSADO"))

    @staticmethod
    def _falta(p) -> int:
        # o dinheiro que o entregador já cobrou na porta (aguardando o repasse) conta como pago
        return p["total_centavos"] - sum(pg["valor_centavos"] for pg in p.get("pagamentos", [])
                                         if pg["status"] == "CONFIRMADO" or (pg["status"] == "PENDENTE" and pg.get("cobrado_em")))

    # ----------------------------------------------------------------- ações
    def _status(self, p, status, motivo="", entregador=None) -> bool:
        r = seguro(self, self.ctx.pdv.mudar_status, p["id"], status, motivo, entregador)
        if r is None:
            return False
        self.atualizar()
        return True

    def aceitar(self):
        p = self.selecionado()
        if p and self._status(p, "RECEBIDO"):
            self.ctx.status(f"Pedido #{p['numero']} aceito")
            if self.auto_imprimir.isChecked():
                self._imprimir_cozinha(p)

    def recusar(self):
        p = self.selecionado()
        if not p:
            return
        d = DialogoConfirmarMotivo("Recusar pedido", f"Recusar o pedido #{p['numero']}? O cliente será avisado.", self)
        if d.exec():
            self._status(p, "RECUSADO", d.motivo.text().strip())

    def avancar(self):
        p = self.selecionado()
        if p and p["status"] in PROXIMO:
            self._status(p, PROXIMO[p["status"]])

    def despachar(self):
        p = self.selecionado()
        if not p:
            return
        motoboys = [(e["nome"], e["id"]) for e in self.ctx.banco.listar("entregadores") if e.get("ativo", True)]
        entregador = p.get("entregador")
        if motoboys:
            d = DialogoEscolha("Quem vai entregar?", motoboys, self)
            if not d.exec():
                return
            entregador = d.valor()
        # caminho válido até SAIU_PARA_ENTREGA
        atual = p["status"]
        while atual in ("RECEBIDO", "EM_PREPARO"):
            if not self._status(p, "PRONTO"):
                return
            atual = "PRONTO"
        self._status(p, "SAIU_PARA_ENTREGA", entregador=entregador)

    # ----------------------------------------------- chamar entregador (app ApFood Entregador)
    def chamar_entregador(self):
        p = self.selecionado()
        if not p:
            return
        r = seguro(self, self.ctx.api.post, f"/api/pedidos/{p['id']}/chamada/", {})
        if r is None:
            return
        self._chamada_pedido = p["id"]
        self._mostrar_chamada(p, r)
        self.timer_chamada.start()

    def _acompanhar_chamada(self):
        pid = self._chamada_pedido
        if not pid:
            self.timer_chamada.stop()
            return
        try:
            r = self.ctx.api.get(f"/api/pedidos/{pid}/chamada/")
        except Exception:  # noqa: BLE001 - tenta de novo no próximo ciclo
            return
        p = next((x for x in self.pedidos if x["id"] == pid), {"id": pid, "numero": ""})
        self._mostrar_chamada(p, r)

    def _mostrar_chamada(self, p, r):
        c = (r or {}).get("chamada") or {}
        st = c.get("status")
        if st == "PROCURANDO":
            quem = (f"oferecendo para {c['entregador_atual']} ({c['segundos_oferta']} s)" if c.get("entregador_atual")
                    else "nenhum entregador disponível no app agora — aguardando")
            self.lbl_chamada.setStyleSheet("padding:6px;border-radius:6px;background:#fdf3e1;color:#8a5a00")
            self.lbl_chamada.setText(f"Procurando entregador para o pedido #{p.get('numero')}: {quem}. "
                                     f"Tentativas: {c.get('tentativas', 0)} · resta {c.get('segundos_total', 0)} s")
            return
        self.timer_chamada.stop()
        self._chamada_pedido = None
        if st == "ACEITA":
            self.lbl_chamada.setStyleSheet("padding:6px;border-radius:6px;background:#e5f5ec;color:#1f8a4c")
            self.lbl_chamada.setText(f"✓ {c.get('aceita_por')} aceitou a entrega do pedido #{p.get('numero')}.")
            self.ctx.status(f"{c.get('aceita_por')} aceitou o pedido #{p.get('numero')}")
            self.atualizar()
        elif st == "SEM_RESPOSTA":
            self.lbl_chamada.setStyleSheet("padding:6px;border-radius:6px;background:#fbe9e7;color:#c0392b")
            self.lbl_chamada.setText(f"Ninguém aceitou o pedido #{p.get('numero')} em 2 minutos.")
            d = DialogoEscolha(f"Ninguém aceitou o pedido #{p.get('numero')}",
                               [("Chamar novamente", "chamar"), ("Outra forma: escolher o entregador", "manual")], self)
            if d.exec():
                sel = next((x for x in self.pedidos if x["id"] == p.get("id")), None)
                if sel is not None:
                    self._selecionar(sel["id"])
                (self.chamar_entregador if d.valor() == "chamar" else self.despachar)()
        else:
            self.lbl_chamada.clear()

    def _selecionar(self, pid):
        for r_, x in enumerate(self.pedidos):
            if x["id"] == pid:
                self.tabela.selectRow(r_)
                return

    def concluir(self):
        p = self.selecionado()
        if not p:
            return
        if self._falta(p) > 0 and p["canal"] != "MARKETPLACE":
            erro(self, f"Falta receber {reais(self._falta(p))}. Registre o pagamento antes de concluir.")
            return
        self._status(p, "CONCLUIDO")

    def receber(self):
        p = self.selecionado()
        if not p:
            return
        pago = p["total_centavos"] - self._falta(p)
        d = DialogoPagamento(p["total_centavos"], ja_pago=pago, parent=self,
                             pix_fn=lambda v: {"qr_code": "", **self.ctx.api.post(f"/api/pedidos/{p['id']}/pix/",
                                                                                 {"valor_centavos": v})})
        if not d.exec() or d.pendente:
            self.atualizar()
            return
        for pg in d.pagamentos:
            if seguro(self, self.ctx.pdv.pagar, p["id"], pg["forma"], pg["valor_centavos"], pg.get("recebido_centavos"),
                      pg.get("bandeira", "")) is None:
                break
        troco = d.troco_total()
        try:
            doc = self.ctx.imprimir_venda(p["id"], cpf=p.get("cpf_nota", ""), gaveta=True)
            if doc.get("aviso"):
                self.ctx.status(doc["aviso"])
        except Exception as e:  # noqa: BLE001
            self.ctx.status(f"Impressão: {e}")
        if troco:
            self.ctx.status(f"TROCO: {reais(troco)}")
        self.atualizar()

    def cancelar(self):
        p = self.selecionado()
        if not p:
            return
        d = DialogoConfirmarMotivo("Cancelar pedido", f"Cancelar o pedido #{p['numero']}? O estoque é devolvido e "
                                                       "os pagamentos são estornados.", self)
        if d.exec():
            self._status(p, "CANCELADO", d.motivo.text().strip())

    def _imprimir_cozinha(self, p):
        try:
            n = self.ctx.imprimir_cozinha(p["id"])
            self.ctx.status(f"{n} via(s) de cozinha impressa(s)")
        except Exception as e:  # noqa: BLE001
            self.ctx.status(f"Impressão da cozinha: {e}")

    def reimprimir_cozinha(self):
        if p := self.selecionado():
            self._imprimir_cozinha(p)

    def reimprimir(self):
        p = self.selecionado()
        if not p:
            return
        try:
            if self._falta(p) <= 0:
                notas = self.ctx.api.get("/api/notas-fiscais/", pedido=p["id"], status="AUTORIZADA")
                notas = notas.get("results", notas) if isinstance(notas, dict) else notas
                if notas:
                    linhas = self.ctx.api.get(f"/api/notas-fiscais/{notas[0]['id']}/danfe/",
                                              largura=self.ctx.cfg.largura_bobina)["linhas"]
                    self.ctx.imprimir(linhas)
                    return
            linhas = self.ctx.api.get(f"/api/pedidos/{p['id']}/cupom/", tipo="venda",
                                      largura=self.ctx.cfg.largura_bobina)["linhas"]
            self.ctx.imprimir(linhas)
        except Exception as e:  # noqa: BLE001
            erro(self, e)

    # ------------------------------------------------------------ tempo real
    def evento(self, ev: dict):
        if ev.get("tipo", "").startswith("pedido."):
            self.atualizar()
