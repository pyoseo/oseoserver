# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-02-13 14:15
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('oseoserver', '0006_auto_20170213_1316'),
    ]

    operations = [
        migrations.AlterField(
            model_name='itemspecification',
            name='order',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='item_specifications', to='oseoserver.Order'),
        ),
    ]