"""Objetos compartilhados pelas telas: config, API, banco local, operações,
sincronização e impressão."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from apfood_core import cupom

from ..api import ApiClient, SemConexao
from ..config import Config
from ..impressao import ErroImpressao, imprimir
from ..local_db import BancoLocal
from ..operacoes import PDV
from ..sync import Sincronizador, SyncWorker


class Ponte(QObject):
    """Leva avisos da thread de sincronização para a interface."""

    estado_sync = Signal(bool, int)
    rejeitada = Signal(str, str, str)


class Contexto:
    def __init__(self, cfg: Config, api: ApiClient, banco: BancoLocal):
        self.cfg, self.api, self.banco = cfg, api, banco
        self.pdv = PDV(api, banco, terminal=cfg.nome_terminal.replace(" ", "")[:4].upper() or "C1")
        self.usuario: dict = {}
        self.ponte = Ponte()
        self.sincronizador = Sincronizador(banco, api)
        self.sincronizador.ao_rejeitar = lambda i, op, e: self.ponte.rejeitada.emit(i, op, e)
        api.ao_renovar = lambda a, r: banco.gravar("tokens", {"access": a, "refresh": r})
        self.sync: SyncWorker | None = None
        self.loja: dict = {}
        self.ao_status = None  # callback da barra de status (janela principal)

    def status(self, mensagem: str) -> None:
        if self.ao_status:
            self.ao_status(mensagem)

    # --- sessão -----------------------------------------------------------------
    def restaurar_sessao(self) -> bool:
        """Reaproveita tokens salvos. Sem internet, entra com o último usuário (modo offline)."""
        tokens = self.banco.ler("tokens") or {}
        if not tokens.get("refresh"):
            return False
        self.api.access, self.api.refresh = tokens.get("access", ""), tokens["refresh"]
        self.api.loja_id = self.cfg.loja_id
        try:
            self.definir_usuario(self.api.eu())
        except SemConexao:
            if not (u := self.banco.ler("usuario")):
                return False
            self.usuario = u
        except Exception:  # noqa: BLE001 — token expirado/inválido
            return False
        loja = next((l_ for l_ in self.usuario.get("lojas", []) if l_["id"] == self.cfg.loja_id), None)
        if loja is None:
            return False
        self.definir_loja(loja)
        return True

    def definir_usuario(self, usuario: dict) -> None:
        self.usuario = usuario
        self.banco.gravar("usuario", usuario)
        self.banco.gravar("tokens", {"access": self.api.access, "refresh": self.api.refresh})

    def definir_loja(self, loja: dict) -> None:
        self.loja = loja
        self.api.loja_id = loja["id"]
        self.banco.gravar("loja", loja)

    def escolher_loja(self, parent) -> bool:
        from .janela import escolher_loja

        return escolher_loja(self, parent)

    def sair(self) -> None:
        self.banco.gravar("tokens", None)
        self.api.access = self.api.refresh = ""

    def iniciar_sync(self):
        self.sync = SyncWorker(self.sincronizador, self.cfg.intervalo_sync_s,
                               ao_mudar_estado=lambda on, n: self.ponte.estado_sync.emit(on, n))
        self.pdv.ao_enfileirar = self.sync.acordar
        self.sync.start()

    @property
    def eh_gerente(self) -> bool:
        return self.usuario.get("papel") in ("MASTER", "ADMIN", "GERENTE")

    # --- impressão ------------------------------------------------------------
    def imprimir(self, linhas, destino: str | None = None, *, gaveta: bool = False) -> str:
        destino = destino or self.cfg.impressora_caixa
        if not destino:
            raise ErroImpressao("configure a impressora do caixa em Configurações")
        return imprimir(destino, linhas, largura=self.cfg.largura_bobina, abrir_gaveta=gaveta)

    def imprimir_venda(self, pedido_id: str, *, cpf: str = "", gaveta: bool = False) -> dict:
        """NFC-e (se a loja tiver emissor) ou comprovante não fiscal."""
        doc = self.api.post(f"/api/pedidos/{pedido_id}/documento/", {"cpf": cpf, "largura": self.cfg.largura_bobina})
        if doc.get("linhas"):  # DANFE NFC-e (autorizada) ou comprovante NÃO FISCAL
            self.imprimir(doc["linhas"], gaveta=gaveta)
        return doc

    def imprimir_cozinha(self, pedido_id: str) -> int:
        vias = self.api.get(f"/api/pedidos/{pedido_id}/cupom/", tipo="cozinha", largura=self.cfg.largura_bobina)["vias"]
        for v in vias:
            imprimir(v["impressora"] or self.cfg.impressora_cozinha_padrao or self.cfg.impressora_caixa, v["linhas"],
                     largura=self.cfg.largura_bobina)
        return len(vias)

    # --- impressão local (sem internet): mesmo layout, sempre NÃO FISCAL ----
    def loja_para_cupom(self) -> dict:
        return {"nome": self.loja.get("nome", ""), "cnpj": self.loja.get("cnpj", ""),
                "telefone": self.loja.get("telefone", ""), "endereco": self.loja.get("endereco", "")}

    def impressora_do_setor(self, setor_nome: str) -> str:
        for s_ in self.banco.listar("setores"):
            if s_.get("nome") == setor_nome and s_.get("impressora"):
                return s_["impressora"]
        return self.cfg.impressora_cozinha_padrao or self.cfg.impressora_caixa

    def imprimir_venda_local(self, pedido: dict, *, gaveta: bool = False) -> str:
        return self.imprimir(cupom.comprovante_venda(pedido, self.loja_para_cupom(), self.cfg.largura_bobina),
                             gaveta=gaveta)

    def imprimir_cozinha_local(self, pedido: dict) -> int:
        grupos: dict[str, list] = {}
        for i in pedido.get("itens", []):
            grupos.setdefault(i.get("setor") or "", []).append(i)
        for setor, itens in grupos.items():
            imprimir(self.impressora_do_setor(setor), cupom.cupom_cozinha({**pedido, "itens": itens}, setor or "Cozinha",
                                                                       self.cfg.largura_bobina),
                     largura=self.cfg.largura_bobina)
        return len(grupos)

    def finalizar_impressao(self, pedido_id: str, pedido_local: dict, *, pago: bool, cozinha: bool,
                            cpf: str = "") -> list[str]:
        """Após lançar a venda: cozinha (por setor) + documento do cliente.
        Online → NFC-e se houver emissor, senão não fiscal. Offline → não fiscal local.
        Devolve avisos (impressora fora, NFC-e rejeitada...) sem travar a venda."""
        avisos = []
        try:
            if cozinha:
                try:
                    self.imprimir_cozinha(pedido_id)
                except SemConexao:
                    self.imprimir_cozinha_local(pedido_local)
            if pago:
                try:
                    doc = self.imprimir_venda(pedido_id, cpf=cpf, gaveta=True)
                    if doc.get("aviso"):
                        avisos.append(doc["aviso"])
                    if doc.get("tipo") == "NFCE":
                        avisos.append(f"NFC-e {doc['nota'].get('numero') or ''} {doc['nota'].get('status', '').lower()}")
                except SemConexao:
                    self.imprimir_venda_local(pedido_local, gaveta=True)
                    avisos.append("Sem internet: impresso comprovante NÃO FISCAL")
        except ErroImpressao as e:
            avisos.append(f"Impressão: {e}")
        except Exception as e:  # noqa: BLE001 — impressão nunca derruba a venda
            avisos.append(f"Impressão: {e}")
        return avisos
