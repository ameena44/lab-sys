from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import datetime, timedelta
from core.models import Patient, Doctor, LabTest, Order, OrderDetail

# ======== دوال الطباعة الجديدة ========
from django.http import HttpResponse
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.lib import colors
import arabic_reshaper
from bidi.algorithm import get_display
# ======================================

@login_required
def reception_dashboard(request):
    """لوحة تحكم الاستقبال"""
    
    # إحصائيات
    today = timezone.now().date()
    
    stats = {
        'total_patients': Patient.objects.count(),
        'total_orders': Order.objects.count(),
        'today_orders': Order.objects.filter(order_date__date=today).count(),
        'pending_orders': Order.objects.filter(status='pending').count(),
        'total_revenue': Order.objects.aggregate(total=Sum('total_amount'))['total'] or 0,
    }
    
    # أحدث الطلبات
    recent_orders = Order.objects.select_related('patient', 'referring_doctor').order_by('-order_date')[:10]
    
    # أحدث المرضى
    recent_patients = Patient.objects.order_by('-created_at')[:10]
    
    context = {
        'stats': stats,
        'recent_orders': recent_orders,
        'recent_patients': recent_patients,
        'page_title': 'لوحة التحكم - الاستقبال',
    }
    
    return render(request, 'reception/dashboard.html', context)

