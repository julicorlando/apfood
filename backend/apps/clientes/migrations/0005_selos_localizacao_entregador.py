from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0004_cliente_saldo_cashback_centavos'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='selos',
            field=models.PositiveSmallIntegerField(default=0, editable=False, help_text='cartão fidelidade'),
        ),
        migrations.AddField(
            model_name='entregador',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=7, editable=False, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='entregador',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=7, editable=False, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='entregador',
            name='localizacao_em',
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
    ]
