# voting/admin.py

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from .models import *

# ------------------------------------------------------------------
# Inline Classes
# ------------------------------------------------------------------
class CandidateUserInline(admin.TabularInline):
    """Inline for displaying a user's candidacy (used in UserAdmin)."""
    model = Candidate
    fk_name = 'user'
    extra = 0
    fields = ('election', 'position', 'party', 'verified', 'missing_marks', 'supplementary_exams', 'withdrawn')
    raw_id_fields = ('election',)
    show_change_link = True

class CandidateElectionInline(admin.TabularInline):
    """Inline for displaying candidates in an election (used in ElectionAdmin)."""
    model = Candidate
    fk_name = 'election'
    extra = 0
    fields = ('user', 'position', 'party', 'verified', 'missing_marks', 'supplementary_exams', 'withdrawn')
    raw_id_fields = ('user',)
    show_change_link = True

class VoterStatusInline(admin.TabularInline):
    model = VoterStatus
    extra = 0
    fields = ('user', 'has_voted', 'vote_receipt', 'voted_at')
    readonly_fields = ('voted_at',)
    raw_id_fields = ('user',)

class VoteInline(admin.TabularInline):
    model = Vote
    extra = 0
    fields = ('receipt_id', 'timestamp')
    readonly_fields = ('receipt_id', 'timestamp')
    can_delete = False

class NotificationInline(admin.TabularInline):
    model = Notification
    extra = 0
    fields = ('subject', 'sent_via_email', 'sent_via_sms', 'created_at')
    readonly_fields = ('created_at',)

class FeedbackInline(admin.TabularInline):
    """Inline for displaying feedback in UserAdmin or ElectionAdmin."""
    model = Feedback
    extra = 0
    fields = ('election', 'rating', 'comment', 'created_at')
    readonly_fields = ('created_at',)

class VoteTimelineInline(admin.TabularInline):
    """Inline for displaying vote timeline in ElectionAdmin."""
    model = VoteTimeline
    extra = 0
    fields = ('timestamp', 'candidate_id', 'position_id')
    readonly_fields = ('timestamp',)
    can_delete = False

