from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

app_name = 'reception'

urlpatterns = [
    # الصفحة الرئيسية
    path('', views.reception_dashboard, name='reception_dashboard'),
    
    # المرضى
    path('patients/', views.patient_list, name='patient_list'),
    path('patients/<int:patient_id>/', views.patient_detail, name='patient_detail'),
    path('patients/<int:patient_id>/print-report/', views.print_patient_report, name='print_patient_report'),
    
    # الطلبات
    path('orders/', views.order_list, name='order_list'),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('orders/new/', views.new_order, name='new_order'),
    
   # 📄 مسارات الطباعة
    path('orders/<int:order_id>/print/', views.print_lab_report, name='print_report'),
    path('orders/<int:order_id>/print/pdf/', views.generate_pdf_report, name='print_pdf'),
     # ✅ أضف هذا الرابط للتقرير اليومي
    path('reports/daily/', views.daily_report, name='daily_report'),
    
    # ⚙️ الإعدادات - Dashboard
    path('settings/', views.settings_dashboard, name='settings_dashboard'),
    
    # ⚙️ إعدادات الطباعة
    path('settings/printing/', views.printing_settings, name='printing_settings'),
    path('settings/printing/save/', views.save_printing_settings, name='save_printing_settings'),
    
    # 🔬 إعدادات التحاليل
    path('settings/lab-tests/', views.lab_tests_settings, name='lab_tests_settings'),
    path('settings/lab-tests/add/', views.add_lab_test, name='add_lab_test'),
    path('settings/lab-tests/<int:test_id>/edit/', views.edit_lab_test, name='edit_lab_test'),
    path('settings/lab-tests/<int:test_id>/toggle/', views.toggle_lab_test_status, name='toggle_lab_test_status'),
    path('settings/lab-tests/<int:test_id>/delete/', views.delete_lab_test, name='delete_lab_test'),
    path('settings/lab-tests/export/', views.export_lab_tests, name='export_lab_tests'),
    
    # 🔧 إعدادات النظام (مستقبلاً)
    path('settings/system/', views.system_settings, name='system_settings'),
    
    # 🏥 إعدادات المختبر (مستقبلاً)
    path('settings/lab/', views.lab_settings, name='lab_settings'),
    
    # 🔐 المصادقة
    path('login/', auth_views.LoginView.as_view(template_name='reception/login.html', redirect_authenticated_user=True), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='reception:login'), name='logout'),
]