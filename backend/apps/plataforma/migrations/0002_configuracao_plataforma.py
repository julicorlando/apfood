import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('plataforma', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfiguracaoPlataforma',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('criado_em', models.DateTimeField(auto_now_add=True, verbose_name='criado em')),
                ('atualizado_em', models.DateTimeField(auto_now=True, db_index=True, verbose_name='atualizado em')),
                ('mp_token_cifrado', models.TextField(blank=True, editable=False)),
                ('mp_conta', models.CharField(blank=True, help_text='conta conferida no Mercado Pago', max_length=120)),
                ('metodo', models.CharField(choices=[('PIX', 'Só Pix (QR Code)'), ('CHECKOUT', 'Página do Mercado Pago: Pix, cartão e boleto')], default='CHECKOUT', max_length=10)),
            ],
            options={
                'verbose_name': 'configuração da plataforma',
                'db_table': 'configuracao_plataforma',
            },
        ),
    ]
