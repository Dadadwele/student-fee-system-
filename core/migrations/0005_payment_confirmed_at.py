from django.db import migrations, models
from django.db.models import F


def backfill_confirmed_at(apps, schema_editor):
    Payment = apps.get_model('core', 'Payment')
    Payment.objects.filter(status='Confirmed', confirmed_at__isnull=True).update(
        confirmed_at=F('updated_at')
    )


def recalc_all(apps, schema_editor):
    """Re-run the balance maths once so existing students get correct totals."""
    from django.db.models import Sum
    from decimal import Decimal
    StudentProfile = apps.get_model('core', 'StudentProfile')
    Fee = apps.get_model('core', 'Fee')
    Payment = apps.get_model('core', 'Payment')
    FeeStatement = apps.get_model('core', 'FeeStatement')
    zero = Decimal('0.00')

    for sp in StudentProfile.objects.all():
        stmt = (FeeStatement.objects.filter(student=sp, outstanding__isnull=False)
                .order_by('-uploaded_at', '-pk').first())
        if stmt:
            owed = stmt.outstanding
            base_total = stmt.total_fees if stmt.total_fees is not None else owed
            base_paid = base_total - owed
            new_fees = Fee.objects.filter(student=sp, created_at__gt=stmt.uploaded_at).aggregate(
                s=Sum('total_amount'))['s'] or zero
            new_paid = Payment.objects.filter(
                student=sp, status='Confirmed', confirmed_at__gt=stmt.uploaded_at
            ).aggregate(s=Sum('amount'))['s'] or zero
            sp.total_fees = base_total + new_fees
            sp.fees_paid = base_paid + new_paid
        else:
            sp.total_fees = Fee.objects.filter(student=sp).aggregate(s=Sum('total_amount'))['s'] or zero
            sp.fees_paid = Payment.objects.filter(student=sp, status='Confirmed').aggregate(
                s=Sum('amount'))['s'] or zero
        sp.save(update_fields=['total_fees', 'fees_paid'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_dashboard_fields_and_notice'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='confirmed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_confirmed_at, migrations.RunPython.noop),
        migrations.RunPython(recalc_all, migrations.RunPython.noop),
    ]