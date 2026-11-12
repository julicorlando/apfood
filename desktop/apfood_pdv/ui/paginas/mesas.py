"""Salão: mapa de mesas e comandas. Abrir, lançar rodada, ver/imprimir a conta,
pedir conta, dividir, receber, fechar, transferir e juntar mesas."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QInputDialog, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ...api import SemConexao
from ..dialogos import DialogoEscolha, DialogoPagamento, DialogoTexto
from ..util import botao, confirmar, erro, reais, seguro


class PaginaMesas(QWidget):
    lancar_rodada = Signal(dict)  # comanda → abre a tela de venda em modo MESA

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.comandas: list[dict] = []
        lay = QVBoxLayout(self)
        topo = QHBoxLayout()
        t = QLabel("Mesas")
        t.setProperty("papel", "titulo")
        topo.addWidget(t)
        topo.addStretch()
        topo.addWidget(botao("Comanda avulsa", self.comanda_avulsa))
        topo.addWidget(botao("Atualizar", self.atualizar, atalho="F5"))
        lay.addLayout(topo)
        self.grade_w = QWidget()
        self.grade = QGridLayout(self.grade_w)
        self.grade.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        rol = QScrollArea()
        rol.setWidgetResizable(True)
        rol.setWidget(self.grade_w)
        lay.addWidget(rol, 1)
        self.info = QLabel("Clique numa mesa livre para abrir; numa ocupada para ver as opções.")
        lay.addWidget(self.info)

    def ao_mostrar(self):
        self.atualizar()

    def atualizar(self):
        try:
            r = self.ctx.api.get("/api/comandas/", abertas=1, limit=500)
            self.comandas = r["results"] if isinstance(r, dict) else r
        except SemConexao:
            self.info.setText("Sem internet: o mapa de mesas mostra só o cadastro (comandas abertas indisponíveis).")
            self.comandas = []
        except Exception as e:  # noqa: BLE001
            self.info.setText(f"Erro: {e}")
            self.comandas = []
        while self.grade.count():
            w = self.grade.takeAt(0).widget()
            if w:
                w.deleteLater()
        mesas = sorted((m for m in self.ctx.banco.listar("mesas") if m.get("ativa", True)),
                       key=lambda m: (m.get("area", ""), m.get("ordem", 0), m["nome"]))
        por_mesa: dict[str, list] = {}
        for c in self.comandas:
            por_mesa.setdefault(str(c.get("mesa") or ""), []).append(c)
        n = 0
        for m in mesas:
            cs = por_mesa.get(str(m["id"]), [])
            total = sum(c["total_centavos"] for c in cs)
            fechando = any(c["status"] == "FECHANDO" for c in cs)
            texto = f"{m['nome']}\n{m.get('area', '')}\n" + (f"{reais(total)}" + ("\nCONTA" if fechando else "") if cs else "livre")
            b = QPushButton(texto)
            b.setMinimumSize(130, 90)
            cor = "#FFE0B2" if fechando else "#FFCDD2" if cs else "#E8F5E9"
            b.setStyleSheet(f"background:{cor}; font-weight:600; border-radius:8px;")
            b.clicked.connect(lambda _=False, mesa=m, coms=cs: self.clicar(mesa, coms))
            self.grade.addWidget(b, n // 6, n % 6)
            n += 1
        for c in por_mesa.get("", []):  # comandas avulsas (sem mesa)
            b = QPushButton(f"Comanda {c.get('numero') or c.get('nome_cliente') or ''}\n{reais(c['total_centavos'])}")
            b.setMinimumSize(130, 90)
            b.setStyleSheet("background:#E3F2FD; font-weight:600; border-radius:8px;")
            b.clicked.connect(lambda _=False, com=c: self.opcoes(com))
            self.grade.addWidget(b, n // 6, n % 6)
            n += 1
        if not mesas:
            self.grade.addWidget(QLabel("Nenhuma mesa cadastrada (cadastre no painel web → Mesas)."), 0, 0)

    def _mesa_nome(self, comanda) -> str:
        m = self.ctx.banco.obter("mesas", comanda.get("mesa")) if comanda.get("mesa") else None
        return m["nome"] if m else (comanda.get("numero") or comanda.get("nome_cliente") or "Comanda")

    def clicar(self, mesa: dict, comandas: list[dict]):
        if not comandas:
            pessoas, ok = QInputDialog.getInt(self, mesa["nome"], "Quantas pessoas?", 2, 1, 50)
            if not ok:
                return
            c = seguro(self, self.ctx.api.post, "/api/comandas/", {"mesa": mesa["id"], "pessoas": pessoas})
            if c:
                self.lancar_rodada.emit({**c, "mesa_nome": mesa["nome"]})
            return
        c = comandas[0] if len(comandas) == 1 else DialogoEscolha(
            "Comandas da mesa", [(f"{x.get('nome_cliente') or x.get('numero') or 'Comanda'} — {reais(x['total_centavos'])}", x)
                                 for x in comandas], self)
        if isinstance(c, DialogoEscolha):
            if not c.exec():
                return
            c = c.valor()
        self.opcoes(c)

    def comanda_avulsa(self):
        nome, ok = QInputDialog.getText(self, "Comanda avulsa", "Número do cartão ou nome do cliente:")
        if ok and nome.strip():
            c = seguro(self, self.ctx.api.post, "/api/comandas/",
                       {"numero": nome.strip()[:20], "nome_cliente": nome.strip()})
            if c:
                self.lancar_rodada.emit({**c, "mesa_nome": nome.strip()})

    def opcoes(self, c: dict):
        nome = self._mesa_nome(c)
        acoes = [("Lançar itens", "rodada"), ("Ver / imprimir conta", "conta"), ("Pedir conta (congela valores)", "pedir"),
                 ("Receber pagamento", "receber"), ("Fechar comanda", "fechar"), ("Transferir de mesa", "transferir"),
                 ("Juntar com outra comanda", "juntar"), ("Tirar/pôr taxa de serviço", "taxa")]
        if c["status"] == "FECHANDO":
            acoes.insert(1, ("Reabrir (voltar a lançar)", "reabrir"))
        d = DialogoEscolha(f"{nome} — {reais(c['total_centavos'])}", acoes, self)
        if not d.exec():
            return
        getattr(self, f"_acao_{d.valor()}")(c, nome)
        self.atualizar()

    def _acao_rodada(self, c, nome):
        if c["status"] != "ABERTA":
            erro(self, "A conta já foi pedida. Reabra a comanda para lançar mais itens.")
            return
        self.lancar_rodada.emit({**c, "mesa_nome": nome})

    def _acao_conta(self, c, nome):
        r = seguro(self, self.ctx.api.get, f"/api/comandas/{c['id']}/cupom/", largura=self.ctx.cfg.largura_bobina)
        if not r:
            return
        from ...impressao import para_texto

        divisao = seguro(self, self.ctx.api.get, f"/api/comandas/{c['id']}/divisao/") or {}
        partes = divisao.get("partes_centavos", [])
        rodape = f"Dividido por {len(partes)}: " + " / ".join(reais(p) for p in partes) if len(partes) > 1 else ""
        DialogoTexto(f"Conta — {nome}", para_texto(r["linhas"], self.ctx.cfg.largura_bobina), self, rodape=rodape,
                     acoes=[("Imprimir", lambda: seguro(self, self.ctx.imprimir, r["linhas"]))]).exec()

    def _acao_pedir(self, c, nome):
        if seguro(self, self.ctx.api.post, f"/api/comandas/{c['id']}/pedir-conta/") is not None:
            self._acao_conta({**c, "status": "FECHANDO"}, nome)

    def _acao_reabrir(self, c, nome):
        seguro(self, self.ctx.api.post, f"/api/comandas/{c['id']}/reabrir/")

    def _acao_receber(self, c, nome):
        atual = seguro(self, self.ctx.api.get, f"/api/comandas/{c['id']}/")
        if not atual:
            return
        pago = sum(p["valor_centavos"] for p in atual.get("pagamentos", []) if p["status"] == "CONFIRMADO")
        pessoas, ok = QInputDialog.getInt(self, "Dividir a conta", "Dividir entre quantas pessoas? (1 = não dividir)",
                                          atual.get("pessoas", 1), 1, 50)
        if not ok:
            return
        if pessoas > 1:
            partes = (seguro(self, self.ctx.api.get, f"/api/comandas/{c['id']}/divisao/", pessoas=pessoas) or {}).get(
                "partes_centavos", [])
            self.ctx.status("Partes: " + " / ".join(reais(p) for p in partes))
        d = DialogoPagamento(atual["total_centavos"], ja_pago=pago, parent=self,
                             pix_fn=lambda v: {"qr_code": "", **self.ctx.api.post(f"/api/comandas/{c['id']}/pix/",
                                                                                 {"valor_centavos": v})})
        if not d.exec() or d.pendente:
            return
        for pg in d.pagamentos:
            corpo = {"forma": pg["forma"], "valor_centavos": pg["valor_centavos"],
                     "valor_recebido_centavos": pg.get("recebido_centavos"), "bandeira": pg.get("bandeira", "")}
            if seguro(self, self.ctx.api.post, f"/api/comandas/{c['id']}/pagamentos/", corpo) is None:
                return
        if d.troco_total():
            self.ctx.status(f"TROCO: {reais(d.troco_total())}")
        if pago + sum(p["valor_centavos"] for p in d.pagamentos) >= atual["total_centavos"] and \
                confirmar(self, "Conta paga. Fechar a comanda e liberar a mesa?"):
            self._acao_fechar(c, nome)

    def _acao_fechar(self, c, nome):
        if seguro(self, self.ctx.api.post, f"/api/comandas/{c['id']}/fechar/") is not None:
            self.ctx.status(f"{nome} fechada")
            r = seguro(self, self.ctx.api.get, f"/api/comandas/{c['id']}/cupom/", largura=self.ctx.cfg.largura_bobina)
            if r:
                try:
                    self.ctx.imprimir(r["linhas"], gaveta=True)
                except Exception as e:  # noqa: BLE001
                    self.ctx.status(f"Impressão: {e}")

    def _acao_transferir(self, c, nome):
        ocupadas = {str(x.get("mesa")) for x in self.comandas}
        livres = [(m["nome"], m["id"]) for m in self.ctx.banco.listar("mesas")
                  if m.get("ativa", True) and str(m["id"]) not in ocupadas]
        d = DialogoEscolha("Transferir para", livres, self)
        if d.exec() and d.valor():
            seguro(self, self.ctx.api.post, f"/api/comandas/{c['id']}/transferir/", {"mesa": d.valor()})

    def _acao_juntar(self, c, nome):
        outras = [(f"{self._mesa_nome(x)} — {reais(x['total_centavos'])}", x["id"]) for x in self.comandas
                  if x["id"] != c["id"] and x["status"] == "ABERTA"]
        d = DialogoEscolha(f"Trazer para {nome} a comanda:", outras, self)
        if d.exec() and d.valor():
            seguro(self, self.ctx.api.post, f"/api/comandas/{c['id']}/juntar/", {"origem": d.valor()})

    def _acao_taxa(self, c, nome):
        seguro(self, self.ctx.api.post, f"/api/comandas/{c['id']}/ajustar/",
               {"cobrar_taxa_servico": not c.get("cobrar_taxa_servico", True)})
