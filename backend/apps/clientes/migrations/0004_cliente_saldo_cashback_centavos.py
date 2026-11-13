from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0003_entregador_token_acesso'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='saldo_cashback_centavos',
            field=models.PositiveIntegerField(default=0, editable=False),
        ),
    ]
