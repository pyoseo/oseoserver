# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-02-20 17:45
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('oseoserver', '0002_auto_20170220_1610'),
    ]

    operations = [
        migrations.AddField(
            model_name='batch',
            name='additional_status_info',
            field=models.TextField(blank=True, help_text='Additional information about the status'),
        ),
    ]
