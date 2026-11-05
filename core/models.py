from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from decimal import Decimal
from django.utils import timezone


class User(AbstractUser):
    ROLE_CHOICES = (
        ('Student', 'Student'),
        ('Admin', 'Admin'),
        ('Finance', 'Finance Administrator'),
        ('HR', 'Human Resources'),
        ('Parent', 'Parent'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='Student')
    student_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True)
    id_number = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    def __str__(self):
        if self.get_full_name():
            return f"{self.get_full_name()} ({self.student_number or self.username})"
        return self.username

    @property
    def is_student(self):
        return self.role == 'Student'
    @property
    def is_hr(self):
        return self.role == 'HR'

    @property
    def is_staff_member(self):
        return self.role in ('Admin', 'Finance') or self.is_superuser


class StudentProfile(models.Model):
    STUDY_MODE_CHOICES = (
        ('Full-Time', 'Full-Time'),
        ('Part-Time', 'Part-Time'),
        ('Distance', 'Distance Learning'),
    )
    STATUS_CHOICES = (
        ('Active', 'Active'),
        ('Inactive', 'Inactive'),
        ('Graduated', 'Graduated'),
        ('Suspended', 'Suspended'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    student_number = models.CharField(max_length=20, unique=True)
    programme = models.CharField(max_length=150, blank=True)
    qualification = models.CharField(max_length=150, blank=True, help_text="e.g. National Certificate (Vocational)")
    faculty = models.CharField(max_length=100, blank=True)
    campus = models.CharField(max_length=100, blank=True, default='Pretoria Campus')
    academic_year = models.PositiveIntegerField(default=2026)
    year_of_study = models.PositiveIntegerField(default=1)
    study_mode = models.CharField(max_length=20, choices=STUDY_MODE_CHOICES, default='Full-Time')
    enrollment_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    registration_date = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    province = models.CharField(max_length=50, blank=True)
    photo = models.ImageField(upload_to='student_photos/', blank=True, null=True)

    # Quick summary fields (kept for performance)
    total_fees = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    fees_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['student_number']

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.student_number})"

    @property
    def outstanding_balance(self):
        return self.total_fees - self.fees_paid

    def latest_statement(self):
        """Most recently uploaded statement whose outstanding amount was read."""
        return (
            self.fee_statements.filter(outstanding__isnull=False)
            .order_by('-uploaded_at', '-pk')
            .first()
        )

    def recalculate_balances(self):
        """
        Single source of truth for a student's totals.

        If the student has an uploaded fee statement, that statement is the
        OPENING balance (what the student owed on the day it was uploaded).
        From then on:

            total_fees = statement total   + fees added after the upload
            fees_paid  = statement paid    + payments confirmed after the upload
            outstanding = total_fees - fees_paid

        Without a statement it falls back to Fee records minus payments.
        """
        from django.db.models import Sum
        zero = Decimal('0.00')
        stmt = self.latest_statement()

        if stmt is not None:
            owed = stmt.outstanding
            if stmt.total_fees is not None:
                base_total = stmt.total_fees
                base_paid = base_total - owed          # keeps total - paid == owed
            else:
                base_total, base_paid = owed, zero

            cutoff = stmt.uploaded_at
            new_fees = self.fees.filter(created_at__gt=cutoff).aggregate(
                s=Sum('total_amount'))['s'] or zero
            new_paid = self.payments.filter(
                status='Confirmed', confirmed_at__gt=cutoff
            ).aggregate(s=Sum('amount'))['s'] or zero

            self.total_fees = base_total + new_fees
            self.fees_paid = base_paid + new_paid
        else:
            self.total_fees = self.fees.aggregate(s=Sum('total_amount'))['s'] or zero
            self.fees_paid = self.payments.filter(status='Confirmed').aggregate(
                s=Sum('amount'))['s'] or zero

        self.save(update_fields=['total_fees', 'fees_paid', 'updated_at'])