# ------------------------------------------------------------------
# User Admin (Custom User Model)
# ------------------------------------------------------------------
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'voter_id', 'role', 'is_verified', 'created_at')
    list_filter = ('role', 'is_verified', 'school', 'department', 'created_at')
    search_fields = ('username', 'email', 'voter_id', 'admission_number', 'phone')
    readonly_fields = ('voter_id', 'created_at', 'updated_at')
    fieldsets = (
        ('Personal Info', {
            'fields': ('username', 'first_name', 'last_name', 'email', 'phone', 'voter_id')
        }),
        ('Role & Verification', {
            'fields': ('role', 'is_verified', 'security_question', 'security_answer')
        }),
        ('Identification', {
            'fields': ('id_type', 'id_photo', 'face_embedding')
        }),
        ('Student Info (if voter)', {
            'fields': ('admission_number', 'course', 'year_of_study', 'school', 'department', 'residence', 'polling_station')
        }),
        ('Staff Info (if polling officer)', {
            'fields': ('staff_id', 'department_work')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    inlines = [CandidateUserInline, VoterStatusInline, NotificationInline, FeedbackInline]
    actions = ['verify_users', 'unverify_users']

    def verify_users(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(request, f'{updated} users marked as verified.')
    verify_users.short_description = "Verify selected users"

    def unverify_users(self, request, queryset):
        updated = queryset.update(is_verified=False)
        self.message_user(request, f'{updated} users unverified.')
    unverify_users.short_description = "Unverify selected users"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('school', 'department')

admin.site.register(User, UserAdmin)

# ------------------------------------------------------------------
# School & Department
# ------------------------------------------------------------------
class DepartmentInline(admin.TabularInline):
    model = Department
    extra = 1
    fields = ('name',)

class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name', 'code')
    inlines = [DepartmentInline]

admin.site.register(School, SchoolAdmin)

class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'school')
    list_filter = ('school',)
    search_fields = ('name', 'school__name')
    raw_id_fields = ('school',)

admin.site.register(Department, DepartmentAdmin)

# ------------------------------------------------------------------
# Position
# ------------------------------------------------------------------
class PositionAdmin(admin.ModelAdmin):
    list_display = ('name', 'school', 'department')
    list_filter = ('school', 'department')
    search_fields = ('name',)
    raw_id_fields = ('school', 'department')

admin.site.register(Position, PositionAdmin)

# ------------------------------------------------------------------
# Party
# ------------------------------------------------------------------
class PartyAdmin(admin.ModelAdmin):
    list_display = ('name', 'abbreviation', 'color', 'logo_preview')
    search_fields = ('name', 'abbreviation')
    list_filter = ('color',)

    def logo_preview(self, obj):
        if obj.logo:
            return format_html('<img src="{}" width="50" height="50" />', obj.logo.url)
        return "No logo"
    logo_preview.short_description = "Logo"

admin.site.register(Party, PartyAdmin)

# ------------------------------------------------------------------
# Election
# ------------------------------------------------------------------
class ElectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_time', 'end_time', 'is_active', 'tally_method', 'status')
    list_filter = ('is_active', 'tally_method', 'start_time')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'description', 'start_time', 'end_time', 'is_active', 'tally_method')
        }),
        ('Cryptography', {
            'fields': ('public_key', 'private_key_encrypted'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    inlines = [CandidateElectionInline, VoterStatusInline, VoteInline, FeedbackInline, VoteTimelineInline]
    actions = ['activate_election', 'deactivate_election']

    def status(self, obj):
        now = timezone.now()
        if obj.start_time > now:
            return format_html('<span style="color: orange;">Upcoming</span>')
        elif obj.start_time <= now <= obj.end_time:
            return format_html('<span style="color: green;">Ongoing</span>')
        else:
            return format_html('<span style="color: red;">Closed</span>')
    status.short_description = "Status"

    def activate_election(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, "Selected elections activated.")
    activate_election.short_description = "Activate selected elections"

    def deactivate_election(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, "Selected elections deactivated.")
    deactivate_election.short_description = "Deactivate selected elections"

admin.site.register(Election, ElectionAdmin)

# ------------------------------------------------------------------
# Candidate
# ------------------------------------------------------------------
class CandidateAdmin(admin.ModelAdmin):
    list_display = ('user', 'election', 'position', 'party', 'verified', 'withdrawn', 'missing_marks', 'supplementary_exams')
    list_filter = ('verified', 'withdrawn', 'missing_marks', 'supplementary_exams', 'election', 'position')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'user__admission_number')
    raw_id_fields = ('user', 'election', 'position', 'party', 'verified_by')
    readonly_fields = ('verified_at',)
    actions = ['verify_candidates', 'mark_missing_marks', 'mark_supplementary', 'mark_withdrawn']

    def verify_candidates(self, request, queryset):
        queryset.update(verified=True, verified_by=request.user, verified_at=timezone.now())
        self.message_user(request, f"{queryset.count()} candidates verified.")
    verify_candidates.short_description = "Verify selected candidates"

    def mark_missing_marks(self, request, queryset):
        queryset.update(missing_marks=True, verified=False)
        self.message_user(request, "Selected candidates marked as having missing marks.")
    mark_missing_marks.short_description = "Mark missing marks"

    def mark_supplementary(self, request, queryset):
        queryset.update(supplementary_exams=True, verified=False)
        self.message_user(request, "Selected candidates marked as having supplementary exams.")
    mark_supplementary.short_description = "Mark supplementary exams"

    def mark_withdrawn(self, request, queryset):
        queryset.update(withdrawn=True, verified=False)
        self.message_user(request, "Selected candidates marked as withdrawn.")
    mark_withdrawn.short_description = "Mark withdrawn"

admin.site.register(Candidate, CandidateAdmin)

# ------------------------------------------------------------------
# Vote
# ------------------------------------------------------------------
class VoteAdmin(admin.ModelAdmin):
    list_display = ('id', 'election', 'receipt_short', 'timestamp')
    list_filter = ('election', 'timestamp')
    search_fields = ('receipt_id',)
    readonly_fields = ('encrypted_vote', 'receipt_id', 'timestamp')
    can_delete = False

    def receipt_short(self, obj):
        return obj.receipt_id[:16] + "..."
    receipt_short.short_description = "Receipt ID"

admin.site.register(Vote, VoteAdmin)

# ------------------------------------------------------------------
# VoterStatus
# ------------------------------------------------------------------
class VoterStatusAdmin(admin.ModelAdmin):
    list_display = ('user', 'election', 'has_voted', 'voted_at')
    list_filter = ('has_voted', 'election', 'voted_at')
    search_fields = ('user__username', 'user__voter_id', 'vote_receipt')
    raw_id_fields = ('user',)
    readonly_fields = ('voted_at',)

admin.site.register(VoterStatus, VoterStatusAdmin)

# ------------------------------------------------------------------
# PollingOfficerTest
# ------------------------------------------------------------------
class PollingOfficerTestAdmin(admin.ModelAdmin):
    list_display = ('user', 'score', 'passed', 'taken_at')
    list_filter = ('passed', 'taken_at')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    readonly_fields = ('answers', 'taken_at')

admin.site.register(PollingOfficerTest, PollingOfficerTestAdmin)

# ------------------------------------------------------------------
# Notification
# ------------------------------------------------------------------
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'subject', 'sent_via_email', 'sent_via_sms', 'created_at', 'is_read')
    list_filter = ('sent_via_email', 'sent_via_sms', 'is_read', 'created_at')
    search_fields = ('user__username', 'subject', 'message')
    readonly_fields = ('created_at',)

admin.site.register(Notification, NotificationAdmin)

# ------------------------------------------------------------------
# AuditLog
# ------------------------------------------------------------------
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'ip_address', 'timestamp')
    list_filter = ('timestamp',)
    search_fields = ('user__username', 'action', 'ip_address')
    readonly_fields = ('user', 'action', 'ip_address', 'user_agent', 'timestamp', 'details')
    can_delete = True

    def has_add_permission(self, request):
        return False  # Logs are only added programmatically

