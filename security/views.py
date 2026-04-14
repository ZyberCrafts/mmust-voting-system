from django.utils import timezone
from django.shortcuts import render, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from .models import AttackLog

@staff_member_required
def security_dashboard(request):
    # Get attack logs
    logs = AttackLog.objects.all().order_by('-timestamp')
    paginator = Paginator(logs, 50)
    page = request.GET.get('page')
    logs_page = paginator.get_page(page)

    # Summary statistics
    total_attacks = AttackLog.objects.count()
    by_type = AttackLog.objects.values('attack_type').annotate(cnt=Count('id')).order_by('-cnt')
    by_severity = AttackLog.objects.values('severity').annotate(cnt=Count('id')).order_by('-severity')
    today = timezone.now().date()
    today_count = AttackLog.objects.filter(timestamp__date=today).count()

    context = {
        'logs': logs_page,
        'total_attacks': total_attacks,
        'by_type': by_type,
        'by_severity': by_severity,
        'today_count': today_count,
    }
    return render(request, 'security/dashboard.html', context)

@staff_member_required
def attack_detail(request, pk):
    log = get_object_or_404(AttackLog, pk=pk)
    return render(request, 'security/attack_detail.html', {'log': log})