@login_required
def patient_list(request):
    """قائمة المرضى"""
    
    patients = Patient.objects.select_related('referring_doctor').order_by('-created_at')
    
    # البحث
    search_query = request.GET.get('search', '')
    if search_query:
        patients = patients.filter(
            Q(full_name__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(national_id__icontains=search_query)
        )
    
    context = {
        'patients': patients,
        'search_query': search_query,
        'page_title': 'قائمة المرضى',
    }
    
    return render(request, 'reception/patient_list.html', context)

@login_required
def patient_detail(request, patient_id):
    """تفاصيل المريض"""
    
    # جلب المريض
    patient = get_object_or_404(Patient, id=patient_id)
    
    # جلب طلبات المريض
    patient_orders = Order.objects.filter(patient=patient).order_by('-order_date')
    
    # إحصائيات المريض
    total_orders = patient_orders.count()
    completed_orders = patient_orders.filter(status='completed').count()
    total_spent = patient_orders.aggregate(total=Sum('total_amount'))['total'] or 0
    
    # حساب المتوسط
    average_spent = 0
    if total_orders > 0:
        average_spent = total_spent / total_orders
    
    # البيانات للقالب
    context = {
        'patient': patient,
        'patient_orders': patient_orders[:10],  # آخر 10 طلبات
        'total_orders': total_orders,
        'completed_orders': completed_orders,
        'total_spent': total_spent,
        'average_spent': average_spent,
        'page_title': f'تفاصيل المريض - {patient.full_name}',
    }
    
    return render(request, 'reception/patient_detail.html', context)

@login_required
def order_list(request):
    """قائمة الطلبات"""
    
    orders = Order.objects.select_related('patient', 'referring_doctor').order_by('-order_date')
    
    # التصفية
    status_filter = request.GET.get('status', '')
    date_filter = request.GET.get('date', '')
    
    if status_filter:
        orders = orders.filter(status=status_filter)
    
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            orders = orders.filter(order_date__date=filter_date)
        except ValueError:
            pass
    
    context = {
        'orders': orders,
        'status_filter': status_filter,
        'date_filter': date_filter,
        'page_title': 'قائمة الطلبات',
    }
    
    return render(request, 'reception/order_list.html', context)

@login_required
def order_detail(request, order_id):
    """تفاصيل الطلب"""
    
    order = get_object_or_404(Order, id=order_id)
    order_details = OrderDetail.objects.filter(order=order).select_related('lab_test')
    
    context = {
        'order': order,
        'order_details': order_details,
        'page_title': f'تفاصيل الطلب - {order.order_number}',
    }
    
    return render(request, 'reception/order_detail.html', context)

@login_required
def new_order(request):
    """إنشاء طلب جديد"""
    
    if request.method == 'POST':
        # هنا سنضيف منطق إنشاء الطلب
        messages.success(request, 'تم إنشاء الطلب بنجاح!')
        return redirect('reception:order_list')
    
    # جلب البيانات للقوائم المنسدلة
    patients = Patient.objects.all()
    doctors = Doctor.objects.filter(is_active=True)
    lab_tests = LabTest.objects.filter(is_active=True)
    
    context = {
        'patients': patients,
        'doctors': doctors,
        'lab_tests': lab_tests,
        'page_title': 'إنشاء طلب جديد',
    }
    
    return render(request, 'reception/new_order.html', context)


# ===========================================================
# ========== دوال الطباعة والتقارير ==========
# ===========================================================

@login_required
def print_lab_report(request, order_id):
    """عرض تقرير الطلب للطباعة (HTML)"""
    
    order = get_object_or_404(Order.objects.select_related('patient', 'referring_doctor'), id=order_id)
    order_details = OrderDetail.objects.filter(order=order).select_related('lab_test')
    
    # التحقق من اكتمال جميع النتائج
    all_tests_completed = all(detail.result_value for detail in order_details)
    has_critical_results = any(detail.result_status == 'critical' for detail in order_details if detail.result_status)
    
    context = {
        'order': order,
        'order_details': order_details,
        'print_date': timezone.now(),
        'all_tests_completed': all_tests_completed,
        'has_critical_results': has_critical_results,
        'total_tests': order_details.count(),
        'completed_tests': sum(1 for detail in order_details if detail.result_value),
    }
    
    return render(request, 'reception/print_report.html', context)

@login_required
def generate_pdf_report(request, order_id):
    """توليد تقرير PDF"""
    
    order = get_object_or_404(Order.objects.select_related('patient', 'referring_doctor'), id=order_id)
    order_details = OrderDetail.objects.filter(order=order).select_related('lab_test')
    
    # التحقق من اكتمال جميع النتائج قبل السماح بتحميل PDF
    all_tests_completed = all(detail.result_value for detail in order_details)
    if not all_tests_completed:
        messages.error(request, 'لا يمكن طباعة التقرير لأن بعض التحاليل لم تكتمل بعد!')
        return redirect('reception:order_detail', order_id=order_id)
    
    # إنشاء buffer للـ PDF
    buffer = io.BytesIO()
    
    # إنشاء مستند PDF
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    # العناصر التي ستظهر في PDF
    elements = []
    
    # الحصول على الأنماط
    styles = getSampleStyleSheet()
    
    # إنشاء أنماط للغة العربية
    arabic_style = ParagraphStyle(
        'ArabicStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        alignment=TA_RIGHT,
        rightIndent=0,
        wordWrap='RTL',
        spaceAfter=6
    )
    
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=15
    )
    
    # العنوان الرئيسي
    title_text = arabic_reshaper.reshape("تقرير نتائج التحاليل الطبية")
    title_bidi = get_display(title_text)
    elements.append(Paragraph(title_bidi, title_style))
    
    # معلومات التقرير
    report_info = arabic_reshaper.reshape(f"رقم التقرير: {order.order_number} | تاريخ الطباعة: {timezone.now().strftime('%Y-%m-%d %H:%M')}")
    report_bidi = get_display(report_info)
    elements.append(Paragraph(report_bidi, arabic_style))
    elements.append(Spacer(1, 15))
    
    # عنوان معلومات المريض
    patient_title = arabic_reshaper.reshape("معلومات المريض")
    patient_title_bidi = get_display(patient_title)
    elements.append(Paragraph(patient_title_bidi, arabic_style))
    
    # عرض العمر بشكل مناسب
    age_display = order.patient.age_display
    
    # معلومات المريض في جدول
    patient_data = [
        [
            Paragraph(get_display(arabic_reshaper.reshape("الاسم الكامل:")), arabic_style),
            Paragraph(get_display(arabic_reshaper.reshape(str(order.patient.full_name))), arabic_style),
            Paragraph(get_display(arabic_reshaper.reshape("العمر:")), arabic_style),
            Paragraph(get_display(arabic_reshaper.reshape(age_display)), arabic_style),
        ],
        [
            Paragraph(get_display(arabic_reshaper.reshape("رقم الهوية:")), arabic_style),
            Paragraph(get_display(arabic_reshaper.reshape(str(order.patient.national_id or '-'))), arabic_style),
            Paragraph(get_display(arabic_reshaper.reshape("الجنس:")), arabic_style),
            Paragraph(get_display(arabic_reshaper.reshape(order.patient.get_gender_display() or '-')), arabic_style),
        ],
        [
            Paragraph(get_display(arabic_reshaper.reshape("رقم الهاتف:")), arabic_style),
            Paragraph(get_display(arabic_reshaper.reshape(str(order.patient.phone or '-'))), arabic_style),
            Paragraph(get_display(arabic_reshaper.reshape("رقم الطلب:")), arabic_style),
            Paragraph(get_display(arabic_reshaper.reshape(order.order_number)), arabic_style),
        ],
        [
            Paragraph(get_display(arabic_reshaper.reshape("تاريخ الطلب:")), arabic_style),
            Paragraph(get_display(arabic_reshaper.reshape(order.order_date.strftime('%Y-%m-%d %H:%M'))), arabic_style),
            Paragraph("", arabic_style),
            Paragraph("", arabic_style),
        ],
    ]
    
    if order.referring_doctor:
        patient_data.insert(3, [
            Paragraph(get_display(arabic_reshaper.reshape("الطبيب المحول:")), arabic_style),
            Paragraph(get_display(arabic_reshaper.reshape(order.referring_doctor.name)), arabic_style),
            Paragraph("", arabic_style),
            Paragraph("", arabic_style),
        ])
    
    patient_table = Table(patient_data, colWidths=[4*cm, 6*cm, 3*cm, 5*cm])
    patient_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ]))
    
    elements.append(patient_table)
    elements.append(Spacer(1, 15))
    
    # عنوان نتائج التحاليل
    results_title = arabic_reshaper.reshape("نتائج التحاليل")
    results_title_bidi = get_display(results_title)
    elements.append(Paragraph(results_title_bidi, arabic_style))
    elements.append(Spacer(1, 10))
    
    # جدول نتائج التحاليل
    results_data = []
    
    # رأس الجدول
    headers = ["#", "اسم التحليل", "النتيجة", "الوحدة", "الحالة"]
    arabic_headers = []
    for header in headers:
        reshaped = arabic_reshaper.reshape(header)
        bidi = get_display(reshaped)
        arabic_headers.append(Paragraph(bidi, arabic_style))
    
    results_data.append(arabic_headers)
    
    # بيانات الجدول
    for idx, detail in enumerate(order_details, 1):
        # اسم التحليل (استخدام الاسم العربي إن وجد)
        test_name = detail.lab_test.name_ar or detail.lab_test.name
        
        # النتيجة
        if detail.result_value:
            result_text = detail.result_value
            # تحديد لون النتيجة
            if detail.result_status == 'normal':
                result_color = colors.green
            elif detail.result_status == 'abnormal':
                result_color = colors.red
            elif detail.result_status == 'critical':
                result_color = colors.darkred
            else:
                result_color = colors.black
        else:
            result_text = "بانتظار النتيجة"
            result_color = colors.orange
        
        # الحالة
        if detail.result_status:
            if detail.result_status == 'normal':
                status_text = "طبيعي"
                status_color = colors.green
            elif detail.result_status == 'abnormal':
                status_text = "غير طبيعي"
                status_color = colors.red
            elif detail.result_status == 'critical':
                status_text = "حرج"
                status_color = colors.darkred
            else:
                status_text = detail.result_status
                status_color = colors.black
        else:
            status_text = "قيد التحليل"
            status_color = colors.orange
        
        # تحويل النصوص للعربية
        reshaped_name = arabic_reshaper.reshape(test_name)
        reshaped_result = arabic_reshaper.reshape(result_text)
        reshaped_unit = arabic_reshaper.reshape(detail.lab_test.unit or "-")
        reshaped_status = arabic_reshaper.reshape(status_text)
        
        bidi_name = get_display(reshaped_name)
        bidi_result = get_display(reshaped_result)
        bidi_unit = get_display(reshaped_unit)
        bidi_status = get_display(reshaped_status)
        
        # إضافة كود التحليل إذا موجود
        if detail.lab_test.code:
            test_code = arabic_reshaper.reshape(f"كود: {detail.lab_test.code}")
            test_code_bidi = get_display(test_code)
            bidi_name = f"{bidi_name}<br/><font size='7'>{test_code_bidi}</font>"
        
        row = [
            Paragraph(str(idx), arabic_style),
            Paragraph(bidi_name, arabic_style),
            Paragraph(bidi_result, arabic_style),
            Paragraph(bidi_unit, arabic_style),
            Paragraph(bidi_status, arabic_style),
        ]
        
        results_data.append(row)
    
    # إنشاء جدول النتائج
    results_table = Table(results_data, colWidths=[1*cm, 8*cm, 4*cm, 2.5*cm, 3*cm])
    
    # تنسيق جدول النتائج
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
    ])
    
    # إضافة ألوان للنتائج
    for i, detail in enumerate(order_details, 1):
        if detail.result_status == 'normal':
            table_style.add('TEXTCOLOR', (2, i), (2, i), colors.green)  # النتيجة
            table_style.add('TEXTCOLOR', (4, i), (4, i), colors.green)  # الحالة
        elif detail.result_status == 'abnormal':
            table_style.add('TEXTCOLOR', (2, i), (2, i), colors.red)
            table_style.add('TEXTCOLOR', (4, i), (4, i), colors.red)
        elif detail.result_status == 'critical':
            table_style.add('TEXTCOLOR', (2, i), (2, i), colors.darkred)
            table_style.add('TEXTCOLOR', (4, i), (4, i), colors.darkred)
            table_style.add('BACKGROUND', (2, i), (2, i), colors.pink)
            table_style.add('BACKGROUND', (4, i), (4, i), colors.pink)
        elif not detail.result_value:
            table_style.add('TEXTCOLOR', (2, i), (2, i), colors.orange)
            table_style.add('TEXTCOLOR', (4, i), (4, i), colors.orange)
    
    results_table.setStyle(table_style)
    elements.append(results_table)
    elements.append(Spacer(1, 20))
    
    # الملاحظات
    if order.notes:
        notes_title = arabic_reshaper.reshape("ملاحظات الطلب:")
        notes_title_bidi = get_display(notes_title)
        elements.append(Paragraph(notes_title_bidi, arabic_style))
        
        reshaped_notes = arabic_reshaper.reshape(order.notes)
        notes_bidi = get_display(reshaped_notes)
        elements.append(Paragraph(notes_bidi, arabic_style))
        elements.append(Spacer(1, 15))
    
    # التوقيعات
    signature_title = arabic_reshaper.reshape("التوقيعات")
    signature_bidi = get_display(signature_title)
    elements.append(Paragraph(signature_bidi, arabic_style))
    elements.append(Spacer(1, 10))
    
    signature_data = [
        [
            Paragraph(get_display(arabic_reshaper.reshape("توقيع فني المختبر")), arabic_style),
            "",
            Paragraph(get_display(arabic_reshaper.reshape("توقيع الطبيب")), arabic_style),
            "",
        ],
        [
            Paragraph(get_display(arabic_reshaper.reshape("الاسم: ________________")), arabic_style),
            Paragraph(get_display(arabic_reshaper.reshape("التاريخ: ________________")), arabic_style),
            Paragraph(get_display(arabic_reshaper.reshape("الاسم: ________________")), arabic_style),
            Paragraph(get_display(arabic_reshaper.reshape("التاريخ: ________________")), arabic_style),
        ],
    ]
    
    signature_table = Table(signature_data, colWidths=[5*cm, 4*cm, 5*cm, 4*cm])
    signature_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    
    elements.append(signature_table)
    
    # ملاحظات عامة
    footer_notes = arabic_reshaper.reshape("ملاحظات:")
    footer_notes_bidi = get_display(footer_notes)
    
    general_notes = arabic_reshaper.reshape("""
    1. هذا التقرير صادر عن المختبر ويرجع تفسيره للطبيب المعالج.
    2. النتائج قد تتأثر بالعوامل الفنية والبيولوجية.
    3. في حالة وجود نتائج حرجة، سيتم إبلاغ الطبيب المعالج فوراً.
    """)
    general_notes_bidi = get_display(general_notes)
    
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(footer_notes_bidi, arabic_style))
    elements.append(Paragraph(general_notes_bidi, arabic_style))
    
    # بناء PDF
    doc.build(elements)
    
    # الحصول على قيمة PDF من buffer
    pdf = buffer.getvalue()
    buffer.close()
    
    # إرجاع استجابة PDF
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="lab_report_{order.order_number}.pdf"'
    
    return response


