from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Auth
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # Student
    path('', views.landing, name='landing'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('upload/statement/', views.upload_statement, name='upload_statement'),
    path('upload/registration/', views.upload_registration_proof, name='upload_registration_proof'),
    path('payments/', views.my_payments, name='my_payments'),
    path('payments/make/', views.make_payment, name='make_payment'),
    path('payments/statement.pdf', views.download_payment_statement, name='download_payment_statement'),
    path('admin-panel/students/search/', views.student_search, name='student_search'),
    # HR
    path('hr/', views.hr_dashboard, name='hr_dashboard'),
    path('hr/staff/', views.hr_staff_list, name='hr_staff_list'),
    path('hr/staff/new/', views.hr_create_staff, name='hr_create_staff'),
    path('hr/staff/<int:pk>/toggle/', views.hr_toggle_staff_active, name='hr_toggle_staff_active'),

    # Admin / Finance
    path('admin-panel/record-payment/', views.record_payment, name='record_payment'),
    path('admin-panel/payments/<int:pk>/confirm/', views.confirm_payment, name='confirm_payment'),
    path('admin-panel/payments/<int:pk>/reject/', views.reject_payment, name='reject_payment'),
    path('admin-panel/fees/', views.manage_fees, name='manage_fees'),
    path('admin-panel/students/', views.student_list, name='student_list'),
    path('admin-panel/students/<int:pk>/', views.student_detail, name='student_detail'),
]