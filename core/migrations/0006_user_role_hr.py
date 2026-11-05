from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_payment_confirmed_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('Student', 'Student'),
                    ('Admin', 'Admin'),
                    ('Finance', 'Finance Administrator'),
                    ('HR', 'Human Resources'),
                    ('Parent', 'Parent'),
                ],
                default='Student',
                max_length=20,
            ),
        ),
    ]