# ===========================================================
# ========== التعديلات المطلوبة ==========
# ===========================================================

@login_required
def print_patient_report(request, patient_id):
    """تقرير المريض - إصلاح: إعادة توجيه لملف المريض"""
    # ✅ الحل البسيط: إعادة توجيه لصفحة تفاصيل المريض
    return redirect('reception:patient_detail', patient_id=patient_id)

@login_required
def daily_report(request):
    """تقرير يومي - إصلاح: إعادة توجيه لقائمة الطلبات"""
    # ✅ الحل البسيط: إعادة توجيه لقائمة الطلبات مع فلترة التاريخ
    date_str = request.GET.get('date', '')
    if date_str:
        return redirect(f'/reception/orders/?date={date_str}')
    else:
        return redirect('reception:order_list')

# ===========================================================
# ========== دوال الإعدادات ==========
# ===========================================================

# إعدادات الطباعة الافتراضية
DEFAULT_PRINT_SETTINGS = {
    'font_size': '10pt',
    'text_color': '#000000',
    'border_color': '#000000',
    'normal_color': '#008000',
    'abnormal_color': '#ff0000',
    'critical_color': '#cc0000',
    'header_height': '80px',
    'footer_height': '60px',
    'table_header_color': '#f0f0f0',
    'even_row_color': '#ffffff',
    'show_h_l': True,
    'show_reference_range': True,
    'show_test_codes': False,
    'show_units': True,
}

