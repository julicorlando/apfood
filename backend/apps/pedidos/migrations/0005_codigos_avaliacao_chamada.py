import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

from apps.pedidos.models import gerar_codigo


def codigos_diferentes(apps, schema_editor):
    """Pedidos em andamento ganham códigos próprios (o AddField usa um só valor para todos)."""
    Pedido = apps.get_model("pedidos", "Pedido")
    for p in Pedido.objects.exclude(status__in=["CONCLUIDO", "CANCELADO", "RECUSADO"]).only("id"):
        Pedido.objects.filter(pk=p.pk).update(codigo_retirada=gerar_codigo(), codigo_entrega=gerar_codigo())


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0004_item_promocao'),
        ('clientes', '0006_entregador_app'),
        ('lojas', '0007_loja_aparecer_no_app'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name='pedido', name='codigo_retirada',
                            field=models.CharField(default=gerar_codigo, editable=False, max_length=4)),
        migrations.AddField(model_name='pedido', name='codigo_entrega',
                            field=models.CharField(default=gerar_codigo, editable=False, max_length=4)),
        migrations.RunPython(codigos_diferentes, migrations.RunPython.noop),
        migrations.CreateModel(
            name='Avaliacao',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('criado_em', models.DateTimeField(auto_now_add=True, verbose_name='criado em')),
                ('atualizado_em', models.DateTimeField(auto_now=True, db_index=True, verbose_name='atualizado em')),
                ('nota', models.PositiveSmallIntegerField()),
                ('comentario', models.CharField(blank=True, max_length=500)),
                ('loja', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='lojas.loja')),
                ('pedido', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='avaliacao', to='pedidos.pedido')),
            ],
            options={'db_table': 'avaliacoes', 'ordering': ['-criado_em'],
                     'indexes': [models.Index(fields=['loja', 'criado_em'], name='avaliacoes_loja_id_6c1b0e_idx')]},
        ),
        migrations.CreateModel(
            name='ChamadaEntrega',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('criado_em', models.DateTimeField(auto_now_add=True, verbose_name='criado em')),
                ('atualizado_em', models.DateTimeField(auto_now=True, db_index=True, verbose_name='atualizado em')),
                ('status', models.CharField(choices=[('PROCURANDO', 'Procurando'), ('ACEITA', 'Aceita'), ('SEM_RESPOSTA', 'Ninguém aceitou'), ('CANCELADA', 'Cancelada')], default='PROCURANDO', max_length=20)),
                ('expira_em', models.DateTimeField()),
                ('oferta_ate', models.DateTimeField(blank=True, null=True)),
                ('ofertados', models.JSONField(blank=True, default=list, help_text='ids na ordem em que receberam a oferta')),
                ('recusados', models.JSONField(blank=True, default=list)),
                ('aceita_em', models.DateTimeField(blank=True, null=True)),
                ('loja', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='lojas.loja')),
                ('pedido', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chamadas', to='pedidos.pedido')),
                ('entregador_atual', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='clientes.entregador')),
                ('aceita_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='clientes.entregador')),
                ('criado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'db_table': 'chamadas_entrega', 'ordering': ['-criado_em'],
                     'indexes': [models.Index(fields=['status', 'loja'], name='chamadas_en_status_9f3a21_idx')]},
        ),
    ]
