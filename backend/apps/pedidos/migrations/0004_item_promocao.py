from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0003_pedido_cashback'),
    ]

    operations = [
        migrations.AddField(
            model_name='itempedido',
            name='promocao',
            field=models.CharField(blank=True, help_text='promoção aplicada (snapshot)', max_length=80),
        ),
        migrations.AddField(
            model_name='itempedido',
            name='desconto_promocao_centavos',
            field=models.PositiveIntegerField(default=0, help_text='por unidade, já abatido do preço'),
        ),
    ]
