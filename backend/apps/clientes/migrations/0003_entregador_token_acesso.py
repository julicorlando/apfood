from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clientes', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='entregador',
            name='token_acesso',
            field=models.CharField(blank=True, db_index=True, editable=False, help_text='link do celular do entregador (/entrega/<token>/); gerar outro invalida o anterior', max_length=64),
        ),
    ]
