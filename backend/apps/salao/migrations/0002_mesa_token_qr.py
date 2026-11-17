import secrets

from django.db import migrations, models


def preencher(apps, schema_editor):
    Mesa = apps.get_model("salao", "Mesa")
    for m in Mesa.objects.filter(token_qr__isnull=True):
        m.token_qr = secrets.token_urlsafe(12)
        m.save(update_fields=["token_qr"])


class Migration(migrations.Migration):

    dependencies = [
        ('salao', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='mesa',
            name='token_qr',
            field=models.CharField(blank=True, editable=False, help_text='QR Code da mesa (/<loja>/mesa/<token>/); gerar outro invalida o impresso', max_length=24, null=True, unique=True),
        ),
        migrations.RunPython(preencher, migrations.RunPython.noop),
    ]
