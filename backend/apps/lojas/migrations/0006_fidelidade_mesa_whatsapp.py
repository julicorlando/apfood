from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lojas', '0005_loja_cashback_percentual'),
    ]

    operations = [
        migrations.AddField(
            model_name='loja',
            name='fidelidade_selos',
            field=models.PositiveSmallIntegerField(default=0, help_text='pedidos para completar o cartão (0 = desligado)'),
        ),
        migrations.AddField(
            model_name='loja',
            name='fidelidade_pedido_minimo_centavos',
            field=models.PositiveIntegerField(default=0, help_text='valor mínimo do pedido para ganhar um selo'),
        ),
        migrations.AddField(
            model_name='loja',
            name='fidelidade_premio_centavos',
            field=models.PositiveIntegerField(default=0, help_text='crédito que o cliente ganha ao completar o cartão'),
        ),
        migrations.AddField(
            model_name='loja',
            name='fidelidade_premio_descricao',
            field=models.CharField(blank=True, help_text='"1 X-Burger grátis"', max_length=120),
        ),
        migrations.AddField(
            model_name='loja',
            name='pedido_na_mesa',
            field=models.BooleanField(default=True, help_text='cliente pede pelo QR Code da mesa'),
        ),
        migrations.AddField(
            model_name='loja',
            name='whatsapp_atendente',
            field=models.BooleanField(default=False, help_text='responde sozinho no WhatsApp'),
        ),
        migrations.AddField(
            model_name='loja',
            name='whatsapp_boas_vindas',
            field=models.TextField(blank=True, help_text='mensagem de abertura; use {loja} e {link}'),
        ),
    ]
