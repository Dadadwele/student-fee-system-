from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Sum, Q, F
from django.utils import timezone
from decimal import Decimal

from .models import (
    User, StudentProfile, FeeStatement, ProofOfRegistration,
    Payment, FeeItem, Fee, Notice
)
from .forms import (
    RegisterForm, StudentProfileForm, FeeStatementForm,
    ProofOfRegistrationForm, PaymentForm, FeeForm, StudentPaymentForm,
    StaffCreationForm
)
from .pdf_utils import extract_fee_summary


def is_staff_member(user):
    return user.is_authenticated and (user.is_staff_member or user.is_superuser)


def is_hr_member(user):
    return user.is_authenticated and (user.is_hr or user.is_superuser)


# NEW: remembers the student picked in the search box, so the form can
# show them again if it comes back with a validation error.
def _selected_student(request):
    pk = request.POST.get('student', '')
    if pk.isdigit():
        return StudentProfile.objects.select_related('user').filter(pk=int(pk)).first()
    return None


def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Registration successful. Welcome!')
            return redirect('dashboard')
    else:
        form = RegisterForm()

    return render(request, 'registration/register.html', {'form': form})


def landing(request):
    """
    Root URL ('/'). Always send people through Login/Register first —
    only an already-authenticated session goes straight to the dashboard.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')


@login_required
def dashboard(request):
    # HR staff have their own home page (they do not handle student money)
    if request.user.is_hr and not request.user.is_superuser:
        return redirect('hr_dashboard')

    context = {'user': request.user}

    if request.user.is_student:
        try:
            profile = request.user.profile
        except StudentProfile.DoesNotExist:
            messages.warning(request, 'Please complete your student profile.')
            return redirect('edit_profile')

        today = timezone.now().date()
        year_fees = profile.fees.filter(academic_year=profile.academic_year)

        # "Due Now" — the closest fee that still has money owing on it
        due_now_fee = (
            year_fees.exclude(status='Paid')
            .exclude(status='Waived')
            .order_by('due_date')
            .first()
        )

        # "Total Paid (This Year)" — confirmed payments dated within the
        # student's current academic year
        total_paid_this_year = profile.payments.filter(
            status='Confirmed', payment_date__year=profile.academic_year
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

        # Fee breakdown, split the way the mockup shows it
        tuition_fees = year_fees.filter(fee_item__category='Tuition')
        other_fees = year_fees.exclude(fee_item__category='Tuition')
        tuition_subtotal = tuition_fees.aggregate(s=Sum('total_amount'))['s'] or Decimal('0.00')
        other_subtotal = other_fees.aggregate(s=Sum('total_amount'))['s'] or Decimal('0.00')

        # "Pay by Installments" — every fee line for this year, in due-date order,
        # each labelled Paid / Due / Upcoming
        installments = []
        for fee in year_fees.order_by('due_date'):
            if fee.status == 'Paid':
                label = 'Paid'
            elif fee.due_date and fee.due_date <= today:
                label = 'Due'
            else:
                label = 'Upcoming'
            installments.append({'fee': fee, 'label': label})

        # Donut chart percentages for "Account Overview"
        total_fees = profile.total_fees or Decimal('0.00')
        fees_paid = profile.fees_paid or Decimal('0.00')
        if total_fees > 0:
            paid_pct = max(0, min(100, round((fees_paid / total_fees) * 100)))
        else:
            paid_pct = 0
        outstanding_pct = 100 - paid_pct

        notices = Notice.objects.filter(is_active=True).filter(
            Q(target_student=profile) | Q(target_student__isnull=True)
        )[:6]

        recent_payments = profile.payments.filter(status='Confirmed')[:5]
        outstanding_fees = profile.fees.exclude(status='Paid')

        context.update({
            'profile': profile,
            'recent_payments': recent_payments,
            'outstanding_fees': outstanding_fees,
            'outstanding': profile.outstanding_balance,
            'due_now_fee': due_now_fee,
            'total_paid_this_year': total_paid_this_year,
            'tuition_fees': tuition_fees,
            'other_fees': other_fees,
            'tuition_subtotal': tuition_subtotal,
            'other_subtotal': other_subtotal,
            'total_fees_year': tuition_subtotal + other_subtotal,
            'installments': installments,
            'paid_pct': paid_pct,
            'outstanding_pct': outstanding_pct,
            'notices': notices,
        })
    else:
        total_students = StudentProfile.objects.count()
        agg = StudentProfile.objects.aggregate(billed=Sum('total_fees'), paid=Sum('fees_paid'))
        total_billed = agg['billed'] or Decimal('0')
        total_paid = agg['paid'] or Decimal('0')
        pending_payments = Payment.objects.filter(status='Pending').count()
        context.update({
            'total_students': total_students,
            'total_outstanding': total_billed - total_paid,
            'total_paid': total_paid,
            'pending_payments': pending_payments,
        })

    return render(request, 'dashboard.html', context)


@login_required
def profile_view(request):
    try:
        profile = request.user.profile
    except StudentProfile.DoesNotExist:
        profile = None
    return render(request, 'profile.html', {'profile': profile})


@login_required
def edit_profile(request):
    try:
        profile = request.user.profile
    except StudentProfile.DoesNotExist:
        profile = StudentProfile(
            user=request.user,
            student_number=request.user.student_number or request.user.username
        )
        profile.save()

    if request.method == 'POST':
        form = StudentProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')
    else:
        form = StudentProfileForm(instance=profile)

    return render(request, 'edit_profile.html', {'form': form})


@login_required
def upload_statement(request):
    try:
        profile = request.user.profile
    except StudentProfile.DoesNotExist:
        messages.error(request, 'Complete your profile first.')
        return redirect('edit_profile')

    if request.method == 'POST':
        form = FeeStatementForm(request.POST, request.FILES)
        if form.is_valid():
            statement = form.save(commit=False)
            statement.student = profile
            statement.save()  # save first so the file exists on disk with a real path

            # Read the PDF that was just uploaded and pull the fee summary
            # out of it, so the numbers show up on the page immediately.
            summary = extract_fee_summary(statement.statement_file.path)
            statement.total_fees = summary['total_fees']
            statement.fees_paid = summary['fees_paid']
            statement.outstanding = summary['outstanding']
            statement.used_ocr = summary['used_ocr']
            statement.extraction_error = summary['error'] or ''
            statement.save(update_fields=[
                'total_fees', 'fees_paid', 'outstanding',
                'used_ocr', 'extraction_error',
            ])  # post_save signal recalculates the student's balance here

            if summary['error']:
                messages.warning(
                    request,
                    f"Statement uploaded, but the amounts could not be read automatically: {summary['error']}"
                )
            elif summary['outstanding'] is None:
                messages.warning(
                    request,
                    'Statement uploaded, but no fee amounts were recognised in this PDF. '
                    'You can still view/download the file below.'
                )
            else:
                # The statement is now this student's opening balance.
                # The signal on FeeStatement has already recalculated the profile
                # (see StudentProfile.recalculate_balances), and every payment
                # confirmed from now on is subtracted from it automatically.
                profile.refresh_from_db()
                messages.success(
                    request,
                    f"Fee statement uploaded and read successfully — amount owed: "
                    f"R{profile.outstanding_balance:,.2f}"
                )
            return redirect('upload_statement')
    else:
        form = FeeStatementForm()

    statements = profile.fee_statements.all()
    return render(request, 'upload_statement.html', {
        'form': form,
        'statements': statements,
    })


@login_required
def upload_registration_proof(request):
    try:
        profile = request.user.profile
    except StudentProfile.DoesNotExist:
        messages.error(request, 'Complete your profile first.')
        return redirect('edit_profile')

    if request.method == 'POST':
        form = ProofOfRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            proof = form.save(commit=False)
            proof.student = profile
            proof.save()
            messages.success(request, 'Proof of registration uploaded successfully.')
            return redirect('upload_registration_proof')
    else:
        form = ProofOfRegistrationForm()

    proofs = profile.registration_proofs.all()
    return render(request, 'upload_registration.html', {
        'form': form,
        'proofs': proofs,
    })


@login_required
def my_payments(request):
    try:
        profile = request.user.profile
    except StudentProfile.DoesNotExist:
        messages.error(request, 'Complete your profile first.')
        return redirect('edit_profile')

    payments = profile.payments.all()
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    status = request.GET.get('status', '')

    if from_date:
        payments = payments.filter(payment_date__gte=from_date)
    if to_date:
        payments = payments.filter(payment_date__lte=to_date)
    if status:
        payments = payments.filter(status=status)

    total_paid_filtered = payments.filter(status='Confirmed').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')
    fees = profile.fees.all()

    return render(request, 'my_payments.html', {
        'profile': profile,
        'payments': payments,
        'fees': fees,
        'from_date': from_date,
        'to_date': to_date,
        'status': status,
        'total_paid_filtered': total_paid_filtered,
    })


@login_required
def download_payment_statement(request):
    """Renders the same filtered payment history as a downloadable PDF."""
    try:
        profile = request.user.profile
    except StudentProfile.DoesNotExist:
        messages.error(request, 'Complete your profile first.')
        return redirect('edit_profile')

    from django.http import FileResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    import io

    payments = profile.payments.all()
    from_date = request.GET.get('from', '')
    to_date = request.GET.get('to', '')
    status = request.GET.get('status', '')
    if from_date:
        payments = payments.filter(payment_date__gte=from_date)
    if to_date:
        payments = payments.filter(payment_date__lte=to_date)
    if status:
        payments = payments.filter(status=status)

    total_paid = payments.filter(status='Confirmed').aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Payment Statement", styles['Title']),
        Spacer(1, 4),
        Paragraph(
            f"{profile.user.get_full_name() or profile.user.username} "
            f"&nbsp;&middot;&nbsp; Student No: {profile.student_number} "
            f"&nbsp;&middot;&nbsp; Programme: {profile.programme or '—'}",
            styles['Normal']
        ),
        Spacer(1, 12),
    ]

    data = [["Date", "Receipt No.", "Method", "Reference", "Amount (R)", "Status"]]
    for p in payments:
        data.append([
            str(p.payment_date), p.receipt_number or "—", p.payment_method,
            p.reference_number or "—", f"{p.amount:,.2f}", p.status
        ])
    data.append(["", "", "", "Total (Confirmed)", f"R {total_paid:,.2f}", ""])

    table = Table(data, colWidths=[22 * mm, 28 * mm, 22 * mm, 28 * mm, 28 * mm, 22 * mm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d47a1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('GRID', (0, 0), (-1, -2), 0.4, colors.grey),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (4, 0), (4, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    doc.build(story)
    buf.seek(0)

    return FileResponse(
        buf, as_attachment=True,
        filename=f"payment_statement_{profile.student_number}.pdf",
        content_type='application/pdf',
    )


@login_required
def make_payment(request):
    """
    Lets a student submit proof of a payment they've already made.
    It's created with status='Pending' — a staff member confirms it
    from the admin panel (or Django admin), which is what actually
    updates the student's balance.
    """
    try:
        profile = request.user.profile
    except StudentProfile.DoesNotExist:
        messages.error(request, 'Complete your profile first.')
        return redirect('edit_profile')

    if request.method == 'POST':
        form = StudentPaymentForm(request.POST, request.FILES, student=profile)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.student = profile
            payment.status = 'Pending'
            payment.save()
            messages.success(
                request,
                'Thanks! Your payment has been submitted and is awaiting confirmation by the finance office.'
            )
            return redirect('my_payments')
    else:
        form = StudentPaymentForm(student=profile)

    return render(request, 'make_payment.html', {'form': form, 'profile': profile})


# ─── Admin / Finance views ───────────────────────────────────────────

@login_required
@user_passes_test(is_staff_member)
def record_payment(request):
    if request.method == 'POST':
        form = PaymentForm(request.POST, request.FILES)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.recorded_by = request.user
            payment.save()   # signals update the fee and the student's balance

            payment.student.refresh_from_db()
            if payment.status == 'Confirmed':
                messages.success(
                    request,
                    f'Payment of R{payment.amount:,.2f} recorded. '
                    f'{payment.student.student_number} now owes R{payment.student.outstanding_balance:,.2f}.'
                )
            else:
                messages.success(
                    request, f'Payment of R{payment.amount:,.2f} recorded (status: {payment.status}).'
                )
            return redirect('record_payment')
    else:
        form = PaymentForm()

    recent = Payment.objects.select_related('student__user', 'fee_item').exclude(status='Pending')[:10]
    pending = Payment.objects.select_related('student__user', 'fee_item').filter(status='Pending')

    # CHANGED: the page no longer loads every student into a dropdown —
    # the search box fetches matches as the admin types.
    return render(request, 'record_payment.html', {
        'form': form,
        'recent_payments': recent,
        'pending_payments': pending,
        'selected_student': _selected_student(request),   # NEW
    })


@login_required
@user_passes_test(is_staff_member)
def confirm_payment(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    if request.method == 'POST' and payment.status != 'Confirmed':
        payment.status = 'Confirmed'
        payment.recorded_by = payment.recorded_by or request.user
        payment.save()   # signals update the fee and the student's balance
        payment.student.refresh_from_db()
        messages.success(
            request,
            f"Payment of R{payment.amount:,.2f} confirmed for {payment.student.student_number}. "
            f"New amount owed: R{payment.student.outstanding_balance:,.2f}."
        )
    return redirect('record_payment')


@login_required
@user_passes_test(is_staff_member)
def reject_payment(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    if request.method == 'POST' and payment.status == 'Pending':
        payment.status = 'Rejected'
        payment.save()
        messages.info(request, f"Payment of R{payment.amount:,.2f} from {payment.student.student_number} was rejected.")
    return redirect('record_payment')


@login_required
@user_passes_test(is_staff_member)
def manage_fees(request):
    if request.method == 'POST':
        form = FeeForm(request.POST)
        if form.is_valid():
            fee = form.save()
            fee.student.recalculate_balances()
            messages.success(request, 'Fee added successfully.')
            return redirect('manage_fees')
    else:
        form = FeeForm()

    fees = Fee.objects.select_related('student', 'fee_item').all()[:50]
    return render(request, 'manage_fees.html', {
        'form': form,
        'fees': fees,
        'selected_student': _selected_student(request),   # NEW
    })


# NEW: JSON endpoint behind the "type a name" student search box
@login_required
@user_passes_test(is_staff_member)
def student_search(request):
    from django.http import JsonResponse

    students = StudentProfile.objects.select_related('user')
    pk = request.GET.get('id', '').strip()
    q = request.GET.get('q', '').strip()

    if pk.isdigit():
        students = students.filter(pk=int(pk))
    elif q:
        # Every word must match somewhere, so "thabo 2021" or "mokoena" both work.
        for term in q.split():
            students = students.filter(
                Q(student_number__icontains=term)
                | Q(user__first_name__icontains=term)
                | Q(user__last_name__icontains=term)
                | Q(user__username__icontains=term)
                | Q(user__email__icontains=term)
                | Q(user__id_number__icontains=term)
            )
        students = students.order_by('user__last_name', 'user__first_name', 'student_number')
    else:
        return JsonResponse({'results': []})

    with_fees = request.GET.get('fees') == '1'
    results = []
    for s in students[:10]:
        name = s.user.get_full_name() or s.user.username
        item = {
            'id': s.pk,
            'student_number': s.student_number,
            'name': name,
            'label': f'{s.student_number} – {name}',
            'programme': s.programme or '—',
            'owing': f'{s.outstanding_balance:,.2f}',
        }
        if with_fees:
            item['fees'] = [
                {
                    'id': f.pk,
                    'label': f'{f.fee_item or f.description or "Fee #" + str(f.pk)} '
                             f'(R{f.remaining_amount} owing)',
                }
                for f in s.fees.exclude(status__in=['Paid', 'Waived'])
            ]
        results.append(item)
    return JsonResponse({'results': results})


@login_required
@user_passes_test(is_staff_member)
def student_list(request):
    """Searchable, filterable, paginated student list for admin/finance staff."""
    from django.core.paginator import Paginator

    students = StudentProfile.objects.select_related('user').all()

    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    balance = request.GET.get('balance', '').strip()
    year = request.GET.get('year', '').strip()

    if q:
        # Every word must match somewhere, so "john 2021" or "smith pretoria" work.
        for term in q.split():
            students = students.filter(
                Q(student_number__icontains=term)
                | Q(user__first_name__icontains=term)
                | Q(user__last_name__icontains=term)
                | Q(user__username__icontains=term)
                | Q(user__email__icontains=term)
                | Q(user__id_number__icontains=term)
                | Q(programme__icontains=term)
                | Q(phone__icontains=term)
            )
    if status:
        students = students.filter(enrollment_status=status)
    if year.isdigit():
        students = students.filter(year_of_study=int(year))
    if balance == 'owing':
        students = students.filter(total_fees__gt=F('fees_paid'))
    elif balance == 'cleared':
        students = students.filter(total_fees__lte=F('fees_paid'))

    total_found = students.count()
    paginator = Paginator(students, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    params = request.GET.copy()
    params.pop('page', None)

    return render(request, 'student_list.html', {
        'students': page_obj,
        'page_obj': page_obj,
        'total_found': total_found,
        'q': q,
        'status': status,
        'balance': balance,
        'year': year,
        'status_choices': StudentProfile.STATUS_CHOICES,
        'querystring': params.urlencode(),
    })


@login_required
@user_passes_test(is_staff_member)
def student_detail(request, pk):
    profile = get_object_or_404(StudentProfile.objects.select_related('user'), pk=pk)
    payments = profile.payments.all()
    fees = profile.fees.all()
    statements = profile.fee_statements.all()
    proofs = profile.registration_proofs.all()
    return render(request, 'student_detail.html', {
        'profile': profile,
        'payments': payments,
        'fees': fees,
        'statements': statements,
        'proofs': proofs,
    })


# ─── HR section ──────────────────────────────────────────────────────

STAFF_ROLES = ['Admin', 'Finance', 'HR']


def _staff_queryset():
    return User.objects.filter(Q(role__in=STAFF_ROLES) | Q(is_superuser=True))


@login_required
@user_passes_test(is_hr_member)
def hr_dashboard(request):
    staff = _staff_queryset()
    return render(request, 'hr_dashboard.html', {
        'total_staff': staff.count(),
        'active_staff': staff.filter(is_active=True).count(),
        'inactive_staff': staff.filter(is_active=False).count(),
        'admin_count': staff.filter(role='Admin').count(),
        'finance_count': staff.filter(role='Finance').count(),
        'hr_count': staff.filter(role='HR').count(),
        'recent_staff': staff.order_by('-date_joined')[:5],
    })


@login_required
@user_passes_test(is_hr_member)
def hr_staff_list(request):
    from django.core.paginator import Paginator

    staff = _staff_queryset().order_by('first_name', 'last_name', 'username')
    q = request.GET.get('q', '').strip()
    role = request.GET.get('role', '').strip()

    for term in q.split():
        staff = staff.filter(
            Q(username__icontains=term) | Q(first_name__icontains=term)
            | Q(last_name__icontains=term) | Q(email__icontains=term)
        )
    if role in STAFF_ROLES:
        staff = staff.filter(role=role)

    page_obj = Paginator(staff, 25).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'hr_staff_list.html', {
        'staff': page_obj, 'page_obj': page_obj, 'q': q, 'role': role,
        'role_options': StaffCreationForm.ROLE_OPTIONS,
        'querystring': params.urlencode(),
    })


@login_required
@user_passes_test(is_hr_member)
def hr_create_staff(request):
    if request.method == 'POST':
        form = StaffCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Staff account "{user.username}" created as {user.get_role_display()}.')
            return redirect('hr_staff_list')
    else:
        form = StaffCreationForm()
    return render(request, 'hr_staff_form.html', {'form': form})


@login_required
@user_passes_test(is_hr_member)
def hr_toggle_staff_active(request, pk):
    target = get_object_or_404(_staff_queryset(), pk=pk)
    if request.method == 'POST':
        if target == request.user:
            messages.error(request, "You can't deactivate your own account.")
        else:
            target.is_active = not target.is_active
            target.save(update_fields=['is_active'])
            state = 'activated' if target.is_active else 'deactivated'
            messages.success(request, f'{target.username} has been {state}.')
    return redirect('hr_staff_list')