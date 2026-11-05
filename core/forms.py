from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, StudentProfile, FeeStatement, ProofOfRegistration, Payment, FeeItem, Fee


FEE_CHOICES = [
    ('', '-- Select Fee Type (Optional) --'),
    ('tuition', 'Tuition Fee'),
    ('registration', 'Registration Fee'),
    ('accommodation', 'Accommodation Fee'),
    ('library', 'Library Fee'),
    ('other', 'Other'),
]


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    student_number = forms.CharField(max_length=20, required=True)
    phone_number = forms.CharField(max_length=20, required=False)
    programme = forms.CharField(max_length=150, required=False, label="Programme / Course")
    year_of_study = forms.IntegerField(min_value=1, max_value=6, initial=1)

    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'username', 'email',
            'student_number', 'phone_number',
            'password1', 'password2',
        ]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = 'Student'
        user.student_number = self.cleaned_data['student_number']
        user.phone_number = self.cleaned_data.get('phone_number', '')
        if commit:
            user.save()
            StudentProfile.objects.create(
                user=user,
                student_number=self.cleaned_data['student_number'],
                programme=self.cleaned_data.get('programme', ''),
                year_of_study=self.cleaned_data.get('year_of_study', 1),
                phone=self.cleaned_data.get('phone_number', ''),
            )
        return user


class StudentProfileForm(forms.ModelForm):
    date_of_birth = forms.DateField(
        required=False, widget=forms.DateInput(attrs={'type': 'date'})
    )

    class Meta:
        model = StudentProfile
        fields = [
            'programme', 'qualification', 'faculty', 'campus', 'academic_year',
            'year_of_study', 'study_mode', 'enrollment_status',
            'registration_date', 'phone', 'address', 'city', 'province', 'photo',
        ]
        widgets = {
            'registration_date': forms.DateInput(attrs={'type': 'date'}),
            'address': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['date_of_birth'].initial = self.instance.user.date_of_birth

    def save(self, commit=True):
        profile = super().save(commit=commit)
        dob = self.cleaned_data.get('date_of_birth')
        if commit:
            profile.user.date_of_birth = dob
            profile.user.save(update_fields=['date_of_birth'])
        return profile


class FeeStatementForm(forms.ModelForm):
    class Meta:
        model = FeeStatement
        fields = ['title', 'statement_file', 'statement_date', 'notes']
        widgets = {
            'statement_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }


class ProofOfRegistrationForm(forms.ModelForm):
    class Meta:
        model = ProofOfRegistration
        fields = ['title', 'document', 'academic_year', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 2}),
        }


class FeeForm(forms.ModelForm):
    class Meta:
        model = Fee
        fields = [
            'student', 'fee_item', 'academic_year', 'description',
            'amount', 'discount', 'fine', 'due_date', 'status'
        ]
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date'}),
            'amount': forms.NumberInput(attrs={'step': '0.01'}),
            'discount': forms.NumberInput(attrs={'step': '0.01'}),
            'fine': forms.NumberInput(attrs={'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fee_item'].queryset = FeeItem.objects.filter(is_active=True)
        self.fields['student'].queryset = StudentProfile.objects.select_related('user').all()


class PaymentForm(forms.ModelForm):
    fee_type = forms.ChoiceField(
        choices=FEE_CHOICES,
        required=False,
        label="Fee Category (Optional)",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Payment
        fields = [
            'student', 'fee_type', 'amount', 'payment_date', 'payment_method',
            'reference_number', 'fee_item', 'status', 'notes', 'proof_of_payment',
        ]
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fee_item'].queryset = FeeItem.objects.filter(is_active=True)
        self.fields['student'].queryset = StudentProfile.objects.select_related('user').all()


class StudentPaymentForm(forms.ModelForm):
    """
    The 'Make a Payment' form a student fills in themselves, to say
    "I've paid this, here's my proof" — always lands as Pending until
    a staff member confirms it in the admin panel.
    """
    fee_type = forms.ChoiceField(
        choices=FEE_CHOICES,
        required=False,
        label="Which fee category is this for? (optional)",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = Payment
        fields = [
            'fee_type', 'amount', 'payment_date', 'payment_method',
            'reference_number', 'notes', 'proof_of_payment',
        ]
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'proof_of_payment': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, student=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Specific fee dropdown completely removed from student view


class StaffCreationForm(UserCreationForm):
    """Used by HR to create staff logins (Admin, Finance or HR)."""
    ROLE_OPTIONS = (
        ('Admin', 'Admin'),
        ('Finance', 'Finance Administrator'),
        ('HR', 'Human Resources'),
    )
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    phone_number = forms.CharField(max_length=20, required=False)
    role = forms.ChoiceField(choices=ROLE_OPTIONS)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email', 'phone_number',
                  'role', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            field.widget.attrs['class'] = css

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = self.cleaned_data['role']
        user.phone_number = self.cleaned_data.get('phone_number', '')
        # HR accounts need is_staff to be able to open the Django admin site
        user.is_staff = (user.role == 'HR')
        if commit:
            user.save()
        return user
