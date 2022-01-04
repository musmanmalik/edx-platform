# -*- coding: utf-8 -*-

import datetime

import django.utils.timezone
import model_utils.fields
from django.conf import settings
from django.db import migrations, models
from django.utils.timezone import utc

from lms.djangoapps.certificates.models import template_assets_path
from opaque_keys.edx.django.models import CourseKeyField


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('instructor_task', '0001_initial'),
        ('certificates', '0003_data__default_modes'),
    ]

    operations = [
        migrations.AddField(
            model_name='certificatewhitelist',
            name='created',
            field=model_utils.fields.AutoCreatedField(default=datetime.datetime(2016, 9, 15, 6, 54, 3, 634153, tzinfo=utc), verbose_name='created', editable=False),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='certificatewhitelist',
            name='notes',
            field=models.TextField(default=None, null=True),
        ),

        migrations.CreateModel(
            name='CertificateGenerationHistory',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, verbose_name='created', editable=False)),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, verbose_name='modified', editable=False)),
                ('course_id', CourseKeyField(max_length=255)),
                ('is_regeneration', models.BooleanField(default=False)),
                ('generated_by', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE)),
                ('instructor_task', models.ForeignKey(to='instructor_task.InstructorTask', on_delete=models.CASCADE)),
            ],
        ),
        migrations.CreateModel(
            name='CertificateTemplate',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, verbose_name='created', editable=False)),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, verbose_name='modified', editable=False)),
                ('name', models.CharField(help_text='Name of template.', max_length=255)),
                ('description', models.CharField(help_text='Description and/or admin notes.', max_length=255, null=True, blank=True)),
                ('template', models.TextField(help_text='Django template HTML.')),
                ('organization_id', models.IntegerField(help_text='Organization of template.', null=True, db_index=True, blank=True)),
                ('course_key', CourseKeyField(db_index=True, max_length=255, null=True, blank=True)),
                ('mode', models.CharField(default=b'honor', choices=[(b'verified', b'verified'), (b'honor', b'honor'), (b'audit', b'audit'), (b'professional', b'professional'), (b'no-id-professional', b'no-id-professional')], max_length=125, blank=True, help_text='The course mode for this template.', null=True)),
                ('is_active', models.BooleanField(default=False, help_text='On/Off switch.')),
            ],
            options={
                'get_latest_by': 'created',
            },
        ),
        migrations.CreateModel(
            name='CertificateTemplateAsset',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, verbose_name='created', editable=False)),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, verbose_name='modified', editable=False)),
                ('description', models.CharField(help_text='Description of the asset.', max_length=255, null=True, blank=True)),
                ('asset', models.FileField(help_text='Asset file. It could be an image or css file.', max_length=255, upload_to=template_assets_path)),
            ],
            options={
                'get_latest_by': 'created',
            },
        ),
        migrations.AlterUniqueTogether(
            name='certificatetemplate',
            unique_together=set([('organization_id', 'course_key', 'mode')]),
        ),

    ]
