import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0004_cliente_saldo_cashback_centavos'),
        ('lojas', '0005_loja_cashback_percentual'),
        ('marketing', '0002_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Campanha',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('criado_em', models.DateTimeField(auto_now_add=True, verbose_name='criado em')),
                ('atualizado_em', models.DateTimeField(auto_now=True, db_index=True, verbose_name='atualizado em')),
                ('nome', models.CharField(max_length=80)),
                ('mensagem', models.TextField(help_text='use {nome}, {loja}, {cashback} e {link}')),
                ('publico', models.CharField(choices=[('MARKETING', 'Todos que aceitam promoções'), ('CASHBACK', 'Quem tem saldo de cashback'), ('INATIVOS', 'Quem não compra há X dias')], default='MARKETING', max_length=12)),
                ('dias_inativo', models.PositiveSmallIntegerField(default=30)),
                ('status', models.CharField(choices=[('RASCUNHO', 'Rascunho'), ('ENVIANDO', 'Enviando'), ('CONCLUIDA', 'Concluída')], default='RASCUNHO', max_length=10)),
                ('total', models.PositiveIntegerField(default=0)),
                ('enviados', models.PositiveIntegerField(default=0)),
                ('falhas', models.PositiveIntegerField(default=0)),
                ('iniciada_em', models.DateTimeField(blank=True, null=True)),
                ('concluida_em', models.DateTimeField(blank=True, null=True)),
                ('criado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('loja', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='lojas.loja')),
            ],
            options={
                'db_table': 'campanhas',
                'ordering': ['-criado_em'],
            },
        ),
        migrations.CreateModel(
            name='EnvioCampanha',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('criado_em', models.DateTimeField(auto_now_add=True, verbose_name='criado em')),
                ('atualizado_em', models.DateTimeField(auto_now=True, db_index=True, verbose_name='atualizado em')),
                ('telefone', models.CharField(max_length=13)),
                ('texto', models.TextField()),
                ('status', models.CharField(default='PENDENTE', max_length=8)),
                ('erro', models.CharField(blank=True, max_length=255)),
                ('campanha', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='envios', to='marketing.campanha')),
                ('cliente', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='clientes.cliente')),
            ],
            options={
                'db_table': 'campanhas_envios',
                'constraints': [models.UniqueConstraint(fields=('campanha', 'telefone'), name='envio_unico_por_telefone')],
            },
        ),
    ]