admin.site.register(AuditLog, AuditLogAdmin)

# ------------------------------------------------------------------
# TallyResult
# ------------------------------------------------------------------
class TallyResultAdmin(admin.ModelAdmin):
    list_display = ('election', 'calculated_at')
    readonly_fields = ('election', 'results', 'calculated_at')

    def has_add_permission(self, request):
        return False

admin.site.register(TallyResult, TallyResultAdmin)

# ------------------------------------------------------------------
# Feedback (NEW)
# ------------------------------------------------------------------
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('user', 'election', 'rating', 'created_at')
    list_filter = ('rating', 'election', 'created_at')
    search_fields = ('user__username', 'user__email', 'comment')
    raw_id_fields = ('user', 'election')
    readonly_fields = ('created_at',)

admin.site.register(Feedback, FeedbackAdmin)

# ------------------------------------------------------------------
# VoteTimeline (NEW)
# ------------------------------------------------------------------
class VoteTimelineAdmin(admin.ModelAdmin):
    list_display = ('election', 'timestamp', 'candidate', 'position')
    list_filter = ('election', 'timestamp')
    search_fields = ('candidate_id', 'position_id')
    readonly_fields = ('timestamp',)

    def candidate(self, obj):
        try:
            return Candidate.objects.get(id=obj.candidate_id).user.get_full_name()
        except Candidate.DoesNotExist:
            return f"Candidate {obj.candidate_id}"
    candidate.short_description = "Candidate"

    def position(self, obj):
        try:
            return Position.objects.get(id=obj.position_id).name
        except Position.DoesNotExist:
            return f"Position {obj.position_id}"
    position.short_description = "Position"

admin.site.register(VoteTimeline, VoteTimelineAdmin)

# ------------------------------------------------------------------
# Custom Admin Site Header & Title
# ------------------------------------------------------------------
admin.site.site_header = "MMUST Voting System Administration"
admin.site.site_title = "MMUST Voting Admin"
admin.site.index_title = "Welcome to the Voting System Admin Panel"