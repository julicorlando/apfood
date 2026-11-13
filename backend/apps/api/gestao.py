"""Gestão pela web: lojas, empresas, usuários, integrações, fiscal e planos.

Mesmas regras do admin do Django (apfood_core.permissoes):
  • MASTER vê e altera tudo; cadastra empresas, planos e faturas;
  • ADMIN gerencia a própria empresa: lojas (até o limite), usuários, integrações;
  • GERENTE gerencia operadores das lojas dele e abre/fecha a loja para pedidos;
  • OPERADOR só lê a própria loja.
"""

from apfood_core import permissoes
from apfood_core.enums import PapelUsuario
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contas.models import Usuario
from apps.core.api import EhAdmin, EhGerente, EscopoLojaMixin, UsuarioLiberado, loja_da_requisicao
from apps.fiscal.models import ConfiguracaoFiscal
from apps.integracoes.models import Integracao
from apps.lojas.models import Empresa, Loja
from apps.plataforma.models import Fatura, Plano

LEITURA = ("GET", "HEAD", "OPTIONS")


class AdminLeMasterAltera(EhAdmin):
    """ADMIN consulta; só o MASTER cria/altera."""

    message = "Somente o MASTER pode alterar."

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.method in LEITURA or request.user.eh_master


def _erros_django(exc: DjangoValidationError):
    return ValidationError(exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages})


# =============================================================================
# Lojas
# =============================================================================
SLUGS_RESERVADOS = {"admin", "api", "painel", "static", "media", "health", "pedido", "ws"}


class LojaGestaoSerializer(serializers.ModelSerializer):
    empresa_nome = serializers.CharField(source="empresa.nome", read_only=True)

    class Meta:
        model = Loja
        fields = "__all__"
        read_only_fields = ["id", "criado_em", "atualizado_em"]
        extra_kwargs = {"empresa": {"required": False}}

    def validate_slug(self, v):
        if v in SLUGS_RESERVADOS:
            raise serializers.ValidationError("endereço reservado pelo sistema, escolha outro")
        return v

    def validate_cor_primaria(self, v):
        if v and (len(v) != 7 or not v.startswith("#")):
            raise serializers.ValidationError("use o formato #RRGGBB")
        return v

    def validate_horarios(self, v):
        if v in (None, ""):
            return {}
        if not isinstance(v, (dict, list)):
            raise serializers.ValidationError("formato de horários inválido")
        return v


class LojaViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                  mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Todos leem as lojas que podem ver; ADMIN altera e cria (até o limite do plano)."""

    serializer_class = LojaGestaoSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]  # logo

    def get_permissions(self):
        if self.request.method in LEITURA or self.action == "pedidos_online":
            return [UsuarioLiberado()]
        return [EhAdmin()]

    def get_queryset(self):
        return self.request.user.lojas_permitidas().select_related("empresa").order_by("nome")

    def perform_create(self, serializer):
        u = self.request.user
        if u.eh_master:
            empresa = serializer.validated_data.get("empresa")
            if empresa is None:
                raise ValidationError({"empresa": ["informe a empresa"]})
        else:
            empresa = u.empresa
        if not permissoes.pode_criar_loja(u.acesso(), str(empresa.id), empresa.lojas.count(),
                                          empresa.limite_lojas_efetivo):
            raise PermissionDenied("limite de lojas do plano atingido")
        serializer.save(empresa=empresa)

    def perform_update(self, serializer):
        if not self.request.user.eh_master:
            serializer.validated_data.pop("empresa", None)  # ninguém muda a loja de empresa
        serializer.save()

    @action(detail=True, methods=["post"], url_path="pedidos-online")
    def pedidos_online(self, request, pk=None):
        """Gerente+ abre/fecha a loja para pedidos online: {"aberta": true}."""
        if not request.user.eh_gerente:
            raise PermissionDenied("requer gerente")
        loja = self.get_object()
        loja.aberta_para_pedidos = bool(request.data.get("aberta"))
        loja.save(update_fields=["aberta_para_pedidos", "atualizado_em"])
        return Response(self.get_serializer(loja).data)


# =============================================================================
# Empresas
# =============================================================================
CAMPOS_DO_MASTER = ["ativa", "motivo_bloqueio", "plano", "status_assinatura", "trial_ate", "dia_vencimento",
                    "limite_lojas", "limite_usuarios", "observacoes"]


class EmpresaSerializer(serializers.ModelSerializer):
    qtd_lojas = serializers.IntegerField(source="lojas.count", read_only=True)
    plano_nome = serializers.CharField(source="plano.nome", read_only=True, default=None)

    class Meta:
        model = Empresa
        fields = "__all__"
        read_only_fields = ["id", "criado_em", "atualizado_em"]

    def get_fields(self):
        campos = super().get_fields()
        request = self.context.get("request")
        if request is not None and not request.user.eh_master:
            for nome in CAMPOS_DO_MASTER:
                if nome in campos:
                    campos[nome].read_only = True
        return campos


class EmpresaViewSet(viewsets.ModelViewSet):
    """MASTER cadastra e bloqueia; ADMIN vê e edita os dados da própria empresa."""

    serializer_class = EmpresaSerializer
    permission_classes = [EhAdmin]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        u = self.request.user
        qs = Empresa.objects.select_related("plano").order_by("nome")
        return qs if u.eh_master else qs.filter(pk=u.empresa_id)

    def create(self, request, *args, **kwargs):
        if not permissoes.pode_cadastrar_empresa(request.user.acesso()):
            raise PermissionDenied("somente o MASTER cadastra empresas")
        return super().create(request, *args, **kwargs)

    @action(detail=False, methods=["post"])
    def onboarding(self, request):
        """MASTER cria empresa + primeira loja + usuário ADMIN de uma vez.
        {"empresa": {...}, "loja": {"nome", "slug"}, "admin": {"username", "password", "first_name", "email"}}"""
        if not permissoes.pode_cadastrar_empresa(request.user.acesso()):
            raise PermissionDenied("somente o MASTER cadastra empresas")
        d = request.data
        se = EmpresaSerializer(data=d.get("empresa") or {}, context={"request": request})
        sl = LojaGestaoSerializer(data=d.get("loja") or {})
        su = UsuarioGestaoSerializer(data={**(d.get("admin") or {}), "papel": PapelUsuario.ADMIN},
                                     context={"request": request, "onboarding": True})
        erros = {}
        for nome, ser in (("empresa", se), ("loja", sl), ("admin", su)):
            if not ser.is_valid():
                erros[nome] = ser.errors
        if erros:
            raise ValidationError(erros)
        with transaction.atomic():
            empresa = se.save()
            sl.save(empresa=empresa)
            su.save(empresa=empresa)
        return Response(EmpresaSerializer(empresa, context={"request": request}).data, status=status.HTTP_201_CREATED)


# =============================================================================
# Usuários
# =============================================================================
class UsuarioGestaoSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, min_length=6,
                                     style={"input_type": "password"})
    pin = serializers.CharField(write_only=True, required=False, allow_blank=True)
    tem_pin = serializers.SerializerMethodField()
    nome = serializers.CharField(source="__str__", read_only=True)
    empresa_nome = serializers.CharField(source="empresa.nome", read_only=True, default=None)

    class Meta:
        model = Usuario
        fields = ["id", "username", "nome", "first_name", "last_name", "email", "papel", "empresa", "empresa_nome",
                  "lojas", "is_active", "last_login", "date_joined", "password", "pin", "tem_pin"]
        read_only_fields = ["id", "last_login", "date_joined"]
        extra_kwargs = {"empresa": {"required": False, "allow_null": True}, "lojas": {"required": False}}

    def get_tem_pin(self, u):
        return bool(u.pin_hash)

    def validate_pin(self, v):
        if v and not (v.isdigit() and 4 <= len(v) <= 6):
            raise serializers.ValidationError("PIN deve ter de 4 a 6 dígitos")
        return v

    def validate(self, attrs):
        request = self.context["request"]
        eu = request.user
        alvo = self.instance
        if alvo is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": ["informe a senha"]})
        if self.context.get("onboarding"):
            return attrs  # empresa definida na view, papel ADMIN fixo
        papel = PapelUsuario(attrs.get("papel", alvo.papel if alvo else PapelUsuario.OPERADOR))
        if eu.eh_master:
            empresa = attrs.get("empresa", alvo.empresa if alvo else None)
        else:
            empresa = eu.empresa
            attrs.pop("empresa", None)
        if alvo is not None and alvo.pk == eu.pk:
            # ninguém se promove nem se desativa sozinho
            for campo in ("papel", "lojas", "is_active", "empresa"):
                attrs.pop(campo, None)
            return attrs
        empresa_id = str(empresa.id) if empresa else None
        if not permissoes.pode_gerenciar_usuario(eu.acesso(), papel, empresa_id):
            raise PermissionDenied("sem permissão para gerenciar este perfil")
        if alvo is not None and not permissoes.pode_gerenciar_usuario(
                eu.acesso(), PapelUsuario(alvo.papel), str(alvo.empresa_id) if alvo.empresa_id else None):
            raise PermissionDenied("sem permissão para alterar este usuário")
        try:
            permissoes.validar_vinculo(papel, empresa_id)
        except ValueError as exc:
            raise serializers.ValidationError({"empresa": [str(exc)]}) from exc
        lojas = attrs.get("lojas")
        if lojas:
            if any(str(l.empresa_id) != empresa_id for l in lojas):
                raise serializers.ValidationError({"lojas": ["loja de outra empresa"]})
            permitidas = set(eu.lojas_permitidas().values_list("id", flat=True))
            if any(l.id not in permitidas for l in lojas):
                raise serializers.ValidationError({"lojas": ["loja fora do seu acesso"]})
        if alvo is None and empresa is not None and not eu.eh_master:
            limite = empresa.limite_usuarios_efetivo
            if limite is not None and empresa.usuarios.filter(is_active=True).count() >= limite:
                raise PermissionDenied("limite de usuários do plano atingido")
        attrs["empresa"] = empresa
        return attrs

    def _aplicar(self, u, senha, pin):
        if senha:
            u.set_password(senha)
        if pin:
            u.definir_pin(pin)
        try:
            u.full_clean(exclude=["password"])
        except DjangoValidationError as exc:
            raise _erros_django(exc) from exc

    def create(self, dados):
        senha, pin, lojas = dados.pop("password", ""), dados.pop("pin", ""), dados.pop("lojas", None)
        u = Usuario(**dados)
        self._aplicar(u, senha, pin)
        u.save()
        if lojas is not None:
            u.lojas.set(lojas)
        return u

    def update(self, u, dados):
        senha, pin, lojas = dados.pop("password", ""), dados.pop("pin", ""), dados.pop("lojas", None)
        for k, v in dados.items():
            setattr(u, k, v)
        self._aplicar(u, senha, pin)
        u.save()
        if lojas is not None:
            u.lojas.set(lojas)
        return u


class UsuarioViewSet(viewsets.ModelViewSet):
    """Gerente+ gerencia quem está abaixo dele; excluir = desativar."""

    serializer_class = UsuarioGestaoSerializer
    permission_classes = [EhGerente]

    def get_queryset(self):
        u = self.request.user
        qs = Usuario.objects.select_related("empresa").prefetch_related("lojas").order_by("first_name", "username")
        if u.eh_master:
            if empresa := self.request.query_params.get("empresa"):
                qs = qs.filter(empresa_id=empresa)
            return qs
        visiveis = qs.filter(empresa_id=u.empresa_id, papel__in=permissoes.GERENCIA[PapelUsuario(u.papel)])
        return visiveis | qs.filter(pk=u.pk)

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            raise PermissionDenied("você não pode desativar a si mesmo")
        instance.is_active = False
        instance.save(update_fields=["is_active", "atualizado_em"])


# =============================================================================
# Integrações (credenciais cifradas, nunca devolvidas)
# =============================================================================
class IntegracaoSerializer(serializers.ModelSerializer):
    credenciais = serializers.DictField(write_only=True, required=False,
                                        help_text="segredos; ficam cifrados. Vazio = manter os atuais")
    tem_credenciais = serializers.SerializerMethodField()

    class Meta:
        model = Integracao
        exclude = ["loja", "credenciais_cifradas"]
        read_only_fields = ["id", "criado_em", "atualizado_em", "ultimo_sucesso_em", "ultimo_erro"]

    def get_tem_credenciais(self, obj):
        return bool(obj.credenciais_cifradas)

    def _salvar(self, obj, credenciais):
        if credenciais:
            obj.definir_credenciais({k: v for k, v in credenciais.items() if v not in (None, "")})
            obj.save(update_fields=["credenciais_cifradas", "atualizado_em"])
        return obj

    def create(self, dados):
        cred = dados.pop("credenciais", None)
        return self._salvar(super().create(dados), cred)

    def update(self, obj, dados):
        cred = dados.pop("credenciais", None)
        return self._salvar(super().update(obj, dados), cred)


class IntegracaoViewSet(EscopoLojaMixin, viewsets.ModelViewSet):
    queryset = Integracao.objects.all()
    serializer_class = IntegracaoSerializer
    permission_classes = [EhAdmin]
    filterset_fields = ["tipo", "ativo"]

    def perform_create(self, serializer):
        loja = self.get_loja()
        d = serializer.validated_data
        if Integracao.objects.filter(loja=loja, tipo=d["tipo"], provedor=d["provedor"]).exists():
            raise ValidationError({"provedor": ["já existe essa integração nesta loja"]})
        serializer.save(loja=loja)


# =============================================================================
# Configuração fiscal (uma por loja)
# =============================================================================
class ConfiguracaoFiscalSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracaoFiscal
        exclude = ["loja"]
        read_only_fields = ["id", "criado_em", "atualizado_em"]

    def validate_modelo_padrao(self, v):
        if v == "SAT":
            raise serializers.ValidationError("CF-e SAT está vedado em SP desde 01/01/2026 — use NFC-e.")
        return v


class ConfiguracaoFiscalView(APIView):
    permission_classes = [EhAdmin]

    def get(self, request):
        loja = loja_da_requisicao(request)
        cfg = ConfiguracaoFiscal.objects.filter(loja=loja).first() or ConfiguracaoFiscal(loja=loja)
        dados = ConfiguracaoFiscalSerializer(cfg).data
        if cfg._state.adding:
            dados["id"] = None
        return Response(dados)

    def put(self, request):
        loja = loja_da_requisicao(request)
        cfg = ConfiguracaoFiscal.objects.filter(loja=loja).first()
        ser = ConfiguracaoFiscalSerializer(cfg, data=request.data, partial=cfg is not None)
        ser.is_valid(raise_exception=True)
        ser.save(loja=loja)
        return Response(ser.data)


# =============================================================================
# Plataforma: planos e faturas
# =============================================================================
class PlanoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plano
        fields = "__all__"
        read_only_fields = ["id", "criado_em", "atualizado_em"]


class PlanoViewSet(viewsets.ModelViewSet):
    """ADMIN consulta; só o MASTER altera."""

    serializer_class = PlanoSerializer
    permission_classes = [AdminLeMasterAltera]
    queryset = Plano.objects.all()

    def perform_destroy(self, instance):
        instance.ativo = False
        instance.save(update_fields=["ativo", "atualizado_em"])


class FaturaSerializer(serializers.ModelSerializer):
    empresa_nome = serializers.CharField(source="empresa.nome", read_only=True)

    class Meta:
        model = Fatura
        fields = "__all__"
        read_only_fields = ["id", "criado_em", "atualizado_em"]


class FaturaViewSet(viewsets.ModelViewSet):
    serializer_class = FaturaSerializer
    permission_classes = [AdminLeMasterAltera]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    filterset_fields = ["status", "empresa"]

    def get_queryset(self):
        u = self.request.user
        qs = Fatura.objects.select_related("empresa")
        return qs if u.eh_master else qs.filter(empresa_id=u.empresa_id)


# =============================================================================
# Rótulos das enumerações (o painel mostra os mesmos nomes do backend)
# =============================================================================
class EnumsView(APIView):
    permission_classes = [UsuarioLiberado]

    def get(self, request):
        from apfood_core import enums

        dados = {}
        for nome in dir(enums):
            cls = getattr(enums, nome)
            if isinstance(cls, type) and issubclass(cls, enums._Rotulado) and cls is not enums._Rotulado:
                dados[nome] = [{"valor": v, "rotulo": r} for v, r in cls.choices()]
        return Response(dados)
