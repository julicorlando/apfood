from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import entregador, gestao, publico, relatorios, sync, views, webhooks

r = DefaultRouter()
for prefixo, vs in [
    ("setores", views.SetorViewSet), ("categorias", views.CategoriaViewSet), ("produtos", views.ProdutoViewSet),
    ("variacoes", views.VariacaoViewSet), ("grupos-adicionais", views.GrupoAdicionalViewSet),
    ("adicionais", views.AdicionalViewSet), ("clientes", views.ClienteViewSet), ("enderecos", views.EnderecoViewSet),
    ("zonas-entrega", views.ZonaViewSet), ("entregadores", views.EntregadorViewSet), ("mesas", views.MesaViewSet),
    ("fornecedores", views.FornecedorViewSet), ("cupons", views.CupomViewSet), ("promocoes", views.PromocaoViewSet),
    ("categorias-despesa", views.CategoriaDespesaViewSet), ("taxas-pagamento", views.TaxaFormaPagamentoViewSet),
    ("despesas", views.DespesaViewSet), ("pedidos", views.PedidoViewSet), ("cozinha", views.CozinhaViewSet),
    ("turnos", views.TurnoViewSet), ("comandas", views.ComandaViewSet), ("estoque", views.EstoqueViewSet),
    ("compras", views.CompraViewSet), ("notas-fiscais", views.NotaFiscalViewSet), ("reservas", views.ReservaViewSet),
]:
    r.register(prefixo, vs, basename=prefixo)
for prefixo, vs in [
    ("lojas", gestao.LojaViewSet), ("empresas", gestao.EmpresaViewSet), ("usuarios", gestao.UsuarioViewSet),
    ("integracoes", gestao.IntegracaoViewSet), ("planos", gestao.PlanoViewSet), ("faturas", gestao.FaturaViewSet),
    ("campanhas", gestao.CampanhaViewSet),
]:
    r.register(prefixo, vs, basename=prefixo)

urlpatterns = [
    path("eu/", views.EuView.as_view()),
    path("auth/pin/", views.PinView.as_view()),
    path("pdv/versao/", views.VersaoPdvView.as_view()),
    path("taxa-entrega/", views.TaxaEntregaView.as_view()),
    path("enums/", gestao.EnumsView.as_view()),
    path("assinatura/", gestao.AssinaturaView.as_view()),
    path("whatsapp/", gestao.WhatsAppView.as_view()),
    path("plataforma/recebimentos/", gestao.RecebimentosView.as_view()),
    path("fiscal/configuracao/", gestao.ConfiguracaoFiscalView.as_view()),
    path("sync/pull/", sync.PullView.as_view()),
    path("sync/push/", sync.PushView.as_view()),
    path("relatorios/vendas/", relatorios.VendasView.as_view()),
    path("relatorios/curva-abc/", relatorios.CurvaABCView.as_view()),
    path("relatorios/cmv/", relatorios.CMVView.as_view()),
    path("relatorios/operadores/", relatorios.OperadoresView.as_view()),
    path("relatorios/avaliacoes/", relatorios.AvaliacoesView.as_view()),
    path("relatorios/garcons/", relatorios.GarconsView.as_view()),
    path("acertos-entregador/", relatorios.AcertoEntregadoresView.as_view()),
    path("acertos-entregador/<uuid:pk>/recibo/", relatorios.ReciboAcertoView.as_view()),
    path("repasses-entregador/", relatorios.RepassesEntregadorView.as_view()),
    # app ApFood Entregador
    path("entregador/entrar/", entregador.EntrarView.as_view()),
    path("entregador/pin/", entregador.PinView.as_view()),
    path("entregador/online/", entregador.OnlineView.as_view()),
    path("entregador/push/", entregador.PushView.as_view()),
    path("push/", gestao.PushView.as_view()),
    path("rede/", gestao.RedeView.as_view()),
    path("rede/replicar/", gestao.RedeReplicarView.as_view()),
    path("entregador/estado/", entregador.EstadoView.as_view()),
    path("entregador/historico/", entregador.HistoricoView.as_view()),
    path("entregador/ofertas/<uuid:chamada>/<str:acao>/", entregador.OfertaView.as_view()),
    path("entregador/entregas/<uuid:pedido>/<str:acao>/", entregador.EntregaView.as_view()),
    path("entregador/repasses/", entregador.RepasseView.as_view()),
    path("entregador/plantao/", entregador.PlantaoView.as_view()),
    path("relatorios/fechamentos/", relatorios.FechamentosView.as_view()),
    path("relatorios/fluxo-caixa/", relatorios.FluxoCaixaView.as_view()),
    path("plataforma/resumo/", relatorios.PlataformaResumoView.as_view()),
    # público (cardápio digital)
    path("publico/lojas/<slug:slug>/", publico.CardapioPublicoView.as_view()),
    path("publico/lojas/<slug:slug>/taxa-entrega/", publico.TaxaEntregaPublicaView.as_view()),
    path("publico/lojas/<slug:slug>/pedidos/", publico.PedidoPublicoView.as_view()),
    path("publico/lojas/<slug:slug>/cupom/", publico.CupomPublicoView.as_view()),
    path("publico/pedidos/<str:token>/", publico.AcompanharPedidoView.as_view()),
    path("publico/lojas/<slug:slug>/reservas/", publico.ReservaPublicaView.as_view()),
    path("publico/lojas/<slug:slug>/totem/<str:token>/pedidos/", publico.TotemPedidoView.as_view()),
    path("publico/lojas/", publico.LojasPublicasView.as_view()),
    path("publico/lojas/<slug:slug>/mesa/<str:token>/", publico.MesaPublicaView.as_view()),
    path("publico/lojas/<slug:slug>/mesa/<str:token>/pedidos/", publico.PedidoMesaView.as_view()),
    path("webhooks/mercadopago/plataforma/", webhooks.MercadoPagoPlataformaWebhook.as_view()),
    path("webhooks/whatsapp/<uuid:loja_id>/<str:chave>/", webhooks.WhatsAppWebhook.as_view()),
    path("webhooks/mercadopago/<uuid:loja_id>/", webhooks.MercadoPagoLojaWebhook.as_view()),
    path("", include(r.urls)),
]