@login_required
def settings_dashboard(request):
    """لوحة تحكم الإعدادات"""
    context = {
        'page_title': 'الإعدادات',
        'active_tab': 'settings',
    }
    return render(request, 'reception/settings/base_settings.html', context)

@login_required
def printing_settings(request):
    """صفحة إعدادات الطباعة"""
    settings = request.session.get('print_settings', DEFAULT_PRINT_SETTINGS)
    
    context = {
        'page_title': 'إعدادات طباعة التقارير',
        'settings': settings,
        'active_tab': 'printing',
    }
    
    return render(request, 'reception/settings/printing_settings.html', context)

@login_required
def save_printing_settings(request):
    """حفظ إعدادات الطباعة"""
    if request.method == 'POST':
        try:
            settings = {
                'font_size': request.POST.get('font_size', '10pt'),
                'text_color': request.POST.get('text_color', '#000000'),
                'border_color': request.POST.get('border_color', '#000000'),
                'normal_color': request.POST.get('normal_color', '#008000'),
                'abnormal_color': request.POST.get('abnormal_color', '#ff0000'),
                'critical_color': request.POST.get('critical_color', '#cc0000'),
                'header_height': request.POST.get('header_height', '80px'),
                'footer_height': request.POST.get('footer_height', '60px'),
                'table_header_color': request.POST.get('table_header_color', '#f0f0f0'),
                'even_row_color': request.POST.get('even_row_color', '#ffffff'),
                'show_h_l': request.POST.get('show_h_l') == 'on',
                'show_reference_range': request.POST.get('show_reference_range') == 'on',
                'show_test_codes': request.POST.get('show_test_codes') == 'on',
                'show_units': request.POST.get('show_units') == 'on',
            }
            
            # التحقق من القيم
            if not settings['font_size'].endswith('pt'):
                settings['font_size'] += 'pt'
            if not settings['header_height'].endswith('px'):
                settings['header_height'] += 'px'
            if not settings['footer_height'].endswith('px'):
                settings['footer_height'] += 'px'
            
            # حفظ في الجلسة
            request.session['print_settings'] = settings
            
            messages.success(request, '✅ تم حفظ إعدادات الطباعة بنجاح!')
            return redirect('reception:printing_settings')
            
        except Exception as e:
            messages.error(request, f'❌ حدث خطأ أثناء حفظ الإعدادات: {str(e)}')
            return redirect('reception:printing_settings')
    
    return redirect('reception:printing_settings')

