"""Janela principal do PDV e login."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import __version__
from ..api import ErroApi, SemConexao
from ..config import SERVIDOR_PADRAO, normalizar_servidor, recurso
from .alerta import AlertaSonoro
from .dialogos import DialogoEscolha
from .paginas.gestao import PaginaCaixa, PaginaConfig, PaginaCozinha, PaginaEstoque, PaginaRelatorios
from .paginas.mesas import PaginaMesas
from .paginas.pedidos import PaginaPedidos
from .paginas.venda import PaginaVenda
from .realtime import ClienteTempoReal


# =============================================================================


class DialogoLogin(QDialog):
    """Login do PDV (ou troca de operador por PIN)."""

    def __init__(self, ctx, parent=None, *, titulo="Entrar no ApFood", pin=False):
        super().__init__(parent)
        self.ctx, self.pin = ctx, pin
        self.setWindowTitle(titulo)
        self.setFixedWidth(440)
        externo = QVBoxLayout(self)
        externo.setContentsMargins(20, 20, 20, 16)

        logo = QLabel()
        imagem = QPixmap(str(recurso("logo.png")))
        if imagem.isNull():
            logo.setText("ApFood PDV")
            logo.setProperty("papel", "titulo")
        else:
            logo.setPixmap(imagem.scaledToHeight(84, Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignCenter)
        externo.addWidget(logo)
        sub = QLabel("Troque o operador com o PIN" if pin else "Acesse o caixa da sua loja")
        sub.setProperty("papel", "sutil")
        sub.setAlignment(Qt.AlignCenter)
        externo.addWidget(sub)
        externo.addSpacing(8)

        cartao = QFrame()
        cartao.setObjectName("cartaoLogin")
        v = QVBoxLayout(cartao)
        v.setContentsMargins(22, 16, 22, 20)
        v.setSpacing(4)

        def rotulo(texto):
            r = QLabel(texto)
            r.setProperty("papel", "rotulo")
            v.addWidget(r)

        self.usuario = QLineEdit(ctx.cfg.ultimo_usuario if not pin else "")
        self.usuario.setPlaceholderText("seu login")
        rotulo("Usuário")
        v.addWidget(self.usuario)
        self.senha = QLineEdit()
        self.senha.setEchoMode(QLineEdit.Password)
        self.senha.setPlaceholderText("PIN de 4 a 6 dígitos" if pin else "sua senha")
        rotulo("PIN" if pin else "Senha")
        linha_senha = QHBoxLayout()
        linha_senha.addWidget(self.senha, 1)
        self.btn_ver = QPushButton("Mostrar")
        self.btn_ver.setCheckable(True)
        self.btn_ver.setFocusPolicy(Qt.NoFocus)
        self.btn_ver.toggled.connect(self._mostrar_senha)
        linha_senha.addWidget(self.btn_ver)
        v.addLayout(linha_senha)

        self.servidor = QLineEdit(ctx.cfg.api_url)
        self.servidor.setPlaceholderText("https://apfood.axionwebdigital.com.br")
        self.box_servidor = QWidget()
        bs = QVBoxLayout(self.box_servidor)
        bs.setContentsMargins(0, 0, 0, 0)
        bs.setSpacing(4)
        r = QLabel("Servidor")
        r.setProperty("papel", "rotulo")
        bs.addWidget(r)
        bs.addWidget(self.servidor)
        v.addWidget(self.box_servidor)
        self.box_servidor.setVisible(False)

        self.msg = QLabel()
        self.msg.setProperty("papel", "erro")
        self.msg.setWordWrap(True)
        self.msg.setVisible(False)
        v.addSpacing(8)
        v.addWidget(self.msg)

        self.btn_entrar = QPushButton("Entrar")
        self.btn_entrar.setProperty("papel", "primario")
        self.btn_entrar.setMinimumHeight(46)
        self.btn_entrar.setDefault(True)
        self.btn_entrar.clicked.connect(self.entrar)
        v.addSpacing(6)
        v.addWidget(self.btn_entrar)
        externo.addWidget(cartao)

        rodape = QHBoxLayout()
        if not pin:
            self.lbl_servidor = QLabel()
            self.lbl_servidor.setProperty("papel", "sutil")
            rodape.addWidget(self.lbl_servidor, 1)
            alterar = QPushButton("alterar")
            alterar.setProperty("papel", "link")
            alterar.setCursor(Qt.PointingHandCursor)
            alterar.clicked.connect(self._editar_servidor)
            rodape.addWidget(alterar)
            esqueci = QPushButton("Esqueci a senha")
            esqueci.setProperty("papel", "link")
            esqueci.setCursor(Qt.PointingHandCursor)
            esqueci.clicked.connect(self._esqueci)
            rodape.addWidget(esqueci)
            self._atualizar_lbl_servidor()
        else:
            rodape.addStretch(1)
        cancelar = QPushButton("Sair" if not pin else "Cancelar")
        cancelar.clicked.connect(self.reject)
        rodape.addWidget(cancelar)
        externo.addLayout(rodape)
        versao = QLabel(f"versão {__version__}")
        versao.setProperty("papel", "sutil")
        versao.setAlignment(Qt.AlignRight)
        externo.addWidget(versao)

        (self.senha if self.usuario.text() else self.usuario).setFocus()

    def _mostrar_senha(self, ver: bool):
        self.senha.setEchoMode(QLineEdit.Normal if ver else QLineEdit.Password)
        self.btn_ver.setText("Ocultar" if ver else "Mostrar")

    def _atualizar_lbl_servidor(self):
        url = normalizar_servidor(self.servidor.text()) or SERVIDOR_PADRAO
        self.lbl_servidor.setText("Servidor: " + url.split("://", 1)[-1])

    def _editar_servidor(self):
        self.box_servidor.setVisible(not self.box_servidor.isVisible())
        if self.box_servidor.isVisible():
            self.servidor.setFocus()
            self.servidor.selectAll()
        self.adjustSize()

    def _esqueci(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        url = normalizar_servidor(self.servidor.text()) or SERVIDOR_PADRAO
        QDesktopServices.openUrl(QUrl(url + "/painel/senha/esqueci/"))

    def _erro(self, texto: str):
        self.msg.setText(texto)
        self.msg.setVisible(True)

    def entrar(self):
        usuario = self.usuario.text().strip()
        if not usuario or not self.senha.text():
            self._erro("Informe usuário e " + ("PIN." if self.pin else "senha."))
            return
        self.btn_entrar.setEnabled(False)
        self.btn_entrar.setText("Entrando…")
        QApplication.processEvents()
        try:
            if self.pin:
                u = self.ctx.api.trocar_operador(usuario, self.senha.text())
            else:
                url = normalizar_servidor(self.servidor.text()) or SERVIDOR_PADRAO
                if url != self.ctx.cfg.api_url:
                    self.ctx.cfg.api_url = self.ctx.api.base_url = url
                    self.ctx.cfg.salvar()
                    self._atualizar_lbl_servidor()
                u = self.ctx.api.login(usuario, self.senha.text())
        except SemConexao:
            self._erro("Não foi possível falar com o servidor. Confira a internet ou clique em \"alterar\".")
            return
        except ErroApi as e:
            self._erro("Usuário ou senha incorretos." if e.status in (400, 401) else e.mensagem)
            return
        finally:
            self.btn_entrar.setEnabled(True)
            self.btn_entrar.setText("Entrar")
        if not self.pin and usuario != self.ctx.cfg.ultimo_usuario:
            self.ctx.cfg.ultimo_usuario = usuario
            self.ctx.cfg.salvar()
        self.ctx.definir_usuario(u)
        if not self.ctx.escolher_loja(self):
            return
        self.accept()


# =============================================================================
class JanelaPrincipal(QMainWindow):
    MENU = [("Pedidos", "F1"), ("Novo pedido", "F3"), ("Delivery", "F4"), ("Mesas", "F6"), ("Caixa", "F8"),
            ("Cozinha", "F9"), ("Estoque", ""), ("Relatórios", ""), ("Configurações", ""), ("Trocar operador", "Ctrl+T")]

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(f"ApFood PDV {__version__}")
        self.resize(1366, 800)
        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        self.menu = QListWidget()
        self.menu.setObjectName("menu")
        self.menu.setFixedWidth(190)
        for nome, atalho in self.MENU:
            it = QListWidgetItem(f"{nome}   {atalho}".rstrip())
            self.menu.addItem(it)
        h.addWidget(self.menu)
        self.pilha = QStackedWidget()
        h.addWidget(self.pilha, 1)
        self.setCentralWidget(central)

        self.p_pedidos = PaginaPedidos(ctx)
        self.p_venda = PaginaVenda(ctx)
        self.p_mesas = PaginaMesas(ctx)
        self.p_caixa = PaginaCaixa(ctx)
        self.p_cozinha = PaginaCozinha(ctx)
        self.p_estoque = PaginaEstoque(ctx)
        self.p_relatorios = PaginaRelatorios(ctx)
        self.p_config = PaginaConfig(ctx)
        self.paginas = [self.p_pedidos, self.p_venda, self.p_venda, self.p_mesas, self.p_caixa, self.p_cozinha,
                        self.p_estoque, self.p_relatorios, self.p_config]
        for p in dict.fromkeys(self.paginas):
            self.pilha.addWidget(p)
        self.menu.currentRowChanged.connect(self.ir_para)
        for i, (_, atalho) in enumerate(self.MENU):
            if atalho:
                QShortcut(QKeySequence(atalho), self, activated=lambda i=i: self.menu.setCurrentRow(i))
        QShortcut(QKeySequence("F2"), self, activated=lambda: self.p_venda.busca.setFocus())

        # barra de status
        self.lbl_usuario, self.lbl_conexao, self.lbl_fila = QLabel(), QLabel(), QLabel()
        for w in (self.lbl_usuario, self.lbl_fila, self.lbl_conexao):
            self.statusBar().addPermanentWidget(w)
        ctx.ao_status = lambda m: self.statusBar().showMessage(m, 12000)
        self._atualizar_usuario()

        # integrações entre telas
        self.p_venda.pedido_lancado.connect(lambda *_: self.p_pedidos.atualizar())
        self.p_mesas.lancar_rodada.connect(self._rodada)
        self.p_pedidos.pendentes_mudou.connect(self._pendentes)
        ctx.ponte.estado_sync.connect(self._estado_sync)
        ctx.ponte.rejeitada.connect(self._rejeitada)

        # alerta e tempo real
        self.alerta = AlertaSonoro(self)
        self.alerta.ativo = ctx.cfg.som_novo_pedido
        self.tempo_real = ClienteTempoReal(self)
        self.tempo_real.evento.connect(self._evento)
        self.tempo_real.conectado.connect(lambda ok: self._conexao(ok, "tempo real"))
        # reserva: confere pedidos online pendentes mesmo fora da tela de pedidos
        self.vigia = QTimer(self)
        self.vigia.setInterval(20000)
        self.vigia.timeout.connect(self.p_pedidos.atualizar)
        self.menu.setCurrentRow(0)

    def iniciar_servicos(self):
        QTimer.singleShot(4000, self.verificar_atualizacao)
        self.ctx.iniciar_sync()
        if self.ctx.loja.get("id"):
            self.tempo_real.iniciar(self.ctx.cfg.ws_url, self.ctx.loja["id"], lambda: self.ctx.api.access)
        self.vigia.start()

    def verificar_atualizacao(self):
        from .. import atualizador

        try:
            at = atualizador.verificar(self.ctx.api)
        except Exception:  # noqa: BLE001 — sem internet/servidor antigo: tenta na próxima abertura
            return
        if at is None:
            return
        texto = (f"Há uma nova versão do PDV: {at.versao} (instalada: {__version__}).\n\n"
                 + ("Esta atualização é OBRIGATÓRIA." if at.obrigatoria else "Atualizar agora? Leva cerca de 1 minuto."))
        if not at.obrigatoria and QMessageBox.question(self, "Atualização", texto) != QMessageBox.Yes:
            return
        if at.obrigatoria:
            QMessageBox.information(self, "Atualização", texto)
        from .util import seguro

        self.ctx.status("Baixando atualização…")
        novo = seguro(self, atualizador.baixar, at)
        if novo is None:
            return
        if atualizador.aplicar(novo):
            self.ctx.status("Reiniciando para atualizar…")
            self._atualizando = True
            self.close()
        else:
            QMessageBox.information(self, "Atualização", f"Versão {at.versao} baixada em:\n{novo}\n"
                                                         "(rodando pelo código-fonte: atualize com git pull)")

    # ---------------------------------------------------------------- navegação
    def ir_para(self, linha: int):
        if linha == len(self.MENU) - 1:  # trocar operador
            self.trocar_operador()
            self.menu.blockSignals(True)
            self.menu.setCurrentRow(self.pilha.currentIndex())
            self.menu.blockSignals(False)
            return
        pagina = self.paginas[linha]
        self.pilha.setCurrentWidget(pagina)
        if pagina is self.p_venda:
            if linha == 2:
                self.p_venda.novo_delivery()
            elif self.p_venda.comanda is None:
                self.p_venda.grupo_modo.button(0).setChecked(True)
        if hasattr(pagina, "ao_mostrar"):
            pagina.ao_mostrar()

    def _rodada(self, comanda: dict):
        self.menu.blockSignals(True)
        self.menu.setCurrentRow(1)
        self.menu.blockSignals(False)
        self.pilha.setCurrentWidget(self.p_venda)
        self.p_venda.para_comanda(comanda)
        self.p_venda.ao_mostrar()

    def trocar_operador(self):
        d = DialogoLogin(self.ctx, self, titulo="Trocar operador (PIN)", pin=True)
        if d.exec():
            self._atualizar_usuario()
            self.ctx.status(f"Operador: {self.ctx.usuario.get('nome')}")
            self.p_caixa.atualizar()

    # ------------------------------------------------------------------ eventos
    def _evento(self, ev: dict):
        tipo = ev.get("tipo", "")
        if tipo == "pedido.novo" and ev.get("pedido", {}).get("status") == "PENDENTE":
            self.alerta.iniciar()
            self.raise_()
            self.activateWindow()
            self.ctx.status(f"NOVO PEDIDO ONLINE #{ev['pedido'].get('numero')} — {ev['pedido'].get('nome_cliente', '')}")
        if tipo.startswith("pedido."):
            self.p_pedidos.atualizar()
        elif tipo == "catalogo.alterado" and self.ctx.sync:
            self.ctx.sync.acordar()
        elif tipo == "estoque.alerta":
            p = ev.get("produto", {})
            self.ctx.status(f"Estoque baixo: {p.get('nome')} ({p.get('estoque_atual')})")
        elif tipo == "pagamento.confirmado":
            self.ctx.status("Pagamento Pix confirmado")
            self.p_pedidos.atualizar()

    def _pendentes(self, n: int):
        item = self.menu.item(0)
        item.setText(f"Pedidos ({n} novo{'s' if n > 1 else ''})   F1" if n else "Pedidos   F1")
        if n:
            self.alerta.iniciar()
        else:
            self.alerta.parar()

    def _estado_sync(self, online: bool, pendentes: int):
        self._conexao(online, "sync")
        self.lbl_fila.setText(f"  {pendentes} aguardando envio  " if pendentes else "")

    def _conexao(self, online: bool, origem: str):
        self.lbl_conexao.setText("  ● ONLINE  " if online else "  ● OFFLINE  ")
        self.lbl_conexao.setStyleSheet(f"color: {'#66BB6A' if online else '#EF5350'}; font-weight: 700;")

    def _rejeitada(self, op_id: str, operacao: str, erro: str):
        QMessageBox.warning(self, "Operação recusada pelo servidor",
                            f"Uma operação feita sem internet foi recusada ao sincronizar:\n\n{operacao}\n{erro}\n\n"
                            "Veja em Configurações → Operações recusadas.")

    def _atualizar_usuario(self):
        u, l_ = self.ctx.usuario, self.ctx.loja
        self.lbl_usuario.setText(f"  {u.get('nome', '')} ({u.get('papel', '').lower()}) — {l_.get('nome', '')}  ")

    def closeEvent(self, ev):
        turno = None
        try:
            turno = self.ctx.banco.ler("turno_atual")
        except Exception:  # noqa: BLE001
            pass
        pend = self.ctx.banco.total_pendentes()
        aviso = []
        if pend:
            aviso.append(f"{pend} operação(ões) ainda não enviada(s) ao servidor — serão enviadas na próxima abertura.")
        if turno:
            aviso.append("O caixa continua ABERTO.")
        if aviso and not getattr(self, "_atualizando", False) and \
                QMessageBox.question(self, "Sair", "\n".join(aviso) + "\n\nSair mesmo assim?") != QMessageBox.Yes:
            ev.ignore()
            return
        self.tempo_real.parar()
        if self.ctx.sync:
            self.ctx.sync.parar()
        super().closeEvent(ev)


def escolher_loja(ctx, parent) -> bool:
    lojas = ctx.usuario.get("lojas", [])
    if not lojas:
        QMessageBox.warning(parent, "ApFood", "Seu usuário não tem acesso a nenhuma loja.")
        return False
    loja = next((l_ for l_ in lojas if l_["id"] == ctx.cfg.loja_id), None)
    if loja is None:
        if len(lojas) == 1:
            loja = lojas[0]
        else:
            d = DialogoEscolha("Em qual loja este computador trabalha?", [(l_["nome"], l_) for l_ in lojas], parent)
            if not d.exec():
                return False
            loja = d.valor()
        ctx.cfg.loja_id = loja["id"]
        ctx.cfg.salvar()
    ctx.definir_loja(loja)
    return True


__all__ = ["DialogoLogin", "JanelaPrincipal", "escolher_loja", "Qt"]
