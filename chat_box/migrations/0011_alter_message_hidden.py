# Generated by Django 3.2.18 on 2023-02-18 21:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("chat_box", "0010_auto_20221028_0300"),
    ]

    operations = [
        migrations.AlterField(
            model_name="message",
            name="hidden",
            field=models.BooleanField(
                db_index=True, default=False, verbose_name="is hidden"
            ),
        ),
    ]