# الحاجة إلى Paginator للدوال التالية
from django.core.paginator import Paginator

@login_required
def lab_tests_settings(request):
    """إعدادات التحاليل - قائمة التحاليل"""
    lab_tests = LabTest.objects.all().order_by('category', 'name_ar')
    
    # البحث والتصفية
    search_query = request.GET.get('search', '')
    category_filter = request.GET.get('category', '')
    status_filter = request.GET.get('status', '')
    
    if search_query:
        lab_tests = lab_tests.filter(
            Q(name__icontains=search_query) |
            Q(name_ar__icontains=search_query) |
            Q(code__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    if category_filter:
        lab_tests = lab_tests.filter(category=category_filter)
    
    if status_filter:
        if status_filter == 'active':
            lab_tests = lab_tests.filter(is_active=True)
        elif status_filter == 'inactive':
            lab_tests = lab_tests.filter(is_active=False)
    
    # التقسيم للصفحات
    paginator = Paginator(lab_tests, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # الحصول على جميع الفئات
    categories = LabTest.objects.values_list('category', flat=True)\
        .distinct()\
        .exclude(category__isnull=True)\
        .exclude(category='')\
        .order_by('category')
    
    # الإحصائيات
    total_tests = lab_tests.count()
    active_tests = lab_tests.filter(is_active=True).count()
    inactive_tests = lab_tests.filter(is_active=False).count()
    
    context = {
        'page_title': 'إدارة التحاليل المخبرية',
        'page_obj': page_obj,
        'search_query': search_query,
        'category_filter': category_filter,
        'status_filter': status_filter,
        'categories': categories,
        'total_tests': total_tests,
        'active_tests': active_tests,
        'inactive_tests': inactive_tests,
        'active_tab': 'lab_tests',
        'sample_type_choices': LabTest.SAMPLE_TYPE_CHOICES,
        'result_type_choices': LabTest.RESULT_TYPE_CHOICES,
    }
    
    return render(request, 'reception/settings/lab_tests_settings.html', context)

@login_required
def add_lab_test(request):
    """إضافة تحليل جديد"""
    if request.method == 'POST':
        try:
            # التحقق من وجود الكود مسبقاً
            code = request.POST.get('code', '').strip()
            if LabTest.objects.filter(code=code).exists():
                messages.error(request, f'❌ كود التحليل "{code}" موجود مسبقاً!')
                return redirect('reception:add_lab_test')
            
            # إنشاء التحليل الجديد
            lab_test = LabTest.objects.create(
                name=request.POST.get('name', '').strip(),
                name_ar=request.POST.get('name_ar', '').strip(),
                code=code,
                result_type=request.POST.get('result_type', 'numerical'),
                sample_type=request.POST.get('sample_type', 'blood'),
                unit=request.POST.get('unit', '').strip(),
                standard_price=float(request.POST.get('standard_price', 0) or 0),
                cost=float(request.POST.get('cost', 0) or 0),
                turnaround_time=request.POST.get('turnaround_time', '24 ساعة').strip(),
                description=request.POST.get('description', '').strip(),
                instructions=request.POST.get('instructions', '').strip(),
                category=request.POST.get('category', '').strip(),
                normal_range=request.POST.get('normal_range', '').strip(),
                is_active=request.POST.get('is_active') == 'on'
            )
            
            messages.success(request, f'✅ تم إضافة التحليل "{lab_test.name_ar}" بنجاح!')
            return redirect('reception:lab_tests_settings')
            
        except Exception as e:
            messages.error(request, f'❌ حدث خطأ أثناء إضافة التحليل: {str(e)}')
    
    context = {
        'page_title': 'إضافة تحليل جديد',
        'active_tab': 'lab_tests',
        'sample_type_choices': LabTest.SAMPLE_TYPE_CHOICES,
        'result_type_choices': LabTest.RESULT_TYPE_CHOICES,
        'categories': LabTest.objects.values_list('category', flat=True)
                        .distinct()
                        .exclude(category__isnull=True)
                        .exclude(category='')
                        .order_by('category'),
    }
    
    return render(request, 'reception/settings/add_lab_test.html', context)

@login_required
def edit_lab_test(request, test_id):
    """تعديل تحليل"""
    lab_test = get_object_or_404(LabTest, id=test_id)
    
    if request.method == 'POST':
        try:
            # التحقق من الكود إذا تم تغييره
            new_code = request.POST.get('code', '').strip()
            if new_code != lab_test.code and LabTest.objects.filter(code=new_code).exists():
                messages.error(request, f'❌ كود التحليل "{new_code}" موجود مسبقاً!')
                return redirect('reception:edit_lab_test', test_id=test_id)
            
            # تحديث البيانات
            lab_test.name = request.POST.get('name', '').strip()
            lab_test.name_ar = request.POST.get('name_ar', '').strip()
            lab_test.code = new_code
            lab_test.result_type = request.POST.get('result_type', 'numerical')
            lab_test.sample_type = request.POST.get('sample_type', 'blood')
            lab_test.unit = request.POST.get('unit', '').strip()
            lab_test.standard_price = float(request.POST.get('standard_price', 0) or 0)
            lab_test.cost = float(request.POST.get('cost', 0) or 0)
            lab_test.turnaround_time = request.POST.get('turnaround_time', '24 ساعة').strip()
            lab_test.description = request.POST.get('description', '').strip()
            lab_test.instructions = request.POST.get('instructions', '').strip()
            lab_test.category = request.POST.get('category', '').strip()
            lab_test.normal_range = request.POST.get('normal_range', '').strip()
            lab_test.is_active = request.POST.get('is_active') == 'on'
            
            lab_test.save()
            
            messages.success(request, f'✅ تم تعديل التحليل "{lab_test.name_ar}" بنجاح!')
            return redirect('reception:lab_tests_settings')
            
        except Exception as e:
            messages.error(request, f'❌ حدث خطأ أثناء تعديل التحليل: {str(e)}')
    
    context = {
        'page_title': f'تعديل التحليل - {lab_test.name_ar}',
        'lab_test': lab_test,
        'active_tab': 'lab_tests',
        'sample_type_choices': LabTest.SAMPLE_TYPE_CHOICES,
        'result_type_choices': LabTest.RESULT_TYPE_CHOICES,
        'categories': LabTest.objects.values_list('category', flat=True)
                        .distinct()
                        .exclude(category__isnull=True)
                        .exclude(category='')
                        .order_by('category'),
    }
    
    return render(request, 'reception/settings/edit_lab_test.html', context)

@login_required
def toggle_lab_test_status(request, test_id):
    """تفعيل/تعطيل تحليل"""
    lab_test = get_object_or_404(LabTest, id=test_id)
    
    try:
        lab_test.is_active = not lab_test.is_active
        lab_test.save()
        
        status = "تفعيل" if lab_test.is_active else "تعطيل"
        messages.success(request, f'✅ تم {status} التحليل "{lab_test.name_ar}" بنجاح!')
        
    except Exception as e:
        messages.error(request, f'❌ حدث خطأ أثناء تغيير حالة التحليل: {str(e)}')
    
    return redirect('reception:lab_tests_settings')

@login_required
def delete_lab_test(request, test_id):
    """حذف تحليل"""
    lab_test = get_object_or_404(LabTest, id=test_id)
    
    try:
        # التحقق من عدم استخدام التحليل في أي طلبات
        used_in_orders = OrderDetail.objects.filter(lab_test=lab_test).exists()
        
        if used_in_orders:
            messages.error(request, f'❌ لا يمكن حذف التحليل "{lab_test.name_ar}" لأنه مستخدم في طلبات سابقة.')
        else:
            test_name = lab_test.name_ar
            lab_test.delete()
            messages.success(request, f'✅ تم حذف التحليل "{test_name}" بنجاح!')
            
    except Exception as e:
        messages.error(request, f'❌ حدث خطأ أثناء حذف التحليل: {str(e)}')
    
    return redirect('reception:lab_tests_settings')

@login_required
def export_lab_tests(request):
    """تصدير قائمة التحاليل (PDF)"""
    lab_tests = LabTest.objects.all().order_by('category', 'name_ar')
    
    # إنشاء buffer للـ PDF
    buffer = io.BytesIO()
    
    # إنشاء مستند PDF
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # عنوان التقرير
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=16,
        alignment=TA_CENTER,
        spaceAfter=20
    )
    
    title_text = arabic_reshaper.reshape("قائمة التحاليل المخبرية")
    title_bidi = get_display(title_text)
    elements.append(Paragraph(title_bidi, title_style))
    
    # معلومات التقرير
    info_text = arabic_reshaper.reshape(f"تاريخ التصدير: {timezone.now().strftime('%Y-%m-%d %H:%M')} | إجمالي التحاليل: {lab_tests.count()}")
    info_bidi = get_display(info_text)
    elements.append(Paragraph(info_bidi, styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # جدول التحاليل
    table_data = []
    
    # رأس الجدول
    headers = ["#", "الاسم العربي", "الكود", "الفئة", "نوع العينة", "السعر", "الحالة"]
    arabic_headers = []
    for header in headers:
        reshaped = arabic_reshaper.reshape(header)
        bidi = get_display(reshaped)
        arabic_headers.append(Paragraph(bidi, styles['Normal']))
    
    table_data.append(arabic_headers)
    
    # بيانات الجدول
    for idx, test in enumerate(lab_tests, 1):
        # تحويل النصوص للعربية
        name_ar = get_display(arabic_reshaper.reshape(test.name_ar))
        code = test.code
        category = get_display(arabic_reshaper.reshape(test.category or "-"))
        sample_type = get_display(arabic_reshaper.reshape(test.get_sample_type_display()))
        price = f"{test.standard_price} د.ع"
        status = "نشط" if test.is_active else "غير نشط"
        status_text = get_display(arabic_reshaper.reshape(status))
        
        row = [
            Paragraph(str(idx), styles['Normal']),
            Paragraph(name_ar, styles['Normal']),
            Paragraph(code, styles['Normal']),
            Paragraph(category, styles['Normal']),
            Paragraph(sample_type, styles['Normal']),
            Paragraph(price, styles['Normal']),
            Paragraph(status_text, styles['Normal']),
        ]
        
        table_data.append(row)
    
    # إنشاء الجدول
    test_table = Table(table_data, colWidths=[1*cm, 6*cm, 3*cm, 3*cm, 3*cm, 3*cm, 2.5*cm])
    test_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ]))
    
    elements.append(test_table)
    
    # بناء PDF
    doc.build(elements)
    
    # إرجاع الملف
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="lab_tests_export_{timezone.now().strftime("%Y%m%d_%H%M")}.pdf"'
    
    return response

@login_required
def system_settings(request):
    """إعدادات النظام (مستقبلاً)"""
    context = {
        'page_title': 'إعدادات النظام',
        'active_tab': 'system',
    }
    return render(request, 'reception/settings/system_settings.html', context)

@login_required
def lab_settings(request):
    """إعدادات المختبر (مستقبلاً)"""
    context = {
        'page_title': 'إعدادات المختبر',
        'active_tab': 'lab',
    }
    return render(request, 'reception/settings/lab_settings.html', context)