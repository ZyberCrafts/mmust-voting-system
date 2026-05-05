# voting/urls.py

from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from . import views

# Custom password reset complete view
class CustomPasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    def get(self, request, *args, **kwargs):
        from django.contrib import messages
        messages.success(request, "Your password has been reset. Please log in.")
        return super().get(request, *args, **kwargs)

urlpatterns = [
    # ---------- Public pages ----------
    path('', views.landing, name='landing'),
    path('elections/', views.election_list, name='election_list'),
    path('elections/<int:election_id>/', views.election_detail, name='election_detail'),
    path('candidate/<int:candidate_id>/', views.candidate_profile, name='candidate_profile'),
    path('results/embed/<int:election_id>/', views.results_embed, name='results_embed'),

    # ---------- Authentication ----------
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('password-reset/', auth_views.PasswordResetView.as_view(template_name='voting/password_reset.html'), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='voting/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='voting/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', CustomPasswordResetCompleteView.as_view(template_name='voting/password_reset_complete.html'), name='password_reset_complete'),

    # ---------- User dashboard & profile ----------
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile, name='profile'),
    path('profile/votes/', views.voting_history, name='voting_history'),
    path('vote/receipt/', views.check_receipt, name='check_receipt'),
    path('feedback/<int:election_id>/', views.feedback, name='feedback'),
    path('profile/update-photo/', views.update_profile_photo, name='update_profile_photo'),
    
    # ---------- Candidate ----------
    path('candidate/register/', views.candidate_register, name='candidate_register'),
    path('candidate/withdraw/', views.candidate_withdraw, name='candidate_withdraw'),
    path('candidate/verify/<int:candidate_id>/', views.verify_candidate, name='verify_candidate'),
    path('candidate/questionnaire/', views.candidate_questionnaire, name='candidate_questionnaire'),
    
    # ---------- Polling officer ----------
    path('polling-officer/test/', views.polling_officer_test, name='polling_officer_test'),

    # ---------- Voting ----------
    path('vote/', views.voting_ballot, name='voting_ballot'),
    path('vote/review/', views.vote_review, name='vote_review'),
    path('admin-panel/close-election/', views.close_election, name='close_election'),
    path('vote/check/', views.vote_redirect, name='vote_check'),
    path('vote/already/', views.already_voted, name='already_voted'),
    
    # ---------- Results ----------
    path('results/', views.results, name='results'),
    path('results/<int:election_id>/', views.results_detail, name='results_detail'),
    path('export/csv/<int:election_id>/', views.export_results_csv, name='export_csv'),

    # ---------- Live & replay (public) ----------
    path('live/<int:election_id>/', views.live_turnout, name='live_turnout'),
    path('replay/<int:election_id>/', views.replay_votes, name='replay_votes'),

    # ---------- Admin panel ----------
    path('admin-panel/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-panel/verify-users/', views.verify_users, name='verify_users'),
    path('admin-panel/broadcast/', views.broadcast_notification, name='broadcast_notification'),
    path('admin-panel/audit-logs/', views.audit_logs, name='audit_logs'),
    path('admin-panel/tally/<int:election_id>/', views.tally_election, name='tally_election'),
    path('admin-panel/live-map/<int:election_id>/', views.live_map, name='live_map'),
    path('admin-panel/test-email/', views.test_email, name='test_email'),
    path('admin-panel/test-sms/', views.test_sms, name='test_sms'),
    path('admin-2fa-setup/', views.admin_2fa_setup, name='admin_2fa_setup'),
    path('admin-panel/broadcast-log/', views.broadcast_log, name='broadcast_log'),
    path('admin-panel/broadcast-log/clear/', views.clear_broadcast_log, name='clear_broadcast_log'),
    path('verify-2fa/', views.verify_2fa, name='verify_2fa'),
    
    # Admin exports
    path('admin-panel/export/voters/', views.export_voters_csv, name='export_voters_csv'),
    path('admin-panel/export/candidates/', views.export_candidates_csv, name='export_candidates_csv'),
    path('admin-panel/export/audit/', views.export_audit_csv, name='export_audit_csv'),

    # ---------- API endpoints ----------
    path('api/face/register/', views.face_register, name='face_register'),
    path('api/face/verify/', views.face_verify, name='face_verify'),
    path('api/eligibility/', views.eligibility_api, name='eligibility_api'),
    path('api/voter-locations/<int:election_id>/', views.voter_locations, name='api_voter_locations'),
    path('api/replay/<int:election_id>/', views.replay_votes, name='api_replay_votes'),
    path('api/departments/', views.get_departments, name='get_departments'),
    path('api/resend-test-reminder/', views.resend_test_reminder, name='resend_test_reminder'),
    path('api/user/status/', views.user_status_api, name='user_status_api'),
    
    path('about/', views.about_page, name='about'),
    path('contact/', views.contact_page, name='contact'),
    path('contact/submit/', views.contact_submit, name='contact_submit'),
    path('faq/', views.faq_page, name='faq'),
    path('api/stats/', views.stats_api, name='stats_api'),
    path('api/login-status/', views.login_status, name='login_status'),

    # ---------- Notifications & AJAX verification ----------
    path('api/notifications/', views.api_notifications, name='api_notifications'),
    path('api/notifications/<int:notification_id>/mark-read/', views.api_mark_notification_read, name='api_mark_notification_read'),
    path('api/notifications/mark-all-read/', views.api_mark_all_notifications_read, name='api_mark_all_notifications_read'),
    path('api/admin/elections/create/', views.create_election_ajax, name='create_election_api'),
    path('admin-panel/create-election/', views.create_election_ajax, name='create_election_ajax'),
    path('admin-panel/verify-user/<int:user_id>/', views.verify_user_ajax, name='verify_user_ajax'),
    path('admin-panel/verify-officer/<int:user_id>/', views.verify_officer_ajax, name='verify_officer_ajax'),
]

# Serve static and media files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)