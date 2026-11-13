from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import gestao, publico, relatorios, sync, views, webhooks

r = DefaultRouter()
for prefixo, vs in [
    ("setores", views.SetorViewSet), ("categorias", views.CategoriaViewSet), ("produtos", views.ProdutoViewSet),
    ("variacoes", views.VariacaoViewSet), ("grupos-adicionais", views.GrupoAdicionalViewSet),
    ("adicionais", views.AdicionalViewSet), ("clientes", views.ClienteViewSet), ("enderecos", views.EnderecoViewSet),
    ("zonas-entrega", views.ZonaViewSet), ("entregadores", views.EntregadorViewSet), ("mesas", views.MesaViewSet),
    ("fornecedores", views.FornecedorViewSet), ("cupons", views.CupomViewSet),
    ("categorias-despesa", views.CategoriaDespesaViewSet), ("taxas-pagamento", views.TaxaFormaPagamentoViewSet),
    ("despesas", views.DespesaViewSet), ("pedidos", views.PedidoViewSet), ("cozinha", views.CozinhaViewSet),
    ("turnos", views.TurnoViewSet), ("comandas", views.ComandaViewSet), ("estoque", views.EstoqueViewSet),
    ("compras", views.CompraViewSet), ("notas-fiscais", views.NotaFiscalViewSet),
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
    path("fiscal/configuracao/", gestao.ConfiguracaoFiscalView.as_view()),
    path("sync/pull/", sync.PullView.as_view()),
    path("sync/push/", sync.PushView.as_view()),
    path("relatorios/vendas/", relatorios.VendasView.as_view()),
    path("relatorios/curva-abc/", relatorios.CurvaABCView.as_view()),
    path("relatorios/fechamentos/", relatorios.FechamentosView.as_view()),
    path("relatorios/fluxo-caixa/", relatorios.FluxoCaixaView.as_view()),
    path("plataforma/resumo/", relatorios.PlataformaResumoView.as_view()),
    # público (cardápio digital)
    path("publico/lojas/<slug:slug>/", publico.CardapioPublicoView.as_view()),
    path("publico/lojas/<slug:slug>/taxa-entrega/", publico.TaxaEntregaPublicaView.as_view()),
    path("publico/lojas/<slug:slug>/pedidos/", publico.PedidoPublicoView.as_view()),
    path("publico/lojas/<slug:slug>/cupom/", publico.CupomPublicoView.as_view()),
    path("publico/pedidos/<str:token>/", publico.AcompanharPedidoView.as_view()),
    path("webhooks/mercadopago/plataforma/", webhooks.MercadoPagoPlataformaWebhook.as_view()),
    path("webhooks/mercadopago/<uuid:loja_id>/", webhooks.MercadoPagoLojaWebhook.as_view()),
    path("", include(r.urls)),
]
