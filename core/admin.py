from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, StudentProfile, FeeItem, Payment,
    FeeStatement, ProofOfRegistration, Fee, Notice
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'student_number', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_superuser')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'student_number')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('College Info', {'fields': ('role', 'student_number', 'phone_number', 'id_number', 'date_of_birth')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('College Info', {'fields': ('role', 'student_number', 'phone_number')}),
    )


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = (
        'student_number', 'user', 'programme', 'campus',
        'enrollment_status', 'total_fees', 'fees_paid', 'outstanding_display'
    )
    list_filter = ('enrollment_status', 'study_mode', 'campus', 'academic_year')
    search_fields = ('student_number', 'user__first_name', 'user__last_name', 'user__email', 'programme')
    readonly_fields = ('total_fees', 'fees_paid', 'created_at', 'updated_at')
    raw_id_fields = ('user',)

    def outstanding_display(self, obj):
        return f"R {obj.outstanding_balance:,.2f}"
    outstanding_display.short_description = 'Outstanding'


@admin.register(FeeItem)
class FeeItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'category', 'default_amount', 'is_active')
    list_filter = ('is_active', 'category')
    search_fields = ('name', 'code')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'receipt_number', 'student', 'amount', 'payment_date',
        'payment_method', 'fee_item', 'status', 'recorded_by', 'created_at'
    )
    list_filter = ('status', 'payment_method', 'payment_date')
    search_fields = (
        'receipt_number', 'reference_number',
        'student__student_number', 'student__user__first_name', 'student__user__last_name'
    )
    date_hierarchy = 'payment_date'
    raw_id_fields = ('student', 'recorded_by')
    readonly_fields = ('receipt_number', 'created_at', 'updated_at')


@admin.register(FeeStatement)
class FeeStatementAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'student', 'statement_date', 'total_fees',
        'fees_paid', 'outstanding', 'used_ocr', 'uploaded_at'
    )
    list_filter = ('used_ocr',)
    search_fields = ('title', 'student__student_number')
    raw_id_fields = ('student',)
       # amounts stay editable so staff can correct a mis-read figure; saving recalculates the student's balance
    readonly_fields = ('used_ocr', 'extraction_error')


@admin.register(ProofOfRegistration)
class ProofOfRegistrationAdmin(admin.ModelAdmin):
    list_display = ('title', 'student', 'academic_year', 'uploaded_at')
    search_fields = ('title', 'student__student_number')
    raw_id_fields = ('student',)


@admin.register(Notice)
class NoticeAdmin(admin.ModelAdmin):
    list_display = ('title', 'level', 'target_student', 'due_date', 'is_active', 'created_at')
    list_filter = ('level', 'is_active')
    search_fields = ('title', 'message', 'target_student__student_number')
    raw_id_fields = ('target_student',)