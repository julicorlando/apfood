from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0005_selos_localizacao_entregador'),
    ]

    operations = [
        migrations.AddField(model_name='entregador', name='pin_hash',
                            field=models.CharField(blank=True, editable=False, max_length=128)),
        migrations.AddField(model_name='entregador', name='pin_trocado',
                            field=models.BooleanField(default=False, editable=False, help_text='o entregador já trocou o PIN inicial')),
        migrations.AddField(model_name='entregador', name='online',
                            field=models.BooleanField(default=False, editable=False, help_text='disponível no app')),
        migrations.AddField(model_name='entregador', name='online_em',
                            field=models.DateTimeField(blank=True, editable=False, null=True)),
        migrations.AddField(model_name='entregador', name='remuneracao',
                            field=models.CharField(choices=[('TAXA', 'Recebe a taxa de entrega'), ('FIXO', 'Valor fixo por entrega'), ('NENHUM', 'Não mostrar')], default='TAXA', max_length=10)),
        migrations.AddField(model_name='entregador', name='valor_por_entrega_centavos',
                            field=models.PositiveIntegerField(default=0)),
    ]
