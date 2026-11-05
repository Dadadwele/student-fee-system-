from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import Fee, FeeStatement, Payment, StudentProfile, User


def make_student(username='s1', number='2021001', first='Thabo', last='Mokoena'):
    user = User.objects.create_user(
        username=username, password='pass12345', first_name=first, last_name=last,
        role='Student', student_number=number,
    )
    return StudentProfile.objects.create(user=user, student_number=number)


def add_statement(student, total, paid, owed):
    return FeeStatement.objects.create(
        student=student, title='Statement',
        statement_file=SimpleUploadedFile('s.pdf', b'%PDF-1.4'),
        total_fees=Decimal(total), fees_paid=Decimal(paid), outstanding=Decimal(owed),
    )


class BalanceAfterStatementTests(TestCase):
    def test_statement_sets_opening_balance(self):
        s = make_student()
        add_statement(s, '10000', '5000', '5000')
        s.refresh_from_db()
        self.assertEqual(s.outstanding_balance, Decimal('5000'))

    def test_confirmed_payment_reduces_amount_owed(self):
        s = make_student()
        add_statement(s, '10000', '5000', '5000')
        Payment.objects.create(student=s, amount=Decimal('1500'),
                               payment_date='2026-01-10', status='Confirmed')
        s.refresh_from_db()
        self.assertEqual(s.outstanding_balance, Decimal('3500'))
        self.assertEqual(s.fees_paid, Decimal('6500'))

    def test_several_payments_keep_subtracting(self):
        s = make_student()
        add_statement(s, '5000', '0', '5000')
        for amt in ('1000', '500', '250'):
            Payment.objects.create(student=s, amount=Decimal(amt),
                                   payment_date='2026-01-10', status='Confirmed')
        s.refresh_from_db()
        self.assertEqual(s.outstanding_balance, Decimal('3250'))

    def test_pending_payment_does_not_change_balance_until_confirmed(self):
        s = make_student()
        add_statement(s, '5000', '0', '5000')
        p = Payment.objects.create(student=s, amount=Decimal('2000'),
                                   payment_date='2026-01-10', status='Pending')
        s.refresh_from_db()
        self.assertEqual(s.outstanding_balance, Decimal('5000'))
        p.status = 'Confirmed'
        p.save()
        s.refresh_from_db()
        self.assertEqual(s.outstanding_balance, Decimal('3000'))

    def test_rejected_payment_is_ignored(self):
        s = make_student()
        add_statement(s, '5000', '0', '5000')
        Payment.objects.create(student=s, amount=Decimal('2000'),
                               payment_date='2026-01-10', status='Rejected')
        s.refresh_from_db()
        self.assertEqual(s.outstanding_balance, Decimal('5000'))

    def test_deleting_payment_restores_balance(self):
        s = make_student()
        add_statement(s, '5000', '0', '5000')
        p = Payment.objects.create(student=s, amount=Decimal('2000'),
                                   payment_date='2026-01-10', status='Confirmed')
        p.delete()
        s.refresh_from_db()
        self.assertEqual(s.outstanding_balance, Decimal('5000'))

    def test_new_statement_becomes_new_opening_balance(self):
        s = make_student()
        add_statement(s, '5000', '0', '5000')
        Payment.objects.create(student=s, amount=Decimal('1000'),
                               payment_date='2026-01-10', status='Confirmed')
        add_statement(s, '5000', '1000', '4000')   # bank's statement now reflects the payment
        s.refresh_from_db()
        self.assertEqual(s.outstanding_balance, Decimal('4000'))   # not 3000: no double count

    def test_fee_added_after_statement_increases_balance(self):
        s = make_student()
        add_statement(s, '5000', '0', '5000')
        Fee.objects.create(student=s, description='Library fine', amount=Decimal('200'))
        s.refresh_from_db()
        self.assertEqual(s.outstanding_balance, Decimal('5200'))

    def test_without_statement_uses_fee_records(self):
        s = make_student()
        fee = Fee.objects.create(student=s, description='Tuition', amount=Decimal('8000'))
        Payment.objects.create(student=s, fee=fee, amount=Decimal('3000'),
                               payment_date='2026-01-10', status='Confirmed')
        s.refresh_from_db()
        fee.refresh_from_db()
        self.assertEqual(s.outstanding_balance, Decimal('5000'))
        self.assertEqual(fee.paid_amount, Decimal('3000'))
        self.assertEqual(fee.status, 'Partial')


class StudentSearchTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='boss', password='pass12345', role='Admin')
        make_student('a', '2021001', 'Thabo', 'Mokoena')
        make_student('b', '2022002', 'Lerato', 'Dlamini')
        make_student('c', '2023003', 'Thabo', 'Naidoo')
        self.client.login(username='boss', password='pass12345')

    def names(self, **params):
        resp = self.client.get(reverse('student_list'), params)
        self.assertEqual(resp.status_code, 200)
        return {s.student_number for s in resp.context['students']}

    def test_search_by_student_number(self):
        self.assertEqual(self.names(q='2022002'), {'2022002'})

    def test_search_by_first_name(self):
        self.assertEqual(self.names(q='thabo'), {'2021001', '2023003'})

    def test_search_multiple_words(self):
        self.assertEqual(self.names(q='thabo naidoo'), {'2023003'})

    def test_owing_filter(self):
        s = StudentProfile.objects.get(student_number='2021001')
        add_statement(s, '1000', '0', '1000')
        self.assertEqual(self.names(balance='owing'), {'2021001'})

    def test_students_cannot_open_student_list(self):
        self.client.logout()
        self.client.login(username='a', password='pass12345')
        resp = self.client.get(reverse('student_list'))
        self.assertNotEqual(resp.status_code, 200)