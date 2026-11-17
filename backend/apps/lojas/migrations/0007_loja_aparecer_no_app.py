from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lojas', '0006_fidelidade_mesa_whatsapp'),
    ]

    operations = [
        migrations.AddField(
            model_name='loja',
            name='aparecer_no_app',
            field=models.BooleanField(default=True, help_text='aparece na lista de restaurantes do app ApFood'),
        ),
    ]
