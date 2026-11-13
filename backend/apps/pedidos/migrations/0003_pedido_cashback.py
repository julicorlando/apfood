from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pedidos', '0002_pagamento_dados_externos'),
    ]

    operations = [
        migrations.AddField(
            model_name='pedido',
            name='cashback_usado_centavos',
            field=models.PositiveIntegerField(default=0, help_text='saldo do cliente usado como desconto'),
        ),
        migrations.AddField(
            model_name='pedido',
            name='cashback_gerado_centavos',
            field=models.PositiveIntegerField(default=0, help_text='creditado ao cliente na conclusão'),
        ),
    ]
