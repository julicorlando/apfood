import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lojas', '0005_loja_cashback_percentual'),
        ('marketing', '0003_campanhas'),
    ]

    operations = [
        migrations.CreateModel(
            name='Promocao',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('criado_em', models.DateTimeField(auto_now_add=True, verbose_name='criado em')),
                ('atualizado_em', models.DateTimeField(auto_now=True, db_index=True, verbose_name='atualizado em')),
                ('excluido_em', models.DateTimeField(blank=True, null=True, verbose_name='excluído em')),
                ('nome', models.CharField(help_text='"Terça do hambúrguer"', max_length=80)),
                ('descricao', models.CharField(blank=True, help_text='aparece no cardápio online', max_length=160)),
                ('tipo', models.CharField(choices=[('PERCENTUAL', '% de desconto'), ('VALOR', 'R$ de desconto'), ('PRECO_FIXO', 'Preço fixo')], default='PERCENTUAL', max_length=10)),
                ('valor', models.PositiveIntegerField(help_text='% (PERCENTUAL) ou centavos (VALOR / PRECO_FIXO)')),
                ('produtos', models.JSONField(blank=True, default=list, help_text='ids; vazio + categorias vazio = cardápio todo')),
                ('categorias', models.JSONField(blank=True, default=list)),
                ('dias', models.JSONField(blank=True, default=list, help_text='0=segunda … 6=domingo; vazio = todos')),
                ('hora_inicio', models.TimeField(blank=True, null=True)),
                ('hora_fim', models.TimeField(blank=True, null=True)),
                ('data_inicio', models.DateField(blank=True, null=True)),
                ('data_fim', models.DateField(blank=True, null=True)),
                ('canais', models.JSONField(blank=True, default=list, help_text='vazio = todos; ou ["ONLINE", "BALCAO"]')),
                ('ativa', models.BooleanField(default=True)),
                ('loja', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='lojas.loja')),
            ],
            options={
                'verbose_name': 'promoção',
                'verbose_name_plural': 'promoções',
                'db_table': 'promocoes',
                'ordering': ['nome'],
            },
        ),
    ]
