
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lojas', '0004_alter_operacaosincronizada_resultado'),
    ]

    operations = [
        migrations.AddField(
            model_name='loja',
            name='cashback_percentual',
            field=models.DecimalField(decimal_places=2, default=0, help_text='% do pedido concluído que volta como saldo para o cliente (0 = desligado)', max_digits=5),
        ),
    ]