class FeeItem(models.Model):
    """Catalogue of possible fee types"""
    CATEGORY_CHOICES = (
        ('Tuition', 'Tuition Fees'),
        ('Other', 'Other Fees'),
    )
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='Other')
    description = models.TextField(blank=True)
    default_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Fee(models.Model):
    """
    A specific fee charged to a student (like the 'Fees' sheet in the original system).
    This is the billed amount.
    """
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Partial', 'Partially Paid'),
        ('Paid', 'Fully Paid'),
        ('Overdue', 'Overdue'),
        ('Waived', 'Waived'),
    )

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='fees')
    fee_item = models.ForeignKey(FeeItem, on_delete=models.SET_NULL, null=True, blank=True)
    academic_year = models.PositiveIntegerField(default=2026)
    description = models.CharField(max_length=200, blank=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    fine = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')

    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-due_date', '-created_at']

    def __str__(self):
        return f"{self.student.student_number} - {self.fee_item or self.description} (R{self.total_amount})"

    def save(self, *args, **kwargs):
        self.total_amount = self.amount - self.discount + self.fine
        self.remaining_amount = self.total_amount - self.paid_amount

        if self.remaining_amount <= 0:
            self.status = 'Paid'
        elif self.paid_amount > 0:
            self.status = 'Partial'
        elif self.due_date and self.due_date < timezone.now().date() and self.remaining_amount > 0:
            self.status = 'Overdue'
        else:
            self.status = 'Pending'

        super().save(*args, **kwargs)
    
    def refresh_paid(self):
        """Recompute paid_amount from confirmed payments (safe to call repeatedly)."""
        from django.db.models import Sum
        self.paid_amount = self.payments.filter(status='Confirmed').aggregate(
            s=Sum('amount'))['s'] or Decimal('0.00')
        self.save()

class Payment(models.Model):
    METHOD_CHOICES = (
        ('EFT', 'EFT / Online Banking'),
        ('Cash', 'Cash'),
        ('Card', 'Card Payment'),
        ('Bank Deposit', 'Bank Deposit'),
        ('NSFAS', 'NSFAS / Bursary'),
        ('Other', 'Other'),
    )
    STATUS_CHOICES = (
        ('Pending', 'Pending Verification'),
        ('Confirmed', 'Confirmed'),
        ('Rejected', 'Rejected'),
    )

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='payments')
    fee = models.ForeignKey(Fee, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='EFT')
    reference_number = models.CharField(max_length=50, blank=True)
    receipt_number = models.CharField(max_length=50, blank=True, unique=True, null=True)
    fee_item = models.ForeignKey(FeeItem, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    notes = models.TextField(blank=True)
    proof_of_payment = models.FileField(upload_to='proofs_of_payment/', blank=True, null=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)          # NEW
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='recorded_payments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-payment_date', '-created_at']

    def __str__(self):
        return f"{self.student.student_number} – R{self.amount} ({self.payment_date})"

    def save(self, *args, **kwargs):
        # NEW: remember when the payment was confirmed. The balance maths uses
        # this to subtract only payments made after the statement was uploaded.
        if self.status == 'Confirmed' and self.confirmed_at is None:
            self.confirmed_at = timezone.now()
        elif self.status != 'Confirmed':
            self.confirmed_at = None

        if not self.receipt_number and self.status == 'Confirmed':
            prefix = timezone.now().strftime('RCPT%y%m%d')
            last = Payment.objects.filter(receipt_number__startswith=prefix).count()
            self.receipt_number = f"{prefix}{last + 1:04d}"
        super().save(*args, **kwargs)


class FeeStatement(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='fee_statements')
    title = models.CharField(max_length=200)
    statement_file = models.FileField(upload_to='fee_statements/')
    statement_date = models.DateField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    # Populated automatically by reading the uploaded PDF (see core/pdf_utils.py)
    total_fees = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    fees_paid = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    outstanding = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    used_ocr = models.BooleanField(default=False)
    extraction_error = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.title} – {self.student.student_number}"


class ProofOfRegistration(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='registration_proofs')
    title = models.CharField(max_length=200, default='Proof of Registration')
    document = models.FileField(upload_to='registration_proofs/')
    academic_year = models.PositiveIntegerField(default=2026)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.title} – {self.student.student_number}"


class Notice(models.Model):
    """
    Shown in the 'Important Notices' panel on the student dashboard.
    Leave target_student blank to show it to every student.
    """
    LEVEL_CHOICES = (
        ('Info', 'Info'),
        ('Warning', 'Warning'),
        ('Urgent', 'Urgent'),
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='Info')
    target_student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, null=True, blank=True,
        related_name='notices',
        help_text="Leave blank to show this notice to all students."
    )
    due_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title
   # ─── Keep balances in sync automatically ─────────────────────────────
from django.db.models.signals import post_save, post_delete  # noqa: E402
from django.dispatch import receiver  # noqa: E402


@receiver(post_save, sender=Payment)
@receiver(post_delete, sender=Payment)
def _payment_changed(sender, instance, **kwargs):
    if instance.fee_id:
        fee = Fee.objects.filter(pk=instance.fee_id).first()
        if fee:
            fee.refresh_paid()
    student = StudentProfile.objects.filter(pk=instance.student_id).first()
    if student:
        student.recalculate_balances()


@receiver(post_save, sender=Fee)
@receiver(post_delete, sender=Fee)
@receiver(post_save, sender=FeeStatement)
@receiver(post_delete, sender=FeeStatement)
def _fee_or_statement_changed(sender, instance, **kwargs):
    student = StudentProfile.objects.filter(pk=instance.student_id).first()
    if student:
        student.recalculate_balances() 