"""Lançamento de pedidos: BALCÃO (nome/senha/mesa), DELIVERY (telefone/WhatsApp,
busca o cliente pelo telefone e autopreenche o endereço) e MESA (rodada de uma
comanda). Funciona offline: o pedido vai para a fila e o cupom sai não fiscal."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QRadioButton, QScrollArea, QSplitter, QTableWidget,
    QVBoxLayout, QWidget,
)

from ...api import ErroApi, SemConexao
from ..dialogos import DialogoEscolha, DialogoItem, DialogoPagamento
from ..util import botao, centavos, confirmar, erro, preencher_tabela, reais, seguro


class PaginaVenda(QWidget):
    pedido_lancado = Signal(dict)  # resposta do servidor (ou payload offline)

    MODOS = {"BALCAO": "Balcão", "DELIVERY": "Delivery"}

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.carrinho: list[dict] = []  # {"item": {...api}, "descricao": str, "total": int, "setor": str}
        self.comanda: dict | None = None
        self.cliente: dict | None = None
        self.zona_taxa: int | None = None

        raiz = QHBoxLayout(self)
        divisor = QSplitter(Qt.Horizontal)
        raiz.addWidget(divisor)

        # ---------------- cardápio ----------------
        esquerda = QWidget()
        le = QVBoxLayout(esquerda)
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar produto (nome ou código)…  [F2]")
        self.busca.textChanged.connect(self._mostrar_produtos)
        le.addWidget(self.busca)
        h = QHBoxLayout()
        self.categorias = QListWidget()
        self.categorias.setMaximumWidth(180)
        self.categorias.currentItemChanged.connect(lambda *_: self._mostrar_produtos())
        h.addWidget(self.categorias)
        self.grade_widget = QWidget()
        self.grade = QGridLayout(self.grade_widget)
        self.grade.setAlignment(Qt.AlignTop)
        rol = QScrollArea()
        rol.setWidgetResizable(True)
        rol.setWidget(self.grade_widget)
        h.addWidget(rol, 1)
        le.addLayout(h)
        divisor.addWidget(esquerda)

        # ---------------- pedido ----------------
        direita = QWidget()
        direita.setMinimumWidth(420)
        ld = QVBoxLayout(direita)
        self.titulo = QLabel()
        self.titulo.setProperty("papel", "titulo")
        ld.addWidget(self.titulo)

        modos = QHBoxLayout()
        self.grupo_modo = QButtonGroup(self)
        for i, (chave, rot) in enumerate(self.MODOS.items()):
            rb = QRadioButton(rot)
            rb.setProperty("modo", chave)
            self.grupo_modo.addButton(rb, i)
            modos.addWidget(rb)
        self.grupo_modo.button(0).setChecked(True)
        self.grupo_modo.idToggled.connect(lambda *_: self._modo_alterado())
        self.box_modos = QWidget()
        self.box_modos.setLayout(modos)
        ld.addWidget(self.box_modos)

        # balcão
        self.box_balcao = QGroupBox("Identificação")
        fb = QFormLayout(self.box_balcao)
        self.atendimento = QComboBox()
        self.atendimento.addItem("Consumo no local", "CONSUMO_LOCAL")
        self.atendimento.addItem("Retirada / viagem", "RETIRADA")
        self.nome_balcao = QLineEdit()
        self.senha = QLineEdit()
        self.senha.setMaximumWidth(90)
        self.mesa_balcao = QLineEdit()
        self.mesa_balcao.setMaximumWidth(90)
        fb.addRow("Atendimento", self.atendimento)
        fb.addRow("Nome", self.nome_balcao)
        linha = QHBoxLayout()
        linha.addWidget(QLabel("Senha"))
        linha.addWidget(self.senha)
        linha.addWidget(QLabel("Mesa"))
        linha.addWidget(self.mesa_balcao)
        linha.addStretch()
        fb.addRow(linha)
        ld.addWidget(self.box_balcao)

        # delivery
        self.box_delivery = QGroupBox("Cliente e entrega")
        fd = QFormLayout(self.box_delivery)
        tel = QHBoxLayout()
        self.telefone = QLineEdit()
        self.telefone.setPlaceholderText("(11) 98765-4321")
        self.telefone.returnPressed.connect(self.buscar_cliente)
        tel.addWidget(self.telefone)
        tel.addWidget(botao("Buscar", self.buscar_cliente))
        self.origem = QComboBox()
        self.origem.addItem("Telefone", "TELEFONE")
        self.origem.addItem("WhatsApp", "WHATSAPP")
        tel.addWidget(self.origem)
        fd.addRow("Telefone", tel)
        self.nome = QLineEdit()
        fd.addRow("Nome", self.nome)
        self.enderecos = QComboBox()
        self.enderecos.currentIndexChanged.connect(self._usar_endereco)
        fd.addRow("Endereços", self.enderecos)
        self.logradouro, self.numero, self.complemento = QLineEdit(), QLineEdit(), QLineEdit()
        self.bairro, self.referencia = QLineEdit(), QLineEdit()
        self.numero.setMaximumWidth(80)
        r1 = QHBoxLayout()
        r1.addWidget(self.logradouro, 1)
        r1.addWidget(QLabel("Nº"))
        r1.addWidget(self.numero)
        fd.addRow("Rua", r1)
        fd.addRow("Complemento", self.complemento)
        r2 = QHBoxLayout()
        r2.addWidget(self.bairro, 1)
        r2.addWidget(botao("Calcular taxa", self.calcular_taxa))
        fd.addRow("Bairro", r2)
        fd.addRow("Referência", self.referencia)
        r3 = QHBoxLayout()
        self.taxa = QLineEdit()
        self.taxa.setPlaceholderText("0,00")
        self.taxa.setMaximumWidth(90)
        self.taxa.textChanged.connect(self._atualizar_total)
        self.entregador = QComboBox()
        self.troco_para = QLineEdit()
        self.troco_para.setPlaceholderText("troco p/")
        self.troco_para.setMaximumWidth(90)
        r3.addWidget(QLabel("Taxa"))
        r3.addWidget(self.taxa)
        r3.addWidget(QLabel("Motoboy"))
        r3.addWidget(self.entregador, 1)
        r3.addWidget(self.troco_para)
        fd.addRow(r3)
        ld.addWidget(self.box_delivery)

        # carrinho
        self.tabela = QTableWidget()
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setMinimumHeight(160)
        ld.addWidget(self.tabela, 1)
        acoes = QHBoxLayout()
        acoes.addWidget(botao("Remover item", self.remover_item, atalho="Del"))
        acoes.addWidget(botao("+1", lambda: self._quantidade(1)))
        acoes.addWidget(botao("−1", lambda: self._quantidade(-1)))
        acoes.addStretch()
        self.desconto = QLineEdit()
        self.desconto.setPlaceholderText("desconto")
        self.desconto.setMaximumWidth(100)
        self.desconto.textChanged.connect(self._atualizar_total)
        acoes.addWidget(self.desconto)
        ld.addLayout(acoes)
        self.observacao = QLineEdit()
        self.observacao.setPlaceholderText("Observação do pedido")
        ld.addWidget(self.observacao)
        self.cpf = QLineEdit()
        self.cpf.setPlaceholderText("CPF na nota (opcional)")
        ld.addWidget(self.cpf)
        rodape = QHBoxLayout()
        self.total = QLabel()
        self.total.setProperty("papel", "total")
        rodape.addWidget(self.total, 1)
        rodape.addWidget(botao("Limpar", self.limpar))
        self.btn_finalizar = botao("Finalizar  [F12]", self.finalizar, "primario", "F12")
        self.btn_finalizar.setMinimumHeight(48)
        rodape.addWidget(self.btn_finalizar)
        ld.addLayout(rodape)
        divisor.addWidget(direita)
        divisor.setStretchFactor(0, 3)
        divisor.setStretchFactor(1, 2)

        self._modo_alterado()
        self._atualizar_carrinho()

    # ------------------------------------------------------------------ dados
    def ao_mostrar(self):
        self.recarregar_cardapio()

    def recarregar_cardapio(self):
        atual = self.categorias.currentItem().data(Qt.UserRole) if self.categorias.currentItem() else None
        self.categorias.blockSignals(True)
        self.categorias.clear()
        todos = QListWidgetItem("Todos")
        todos.setData(Qt.UserRole, None)
        self.categorias.addItem(todos)
        for c in self.ctx.pdv.categorias():
            it = QListWidgetItem(c["nome"])
            it.setData(Qt.UserRole, c["id"])
            self.categorias.addItem(it)
            if c["id"] == atual:
                self.categorias.setCurrentItem(it)
        if not self.categorias.currentItem():
            self.categorias.setCurrentRow(0)
        self.categorias.blockSignals(False)
        self.entregador.clear()
        self.entregador.addItem("—", None)
        for e in self.ctx.banco.listar("entregadores"):
            if e.get("ativo", True):
                self.entregador.addItem(e["nome"], e["id"])
        self._mostrar_produtos()

    def _mostrar_produtos(self):
        while self.grade.count():
            w = self.grade.takeAt(0).widget()
            if w:
                w.deleteLater()
        cat = self.categorias.currentItem().data(Qt.UserRole) if self.categorias.currentItem() else None
        termo = self.busca.text().strip().lower()
        produtos = self.ctx.pdv.produtos(None if termo else cat)
        if termo:
            produtos = [p for p in produtos if termo in p["nome"].lower() or termo == (p.get("codigo") or "").lower()]
        if not produtos:
            aviso = QLabel("Nenhum produto. Aguarde a sincronização do cardápio\nou cadastre no painel web.")
            aviso.setAlignment(Qt.AlignCenter)
            self.grade.addWidget(aviso, 0, 0)
        colunas = 4
        for n, p in enumerate(produtos):
            vars_ = self.ctx.pdv.variacoes(p["id"])
            preco = f"a partir de {reais(min(v['preco_centavos'] for v in vars_))}" if vars_ else reais(p["preco_centavos"])
            b = QPushButton(f"{p['nome']}\n{preco}")
            b.setProperty("papel", "produto")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, prod=p: self.adicionar_produto(prod))
            self.grade.addWidget(b, n // colunas, n % colunas)

    # --------------------------------------------------------------- carrinho
    def _setor_do_produto(self, produto: dict) -> str:
        setor_id = produto.get("setor")
        if not setor_id:
            cat = self.ctx.banco.obter("categorias", produto.get("categoria")) or {}
            setor_id = cat.get("setor")
        setor = self.ctx.banco.obter("setores", setor_id) if setor_id else None
        return setor["nome"] if setor else ""

    def adicionar_produto(self, produto: dict, *, item: dict | None = None):
        """Abre o diálogo quando há tamanho/sabor/adicional; senão adiciona direto."""
        tem_opcoes = (self.ctx.pdv.variacoes(produto["id"]) or self.ctx.pdv.grupos_do_produto(produto)
                      or ((self.ctx.banco.obter("categorias", produto.get("categoria")) or {}).get("max_sabores", 1) > 1))
        descricao = produto["nome"]
        if item is None and tem_opcoes:
            d = DialogoItem(self.ctx.pdv, produto, self)
            if not d.exec():
                return
            item, descricao = d.item(), d.descricao()
        item = item or {"produto_id": produto["id"], "quantidade": 1, "adicionais": [], "sabores": [],
                        "variacao_id": None, "observacao": ""}
        self.carrinho.append({"item": item, "descricao": descricao, "setor": self._setor_do_produto(produto),
                              "total": self.ctx.pdv.precificar_item(item)})
        self._atualizar_carrinho()

    def _quantidade(self, delta: int):
        r = self.tabela.currentRow()
        if r < 0:
            return
        linha = self.carrinho[r]
        linha["item"]["quantidade"] = max(1, linha["item"]["quantidade"] + delta)
        linha["total"] = self.ctx.pdv.precificar_item(linha["item"])
        self._atualizar_carrinho()
        self.tabela.selectRow(r)

    def remover_item(self):
        r = self.tabela.currentRow()
        if 0 <= r < len(self.carrinho):
            self.carrinho.pop(r)
            self._atualizar_carrinho()

    def _atualizar_carrinho(self):
        preencher_tabela(self.tabela, ["Qtd", "Item", "Obs", "Total"],
                         [[c["item"]["quantidade"], c["descricao"], c["item"].get("observacao", ""), reais(c["total"])]
                          for c in self.carrinho])
        self._atualizar_total()

    def subtotal(self) -> int:
        return sum(c["total"] for c in self.carrinho)

    def _valor(self, campo: QLineEdit) -> int:
        try:
            return centavos(campo.text())
        except ValueError:
            return 0

    def _atualizar_total(self):
        taxa = self._valor(self.taxa) if self.modo == "DELIVERY" else 0
        total = max(0, self.subtotal() + taxa - self._valor(self.desconto))
        self.total.setText(reais(total))
        self.btn_finalizar.setEnabled(bool(self.carrinho))

    # ------------------------------------------------------------------ modos
    @property
    def modo(self) -> str:
        if self.comanda is not None:
            return "MESA"
        return self.grupo_modo.checkedButton().property("modo")

    def _modo_alterado(self):
        self.box_balcao.setVisible(self.modo == "BALCAO")
        self.box_delivery.setVisible(self.modo == "DELIVERY")
        self.box_modos.setVisible(self.comanda is None)
        if self.comanda:
            mesa = self.comanda.get("mesa_nome") or self.comanda.get("numero") or "comanda"
            self.titulo.setText(f"Rodada — {mesa}")
        else:
            self.titulo.setText("Novo pedido — " + self.MODOS[self.modo])
        self._atualizar_total()

    def para_comanda(self, comanda: dict):
        """Chamado pela tela de mesas: lança a próxima rodada na comanda."""
        self.limpar()
        self.comanda = comanda
        self._modo_alterado()

    def novo_delivery(self):
        self.limpar()
        self.grupo_modo.button(1).setChecked(True)
        self.telefone.setFocus()

    # --------------------------------------------------------------- cliente
    def buscar_cliente(self):
        tel = self.telefone.text()
        if len("".join(c for c in tel if c.isdigit())) < 8:
            return
        achados = seguro(self, self.ctx.pdv.buscar_cliente, tel) or []
        self.enderecos.blockSignals(True)
        self.enderecos.clear()
        self.cliente = None
        if not achados:
            self.ctx.status("Cliente novo — preencha nome e endereço")
            self.enderecos.blockSignals(False)
            return
        if len(achados) > 1:
            d = DialogoEscolha("Clientes encontrados", [(f"{c['nome']} — {c['telefone']}", c) for c in achados], self)
            if not d.exec():
                self.enderecos.blockSignals(False)
                return
            self.cliente = d.valor()
        else:
            self.cliente = achados[0]
        self.nome.setText(self.cliente["nome"])
        self.telefone.setText(self.cliente["telefone"])
        for e in self.cliente.get("enderecos", []):
            self.enderecos.addItem(f"{e['logradouro']}, {e['numero']} — {e['bairro']}", e)
        self.enderecos.addItem("Novo endereço…", None)
        self.enderecos.blockSignals(False)
        self.enderecos.setCurrentIndex(0)
        self._usar_endereco()

    def _usar_endereco(self, *_):
        e = self.enderecos.currentData()
        campos = (self.logradouro, self.numero, self.complemento, self.bairro, self.referencia)
        for campo, chave in zip(campos, ("logradouro", "numero", "complemento", "bairro", "referencia"), strict=True):
            campo.setText((e or {}).get(chave, "") or "")
        if e:
            self.calcular_taxa(silencioso=True)

    def calcular_taxa(self, silencioso: bool = False):
        if not self.bairro.text().strip():
            return
        try:
            r = self.ctx.api.post("/api/taxa-entrega/", {"bairro": self.bairro.text().strip()})
            self.taxa.setText(reais(r["taxa_centavos"]).replace("R$ ", ""))
            self.ctx.status(f"Zona {r['nome']} — taxa {reais(r['taxa_centavos'])}")
        except SemConexao:
            if not silencioso:
                self.ctx.status("Sem internet: informe a taxa manualmente")
        except ErroApi as e:
            if not silencioso:
                erro(self, e)

    # ---------------------------------------------------------------- finalizar
    def montar_dados(self) -> dict:
        itens = [c["item"] for c in self.carrinho]
        dados = {"itens": itens, "observacao": self.observacao.text().strip(), "cpf_nota": self.cpf.text().strip(),
                 "desconto_centavos": self._valor(self.desconto)}
        if self.modo == "MESA":
            dados.update(canal="MESA", tipo_atendimento="CONSUMO_LOCAL", comanda=self.comanda["id"],
                         mesa=(self.comanda.get("mesa_nome") or "")[:10])
        elif self.modo == "BALCAO":
            dados.update(canal="BALCAO", tipo_atendimento=self.atendimento.currentData(),
                         nome_cliente=self.nome_balcao.text().strip(), senha=self.senha.text().strip(),
                         mesa=self.mesa_balcao.text().strip())
        else:
            dados.update(
                canal="DELIVERY", tipo_atendimento="ENTREGA", origem_contato=self.origem.currentData(),
                nome_cliente=self.nome.text().strip(), telefone_cliente=self.telefone.text().strip(),
                endereco={"logradouro": self.logradouro.text().strip(), "numero": self.numero.text().strip(),
                          "complemento": self.complemento.text().strip(), "bairro": self.bairro.text().strip(),
                          "referencia": self.referencia.text().strip()},
                taxa_entrega_centavos=self._valor(self.taxa), entregador_id=self.entregador.currentData(),
                troco_para_centavos=self._valor(self.troco_para) or None,
            )
        return dados

    def validar(self) -> str | None:
        if not self.carrinho:
            return "Adicione itens ao pedido."
        if self.modo == "DELIVERY":
            if not self.nome.text().strip() or len("".join(c for c in self.telefone.text() if c.isdigit())) < 10:
                return "Informe nome e telefone (com DDD) do cliente."
            if not (self.logradouro.text().strip() and self.numero.text().strip() and self.bairro.text().strip()):
                return "Informe rua, número e bairro da entrega."
        return None

    def pedido_para_impressao(self, resp: dict, dados: dict, pagamentos: list[dict]) -> dict:
        """Dicionário no formato do apfood_core.cupom (impressão local/offline)."""
        end = dados.get("endereco") or {}
        endereco = ""
        if end.get("logradouro"):
            endereco = f"{end['logradouro']}, {end.get('numero', '')}" + "".join(
                f" - {end[k]}" for k in ("complemento", "bairro", "referencia") if end.get(k))
        return {
            "numero": resp.get("numero"), "codigo_local": resp.get("codigo_local", ""),
            "tipo_atendimento": dados.get("tipo_atendimento"), "mesa": dados.get("mesa", ""),
            "senha": dados.get("senha", ""), "nome_cliente": dados.get("nome_cliente", ""),
            "telefone_cliente": dados.get("telefone_cliente", ""), "atendente": self.ctx.usuario.get("nome", ""),
            "itens": [{"quantidade": c["item"]["quantidade"], "nome": c["descricao"], "total_centavos": c["total"],
                       "observacao": c["item"].get("observacao", ""), "setor": c["setor"]} for c in self.carrinho],
            "subtotal_centavos": resp.get("subtotal_centavos", self.subtotal()),
            "taxa_entrega_centavos": resp.get("taxa_entrega_centavos", 0),
            "desconto_centavos": resp.get("desconto_centavos", 0), "total_centavos": resp.get("total_centavos", 0),
            "troco_para_centavos": dados.get("troco_para_centavos"), "endereco": endereco,
            "observacao": dados.get("observacao", ""),
            "pagamentos": [{"forma": p["forma"], "valor_centavos": p["valor_centavos"],
                            "troco_centavos": max(0, (p.get("recebido_centavos") or 0) - p["valor_centavos"])
                            if p["forma"] == "DINHEIRO" else 0} for p in pagamentos],
        }

    def finalizar(self, *, pagamentos: list[dict] | None = None, pagar: bool = True) -> dict | None:
        """Lança o pedido, recebe (exceto mesa e 'pagar na entrega') e imprime.
        `pagamentos` permite finalizar sem abrir o diálogo (testes / atalhos)."""
        if msg := self.validar():
            erro(self, msg)
            return None
        dados = self.montar_dados()
        resp = seguro(self, self.ctx.pdv.criar_pedido, dados)
        if resp is None:
            return None
        pedido_id = resp["id"]
        pagos: list[dict] = []
        if self.modo != "MESA" and pagar:
            if pagamentos is None:
                d = DialogoPagamento(resp["total_centavos"], parent=self, permitir_pendente=self.modo == "DELIVERY",
                                     pix_fn=None if resp.get("offline") else
                                     (lambda v: {"qr_code": "", **self.ctx.api.post(f"/api/pedidos/{pedido_id}/pix/",
                                                                                   {"valor_centavos": v})}))
                if d.exec() and not d.pendente:
                    pagamentos = d.pagamentos
                else:
                    pagamentos = []
            for p in pagamentos:
                r = seguro(self, self.ctx.pdv.pagar, pedido_id, p["forma"], p["valor_centavos"],
                           p.get("recebido_centavos"), p.get("bandeira", ""))
                if r is not None:
                    pagos.append(p)
        local = self.pedido_para_impressao(resp, dados, pagos)
        pago = sum(p["valor_centavos"] for p in pagos) >= resp.get("total_centavos", 0) and bool(pagos)
        avisos = self.ctx.finalizar_impressao(pedido_id, local, pago=pago,
                                              cozinha=self.ctx.cfg.imprimir_cozinha_automatico,
                                              cpf=dados.get("cpf_nota", ""))
        numero = resp.get("numero") or resp.get("codigo_local")
        offline = " (offline — será enviado ao voltar a internet)" if resp.get("offline") else ""
        troco = sum(max(0, (p.get("recebido_centavos") or 0) - p["valor_centavos"]) for p in pagos if p["forma"] == "DINHEIRO")
        self.ctx.status(f"Pedido {numero} lançado{offline}" + (f" — TROCO {reais(troco)}" if troco else "")
                        + ("  |  " + " | ".join(avisos) if avisos else ""))
        self.pedido_lancado.emit(resp)
        comanda = self.comanda
        self.limpar()
        if comanda is not None:
            self.comanda = None
            self._modo_alterado()
        return resp

    def limpar(self):
        if self.carrinho and self.sender() is not None and isinstance(self.sender(), QPushButton) \
                and self.sender().text() == "Limpar" and not confirmar(self, "Descartar o pedido atual?"):
            return
        self.carrinho.clear()
        for campo in (self.nome_balcao, self.senha, self.mesa_balcao, self.telefone, self.nome, self.logradouro,
                      self.numero, self.complemento, self.bairro, self.referencia, self.taxa, self.troco_para,
                      self.desconto, self.observacao, self.cpf, self.busca):
            campo.clear()
        self.enderecos.clear()
        self.cliente = None
        self._atualizar_carrinho()


class Separador(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.HLine)
