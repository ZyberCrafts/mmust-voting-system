import json
import logging
import csv
import qrcode
import base64
import requests
from io import BytesIO
from django.conf import settings
from security.models import AttackLog
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db import models
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import send_mail
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .utils import get_active_election
from django_otp.plugins.otp_totp.models import TOTPDevice
from .models import *
from .forms import *
from .utils import (
    encrypt_vote, generate_receipt, send_notification,
    check_candidate_eligibility, get_election_public_key,
    store_face_embedding, verify_face, decrypt_vote, tally_votes,
    log_audit
)
from .decorators import role_required, admin_required

logger = logging.getLogger(__name__)

# ---------- Helper functions ----------
def get_client_ip(request):
    """Extract client IP from request, respecting proxies."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def get_location_from_ip(ip):
    """Return (latitude, longitude) for given IP using ipapi.co."""
    try:
        response = requests.get(f'https://ipapi.co/{ip}/json/', timeout=5)
        data = response.json()
        return data.get('latitude'), data.get('longitude')
    except Exception:
        return None, None
from django_ratelimit.decorators import ratelimit

@ratelimit(key='ip', rate='5/m', method='POST')
def login_view(request):
    # Check if rate limit was exceeded
    if getattr(request, 'limited', False):
        messages.error(request, "Too many login attempts. Try later.")
        return render(request, 'voting/login.html')

    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        security_answer = request.POST.get('security_answer', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            # Admin security code check
            if user.is_staff:
                if not security_answer or security_answer.lower() != 'mmust':
                    messages.error(request, "Invalid security code for admin access.")
                    return render(request, 'voting/login.html')

                # 2FA: check if the user has a confirmed TOTP device
                device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
                if device:
                    # Store user ID in session and redirect to 2FA verification
                    request.session['pre_2fa_user_id'] = user.id
                    return redirect('verify_2fa')
                else:
                    # No TOTP device – redirect to 2FA setup (first time)
                    request.session['pre_2fa_user_id'] = user.id
                    return redirect('admin_2fa_setup')

            else:
                # Regular users: ask security answer only if voting is ongoing
                election = get_active_election()
                if election and election.is_ongoing():
                    if not security_answer or security_answer.lower() != user.security_answer.lower():
                        messages.error(request, "Incorrect security answer for voting period.")
                        return render(request, 'voting/login.html')
                # No 2FA for regular users – log in immediately
                login(request, user)
                # Remember me functionality
                if request.POST.get('remember_me'):
                    request.session.set_expiry(1209600)
                else:
                    request.session.set_expiry(0)
                return redirect('dashboard')
        else:
            messages.error(request, "Invalid username or password.")
    return render(request, 'voting/login.html')

def landing(request):
    """Public landing page."""
    # If user is already logged in, redirect to dashboard
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'voting/landing.html')

@login_required
def send_page_email(request):
    if request.method == 'POST':
        page = request.POST.get('page')
        # fetch data for that page
        # send email to request.user.email
        return JsonResponse({'status': 'ok'})

@login_required
@role_required(['polling_officer'])
def resend_test_reminder(request):
    if request.method == 'POST':
        send_notification(request.user, "Polling Officer Test Reminder", 
                         "Please complete your qualification test for the upcoming election. Visit the test page now.",
                         send_email=True, send_sms=False)
        return JsonResponse({'success': True})
    return JsonResponse({'success': False}, status=400)

def get_departments(request):
    school_id = request.GET.get('school_id')
    if school_id:
        departments = Department.objects.filter(school_id=school_id).values('id', 'name')
        return JsonResponse(list(departments), safe=False)
    return JsonResponse([], safe=False)

def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('login')

# ---------- Registration ----------
def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_verified = False
            user.save()
            # Auto‑approve if admission number matches COM/B/01-00xxx/2022 pattern
            import re
            pattern = r'^COM/B/01-00(\d{3})/2022$'  # expects 3 digits after 00
            if re.match(pattern, user.admission_number):
                user.is_verified = True
                user.save()
                # Optionally send a welcome notification
                send_notification(user, "Account Auto‑Verified", "Your account has been automatically verified. You can now vote.")      
            face_data = request.POST.get('face_data')
            if face_data:
                store_face_embedding(user, face_data)
            messages.success(request, "Registration successful. Wait for verification.")
            return redirect('login')
        else:
            # Log errors to the console for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Form errors: {form.errors.as_json()}")
            # Also print to terminal
            print("Form errors:", form.errors)
    else:
        form = UserRegistrationForm()
    return render(request, 'voting/register.html', {'form': form})

# ---------- Dashboard ----------
@login_required
def dashboard(request):
    user = request.user
    active_election = get_active_election()
    context = {'user': user, 'election': active_election}
    context['is_leader'] = hasattr(user, 'candidacy') and user.candidacy.is_winner
    if user.role == 'candidate' and hasattr(user, 'candidacy'):
        context['candidacy'] = user.candidacy
    elif user.role == 'polling_officer':
        context['test'] = PollingOfficerTest.objects.filter(user=user).first()
    context['notifications'] = Notification.objects.filter(user=user, is_read=False)[:10]

    # Add live turnout if election is ongoing
    if active_election and active_election.is_ongoing():
        voted_count = VoterStatus.objects.filter(election=active_election, has_voted=True).count()
        total_voters = User.objects.filter(role='voter', is_verified=True).count()
        context['live_turnout'] = voted_count
        context['total_voters'] = total_voters

    return render(request, 'voting/dashboard.html', context)

# ---------- Candidate Registration ----------
@login_required
@role_required(['candidate'])
def candidate_register(request):
    if hasattr(request.user, 'candidacy'):
        messages.warning(request, "You already have a candidacy.")
        return redirect('dashboard')
    election = get_active_election()
    if not election:
        messages.error(request, "No active election.")
        return redirect('dashboard')
    if request.method == 'POST':
        form = CandidateRegistrationForm(request.POST, request.FILES, election=election, user=request.user)
        if form.is_valid():
            candidate = form.save(commit=False)
            candidate.user = request.user
            candidate.election = election

            # Check eligibility
            eligible = check_candidate_eligibility(request.user.admission_number)
            if eligible is None:
                candidate.eligibility_pending = True
                messages.warning(request, "Automatic eligibility check failed. Admin will verify your academic status manually.")
            elif eligible is False:
                messages.error(request, "You are not eligible due to academic issues.")
                return redirect('candidate_register')
            else:
                candidate.eligibility_pending = False

            candidate.save()

            # Save candidate_metadata from form
            candidate.candidate_metadata = form.cleaned_data.get('candidate_metadata', {})
            candidate.save()

            # Save party certificate if uploaded
            if request.FILES.get('party_certificate'):
                candidate.party_nomination_certificate = request.FILES['party_certificate']
                candidate.save()

            messages.success(request, "Candidate registered successfully! Please complete the questionnaire.")
            return redirect('candidate_questionnaire')
        else:
            # Print errors to console for debugging
            print("Form errors:", form.errors)
            messages.error(request, "Please correct the errors below.")
    else:
        positions = Position.objects.filter(
            models.Q(school=request.user.school) | models.Q(school__isnull=True),
            models.Q(department=request.user.department) | models.Q(department__isnull=True)
        )
        form = CandidateRegistrationForm(election=election, user=request.user)
        form.fields['position'].queryset = positions

    # Prepare positions JSON with allowed genders based on position name
    positions_qs = Position.objects.filter(
        models.Q(school=request.user.school) | models.Q(school__isnull=True),
        models.Q(department=request.user.department) | models.Q(department__isnull=True)
    )
    positions_list = []
    for p in positions_qs:
        allowed = []
        if 'Hall' in p.name or 'School Representative' in p.name or 'Non-resident' in p.name:
            if 'Male' in p.name:
                allowed = ['male']
            elif 'Female' in p.name:
                allowed = ['female']
            else:
                # For generic positions, allow both
                allowed = ['male', 'female']
        elif p.name == 'President (Party Ticket)':
            allowed = ['male', 'female']
        else:
            allowed = ['male', 'female']
        positions_list.append({
            'id': p.id,
            'name': p.name,
            'type': (
                'president' if p.name == 'President (Party Ticket)'
                else 'hall' if 'Hall' in p.name
                else 'school' if 'School Representative' in p.name
                else 'nonresident' if 'Non-resident' in p.name
                else 'other'
            ),
            'allowed_genders': allowed
        })

    # Prepare parties JSON with slogan and term
    parties_qs = Party.objects.all()
    parties_list = []
    for p in parties_qs:
        parties_list.append({
            'id': p.id,
            'name': p.name,
            'logo': p.logo.url if p.logo else '',
            'slogan': p.slogan,
            'term': p.term,
        })

    import json
    positions_json = json.dumps(positions_list)
    parties_json = json.dumps(parties_list)

    # Add parties to the context (original)
    parties = Party.objects.all()
    context = {
        'form': form,
        'parties': parties,
        'positions_json': positions_json,
        'parties_json': parties_json,
    }
    return render(request, 'voting/candidate_register.html', context)

@login_required
@admin_required
def verify_candidate(request, candidate_id):
    candidate = get_object_or_404(Candidate, id=candidate_id)
    if request.method == 'POST':
        form = CandidateVerificationForm(request.POST, instance=candidate)
        if form.is_valid():
            form.save()
            messages.success(request, f"Candidate {candidate.user.get_full_name()} updated.")
            return redirect('admin_dashboard')
    else:
        form = CandidateVerificationForm(instance=candidate)
    return render(request, 'voting/verify_candidate.html', {'form': form, 'candidate': candidate})

# ---------- Polling Officer Test ----------
@login_required
@role_required(['polling_officer'])
def polling_officer_test(request):
    if PollingOfficerTest.objects.filter(user=request.user).exists():
        messages.warning(request, "You already took the test.")
        return redirect('dashboard')
    if request.method == 'POST':
        form = PollingOfficerTestForm(request.POST)
        if form.is_valid():
            score, answers = form.grade()
            passed = score >= 80
            test = PollingOfficerTest.objects.create(
                user=request.user, score=score, passed=passed, answers=answers
            )
            if passed:
                messages.success(request, f"Test passed! Score: {score}%.")
            else:
                messages.error(request, f"Test failed. Score: {score}%.")
            return redirect('dashboard')
    else:
        form = PollingOfficerTestForm()
    return render(request, 'voting/polling_officer_test.html', {'form': form})

# ---------- Voting Process ----------
@login_required
def voting_ballot(request):
    user = request.user
    election = get_active_election()
    if not election or not election.is_ongoing():
        messages.error(request, "Voting is not open.")
        return redirect('dashboard')
    voter_status, _ = VoterStatus.objects.get_or_create(user=user, election=election)
    if voter_status.has_voted:
        messages.warning(request, "You have already voted.")
        return redirect('dashboard')
    positions = Position.objects.filter(
        models.Q(school=user.school) | models.Q(school__isnull=True),
        models.Q(department=user.department) | models.Q(department__isnull=True)
    ).distinct()
    candidates_by_position = {}
    for pos in positions:
        # Special handling for "President (Party Ticket)" position
        if pos.name == "President (Party Ticket)":
            # Get all parties that have at least one verified candidate for this position
            parties_with_candidates = Party.objects.filter(
                candidate__position=pos,
                candidate__election=election,
                candidate__verified=True
            ).distinct()
            # Treat each party as a "candidate" with a negative ID to avoid collision with real candidate IDs
            candidates_by_position[pos] = [
                {
                    'id': -p.id,           # negative ID signals party vote
                    'name': p.name,
                    'logo': p.logo.url if p.logo else None
                }
                for p in parties_with_candidates
            ]
        else:
            candidates_by_position[pos] = Candidate.objects.filter(
                position=pos, verified=True, election=election
            )
    if request.method == 'POST':
        vote_data = {}
        for pos in positions:
            selected = request.POST.get(f'position_{pos.id}')
            if selected:
                # For party-based position, store party ID (negative); otherwise candidate ID
                vote_data[pos.id] = int(selected)
            else:
                vote_data[pos.id] = None
        request.session['pending_vote'] = vote_data
        request.session['pending_election_id'] = election.id
        return redirect('vote_review')
    return render(request, 'voting/ballot.html', {
        'election': election,
        'candidates_by_position': candidates_by_position,
    })

@login_required
def vote_review(request):
    election_id = request.session.get('pending_election_id')
    election = get_object_or_404(Election, id=election_id) if election_id else None
    if not election or not election.is_ongoing():
        messages.error(request, "Invalid session.")
        return redirect('dashboard')
    pending_vote = request.session.get('pending_vote')
    if not pending_vote:
        return redirect('voting_ballot')
    positions = Position.objects.filter(id__in=pending_vote.keys())
    selected = {}
    for pos in positions:
        cid = pending_vote.get(str(pos.id))
        if cid:
            selected[pos] = get_object_or_404(Candidate, id=cid)

    if request.method == 'POST':
        vote_str = json.dumps(pending_vote)
        public_key = get_election_public_key(election)
        encrypted = encrypt_vote(vote_str, public_key)
        receipt = generate_receipt(encrypted, request.user.id)
        Vote.objects.create(election=election, encrypted_vote=encrypted, receipt_id=receipt)

        # Record timeline for replay
        for pos_id, cand_id in pending_vote.items():
            if cand_id:
                VoteTimeline.objects.create(
                    election=election,
                    candidate_id=cand_id,
                    position_id=pos_id
                )

        # IP & Location Capture
        ip = get_client_ip(request)
        lat, lon = get_location_from_ip(ip)

        voter_status, _ = VoterStatus.objects.get_or_create(user=request.user, election=election)
        voter_status.has_voted = True
        voter_status.vote_receipt = receipt
        voter_status.voted_at = timezone.now()
        voter_status.ip_address = ip
        voter_status.latitude = lat
        voter_status.longitude = lon
        voter_status.save()

        # WebSocket live update
        voted_count = VoterStatus.objects.filter(election=election, has_voted=True).count()
        total_voters = VoterStatus.objects.filter(election=election).count()
        turnout = (voted_count / total_voters * 100) if total_voters > 0 else 0

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'live_tracking_{election.id}',
            {
                'type': 'vote_update',
                'data': {
                    'voted': voted_count,
                    'turnout': round(turnout, 2),
                    'candidates': {},
                }
            }
        )

        del request.session['pending_vote']
        del request.session['pending_election_id']
        send_notification(request.user, "Vote Confirmation", f"Receipt: {receipt}", True, False)
        messages.success(request, "Your vote has been recorded.")
        return redirect('feedback', election_id=election.id)   # redirect to feedback page

    return render(request, 'voting/review.html', {'selected': selected})

# ---------- Feedback ----------
@login_required
def feedback(request, election_id):
    if request.method == 'POST':
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback = form.save(commit=False)
            feedback.user = request.user
            feedback.election_id = election_id
            feedback.save()

            # Send thank‑you email
            send_mail(
                'Thank you for your feedback',
                'Thank you for participating in the MMUST Voting System. Your feedback helps us improve.',
                settings.EMAIL_HOST_USER,
                [request.user.email],
                fail_silently=True,
            )

            messages.success(request, "Thank you for your feedback!")
            return redirect('dashboard')
    else:
        form = FeedbackForm()
    return render(request, 'voting/feedback.html', {'form': form, 'election_id': election_id})

# ---------- Map & QR ----------
@login_required
@admin_required
def live_map(request, election_id):
    election = get_object_or_404(Election, id=election_id)
    return render(request, 'voting/live_map.html', {'election': election})

@login_required
@admin_required
def voter_locations(request, election_id):
    """API endpoint returning aggregated voter coordinates for heatmap."""
    locations = VoterStatus.objects.filter(
        election_id=election_id
    ).exclude(latitude__isnull=True).values('latitude', 'longitude')
    # Aggregate by rounding to 3 decimal places (~100m precision)
    agg = {}
    for loc in locations:
        lat = round(loc['latitude'], 3)
        lon = round(loc['longitude'], 3)
        key = (lat, lon)
        agg[key] = agg.get(key, 0) + 1
    result = [{'lat': lat, 'lon': lon, 'count': count} for (lat, lon), count in agg.items()]
    return JsonResponse(result, safe=False)

@login_required
def check_receipt(request):
    qr_base64 = None
    if request.method == 'POST':
        receipt_id = request.POST.get('receipt_id')
        try:
            vote = Vote.objects.get(receipt_id=receipt_id)
            qr = qrcode.make(receipt_id)
            buffer = BytesIO()
            qr.save(buffer, format='PNG')
            qr_base64 = base64.b64encode(buffer.getvalue()).decode()
            messages.success(request, "Your vote is recorded.")
        except Vote.DoesNotExist:
            messages.error(request, "Receipt not found.")
    return render(request, 'voting/check_receipt.html', {'qr_base64': qr_base64})

# ---------- Results ----------
@login_required
def results(request):
    election = Election.objects.filter(end_time__lt=timezone.now()).order_by('-end_time').first()
    if not election:
        messages.warning(request, "No completed elections.")
        return redirect('dashboard')
    try:
        tally = TallyResult.objects.get(election=election)
        results_data = tally.results
    except TallyResult.DoesNotExist:
        results_data = {}
    return render(request, 'voting/results.html', {'election': election, 'results': results_data})

def results_detail(request, election_id):
    election = get_object_or_404(Election, id=election_id)
    if election.is_ongoing() or election.is_upcoming():
        messages.warning(request, "Results not available yet.")
        return redirect('results')
    try:
        tally = TallyResult.objects.get(election=election)
        results_data = tally.results
    except TallyResult.DoesNotExist:
        results_data = {}

    # Build maps for template
    candidate_map = {c.id: c.user.get_full_name() for c in Candidate.objects.filter(election=election)}
    position_map = {p.id: p.name for p in Position.objects.all()}

    return render(request, 'voting/results_detail.html', {
        'election': election,
        'results': results_data,
        'candidate_map': candidate_map,
        'position_map': position_map,
    })

def results_embed(request, election_id):
    election = get_object_or_404(Election, id=election_id)
    if not election.is_closed():
        return HttpResponse("Results not available yet.", status=403)
    try:
        tally = TallyResult.objects.get(election=election)
        results_data = tally.results   # {position_id: {candidate_id: {'name':..., 'party':..., 'votes':...}}}
    except TallyResult.DoesNotExist:
        results_data = {}

    # Build structured list for template
    results_by_position = []
    chart_data = []
    positions = Position.objects.filter(id__in=results_data.keys()).in_bulk()
    for pos_id, cands in results_data.items():
        position = positions.get(int(pos_id))
        if not position:
            continue
        total_votes = sum(c['votes'] for c in cands.values())
        candidates_list = []
        labels = []
        votes_list = []
        for cand_id, data in cands.items():
            candidates_list.append({
                'name': data['name'],
                'party': data['party'],
                'votes': data['votes'],
            })
            labels.append(data['name'])
            votes_list.append(data['votes'])
        results_by_position.append({
            'name': position.name,
            'total_votes': total_votes,
            'candidates': candidates_list,
        })
        chart_data.append({'labels': labels, 'votes': votes_list})

    import json
    results_chart_data = json.dumps(chart_data)

    return render(request, 'voting/results_embed.html', {
        'election': election,
        'results_by_position': results_by_position,
        'results_chart_data': results_chart_data,
    })
    
def live_turnout(request, election_id):
    """Public page showing real‑time turnout via WebSocket."""
    election = get_object_or_404(Election, id=election_id)
    total_voters = User.objects.filter(role='voter', is_verified=True).count()
    context = {
        'election': election,
        'total_voters': total_voters,
    }
    return render(request, 'voting/live_turnout.html', context)

# ---------- CSV Export ----------
@login_required
@admin_required
def export_results_csv(request, election_id):
    election = get_object_or_404(Election, id=election_id)
    tally = TallyResult.objects.get(election=election)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{election.name}_results.csv"'
    writer = csv.writer(response)
    writer.writerow(['Position', 'Candidate', 'Party', 'Votes'])
    for pos_id, cands in tally.results.items():
        position = Position.objects.get(id=pos_id)
        for cand_id, data in cands.items():
            candidate = Candidate.objects.get(id=cand_id)
            writer.writerow([position.name, data['name'], data['party'], data['votes']])
    return response

# ---------- Replay ----------
def replay_votes(request, election_id):
    """Return the vote timeline for replay (API) and also render a page."""
    election = get_object_or_404(Election, id=election_id)
    if not election.is_closed():
        messages.warning(request, "Election not closed yet.")
        return redirect('results')
    if request.method == 'GET' and 'json' in request.GET:
        timeline = VoteTimeline.objects.filter(election=election).order_by('timestamp')
        
        # Get candidate and position name mappings
        candidate_ids = list(set([v.candidate_id for v in timeline]))
        candidates = Candidate.objects.filter(id__in=candidate_ids).select_related('user')
        candidate_name_map = {c.id: c.user.get_full_name() for c in candidates}
        
        position_ids = list(set([v.position_id for v in timeline]))
        positions = Position.objects.filter(id__in=position_ids)
        position_name_map = {p.id: p.name for p in positions}
        
        # Build data with names
        data = []
        for t in timeline:
            data.append({
                'time': t.timestamp.isoformat(),
                'candidate': t.candidate_id,
                'candidate_name': candidate_name_map.get(t.candidate_id, f"Candidate {t.candidate_id}"),
                'position': t.position_id,
                'position_name': position_name_map.get(t.position_id, f"Position {t.position_id}"),
            })
        return JsonResponse(data, safe=False)
    return render(request, 'voting/replay.html', {'election': election})

# ---------- Face Recognition APIs ----------
@csrf_exempt
@login_required
def face_register(request):
    if request.method == 'POST':
        image_data = request.POST.get('image')
        if image_data:
            success = store_face_embedding(request.user, image_data)
            return JsonResponse({'success': success})
    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
@login_required
def face_verify(request):
    if request.method == 'POST':
        image_data = request.POST.get('image')
        if image_data and request.user.face_embedding:
            match = verify_face(request.user.face_embedding, image_data)
            return JsonResponse({'match': match})
    return JsonResponse({'error': 'Invalid request'}, status=400)

# ---------- Election List & Detail ----------
def election_list(request):
    elections = Election.objects.all().order_by('-start_time')
    return render(request, 'voting/election_list.html', {'elections': elections})

def election_detail(request, election_id):
    election = get_object_or_404(Election, id=election_id)
    candidates = Candidate.objects.filter(election=election, verified=True).select_related('user', 'position', 'party')
    return render(request, 'voting/election_detail.html', {'election': election, 'candidates': candidates})

# ---------- Admin Views ----------
@login_required
@admin_required
def admin_dashboard(request):
    total_voters = User.objects.filter(role='voter').count()
    total_candidates = Candidate.objects.filter(verified=True).count()
    pending = User.objects.filter(is_verified=False).count()
    active = get_active_election()
    votes_cast = VoterStatus.objects.filter(election=active, has_voted=True).count() if active else 0
    recent_logs = AuditLog.objects.all().order_by('-timestamp')[:5]
    return render(request, 'voting/admin_dashboard.html', {
        'total_voters': total_voters,
        'total_candidates': total_candidates,
        'pending_verifications': pending,
        'active_election': active,
        'votes_cast': votes_cast,
        'recent_logs': recent_logs,
    })

@login_required
@admin_required
def broadcast_notification(request):
    print("=== BROADCAST VIEW CALLED ===")   # debug
    if request.method == 'POST':
        form = BroadcastNotificationForm(request.POST)
        print("Form data:", request.POST)    # debug
        if form.is_valid():
            print("Form is valid")           # debug
            subject = form.cleaned_data['subject']
            message = form.cleaned_data['message']
            send_to = form.cleaned_data['send_to']
            via_email = form.cleaned_data['via_email']
            via_sms = form.cleaned_data['via_sms']

            if send_to == 'all':
                users = User.objects.all()
            elif send_to == 'voters':
                users = User.objects.filter(role='voter')
            elif send_to == 'candidates':
                users = User.objects.filter(role='candidate')
            elif send_to == 'polling_officers':
                users = User.objects.filter(role='polling_officer')
            else:
                users = User.objects.filter(role='admin')

            print(f"Number of users: {users.count()}")   # debug

            from .tasks import send_notification_task
            for user in users:
                print(f"Queuing for {user.email}")       # debug
                send_notification_task.delay(user.id, subject, message, via_email, via_sms)
                Notification.objects.create(
                    user=user,
                    subject=subject,
                    message=message,
                    sent_via_email=via_email,
                    sent_via_sms=via_sms,
                    is_read=False
                )

            messages.success(request, f"Broadcast sent to {users.count()} users.")
            return redirect('admin_dashboard')
        else:
            print("Form errors:", form.errors)           # debug
            messages.error(request, "Form is invalid. Please check the data.")
    else:
        form = BroadcastNotificationForm()
    return render(request, 'voting/broadcast.html', {'form': form})

@login_required
@admin_required
def tally_election(request, election_id):
    election = get_object_or_404(Election, id=election_id)
    if not election.is_closed():
        messages.error(request, "Election is still ongoing.")
        return redirect('admin_dashboard')
    from .tasks import tally_election_results
    tally_election_results.delay(election_id)
    messages.success(request, "Tallying started in background.")
    return redirect('admin_dashboard')

@login_required
@admin_required
def audit_logs(request):
    logs = AuditLog.objects.all().order_by('-timestamp')
    paginator = Paginator(logs, 50)
    page = request.GET.get('page')
    logs_page = paginator.get_page(page)

    # AJAX request → return only the table partial
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'voting/audit_logs_table.html', {'logs': logs_page})

    return render(request, 'voting/audit_logs.html', {'logs': logs_page})

@login_required
@admin_required
def test_email(request):
    send_mail(
        'Test',
        'This is a test email',
        settings.EMAIL_HOST_USER,   # use the authenticated email
        [request.user.email],
        fail_silently=False
    )
    messages.success(request, 'Test email sent.')
    return redirect('admin_dashboard')

@login_required
@admin_required
def test_sms(request):
    from .utils import send_notification
    send_notification(request.user, "Test SMS", "This is a test message from MMUST Voting System.", send_email=False, send_sms=True)
    messages.success(request, "Test SMS sent.")
    return redirect('admin_dashboard')

# ---------- Candidate Profile (Enhanced) ----------
def candidate_profile(request, candidate_id):
    candidate = get_object_or_404(Candidate, id=candidate_id, verified=True)
    # If election is closed, compute vote count from TallyResult
    election = candidate.election
    vote_count = None
    if election.is_closed():
        try:
            tally = TallyResult.objects.get(election=election)
            # tally.results is dict: {position_id: {candidate_id: votes}}
            pos_id = str(candidate.position.id)
            cand_id = str(candidate.id)
            vote_count = tally.results.get(pos_id, {}).get(cand_id, 0)
        except TallyResult.DoesNotExist:
            pass

    # Get related candidates (same position, different user)
    related_candidates = Candidate.objects.filter(
        position=candidate.position,
        election=election,
        verified=True
    ).exclude(id=candidate.id)[:3]  # max 3

    context = {
        'candidate': candidate,
        'vote_count': vote_count,
        'related_candidates': related_candidates,
        'election': election,
    }
    return render(request, 'voting/candidate_profile.html', context)
@login_required
@role_required(['candidate'])
def candidate_questionnaire(request):
    candidate = request.user.candidacy if hasattr(request.user, 'candidacy') else None
    if not candidate:
        messages.warning(request, "Please register for a position before filling the questionnaire.")
        return redirect('candidate_register')
    if candidate.questionnaire_completed:
        messages.info(request, "You have already completed the questionnaire.")
        return redirect('dashboard')

    questions = CandidateQuestion.objects.all()

    if request.method == 'POST':
        # Save answers
        answers = {}
        for q in questions:
            if q.question_type == 'file':
                uploaded = request.FILES.get(f'file_{q.id}')
                if uploaded:
                    answers[str(q.id)] = uploaded.name
            else:
                val = request.POST.get(f'question_{q.id}')
                if val:
                    answers[str(q.id)] = val
        candidate.questionnaire_answers = answers
        # Save documents
        if 'party_certificate' in request.FILES:
            candidate.party_nomination_certificate = request.FILES['party_certificate']
        if 'fee_statement' in request.FILES:
            candidate.fee_statement = request.FILES['fee_statement']
        candidate.questionnaire_completed = True
        candidate.save()
        messages.success(request, "Your questionnaire has been submitted. Admin will review.")
        return redirect('dashboard')

    return render(request, 'voting/candidate_questionnaire.html', {'questions': questions})

# ---------- User Profile ----------
@login_required
def profile(request):
    user = request.user
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect('profile')
    else:
        form = UserProfileForm(instance=user)
    
    # Additional user data for template (read-only fields)
    context = {
        'form': form,
        'user': user,
        'schools': School.objects.all(),
        'departments': Department.objects.filter(school=user.school) if user.school else Department.objects.none(),
        'candidacy': getattr(user, 'candidacy', None),
    }
    return render(request, 'voting/profile.html', context)

@login_required
def update_profile_photo(request):
    """AJAX endpoint to update profile photo from camera capture (cropped)."""
    if request.method == 'POST' and request.FILES.get('photo'):
        photo = request.FILES['photo']
        # Validate image type and size
        if photo.content_type not in ['image/jpeg', 'image/png']:
            return JsonResponse({'status': 'error', 'message': 'Invalid image format. Use JPEG or PNG.'}, status=400)
        if photo.size > 5 * 1024 * 1024:
            return JsonResponse({'status': 'error', 'message': 'Image too large. Max 5MB.'}, status=400)
        # Save to user.id_photo
        request.user.id_photo.save(f"profile_{request.user.id}.jpg", photo)
        photo.seek(0)
        img_bytes = photo.read()
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        success = store_face_embedding(request.user, img_base64)
        return JsonResponse({'status': 'ok', 'message': 'Photo updated successfully.', 'embedding_stored': success})
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

@login_required
def voting_history(request):
    statuses = VoterStatus.objects.filter(user=request.user, has_voted=True).select_related('election').order_by('-voted_at')
    history_list = []
    for s in statuses:
        history_list.append({
            'id': s.id,
            'election_name': s.election.name,
            'voted_at': s.voted_at.isoformat(),
            'receipt': s.vote_receipt,
            'receipt_short': s.vote_receipt[:16] + '...' if len(s.vote_receipt) > 16 else s.vote_receipt,
        })
    import json
    history_json = json.dumps(history_list)
    return render(request, 'voting/voting_history.html', {'statuses': statuses, 'history_json': history_json})

# ---------- Eligibility API ----------
@login_required
def eligibility_api(request):
    """Return JSON: {eligible: bool, reason: str}"""
    election = get_active_election()
    if not election:
        return JsonResponse({'eligible': False, 'reason': 'No active election'})
    if not election.is_ongoing():
        return JsonResponse({'eligible': False, 'reason': 'Election not open'})
    if not request.user.is_verified:
        return JsonResponse({'eligible': False, 'reason': 'Your account is not verified'})
    try:
        status = VoterStatus.objects.get(user=request.user, election=election)
        if status.has_voted:
            return JsonResponse({'eligible': False, 'reason': 'You have already voted'})
    except VoterStatus.DoesNotExist:
        pass
    return JsonResponse({'eligible': True, 'reason': ''})

# ---------- Admin Exports ----------
@login_required
@admin_required
def export_voters_csv(request):
    voters = User.objects.filter(role='voter').values('username', 'email', 'voter_id', 'admission_number', 'course', 'year_of_study', 'school__name', 'department__name', 'is_verified', 'created_at')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="voters.csv"'
    writer = csv.writer(response)
    writer.writerow(['Username', 'Email', 'Voter ID', 'Admission', 'Course', 'Year', 'School', 'Department', 'Verified', 'Registered'])
    for v in voters:
        writer.writerow([v['username'], v['email'], v['voter_id'], v['admission_number'], v['course'], v['year_of_study'], v['school__name'], v['department__name'], v['is_verified'], v['created_at']])
    return response

@login_required
@admin_required
def export_candidates_csv(request):
    candidates = Candidate.objects.filter(verified=True).select_related('user', 'position', 'party', 'election')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="candidates.csv"'
    writer = csv.writer(response)
    writer.writerow(['Name', 'Email', 'Voter ID', 'Position', 'Party', 'Election', 'Manifesto'])
    for c in candidates:
        writer.writerow([c.user.get_full_name(), c.user.email, c.user.voter_id, c.position.name, c.party.name if c.party else 'Independent', c.election.name, c.manifesto[:100]])
    return response

@login_required
@admin_required
def export_audit_csv(request):
    logs = AuditLog.objects.all().order_by('-timestamp').values('user__username', 'action', 'ip_address', 'timestamp', 'details')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="audit_logs.csv"'
    writer = csv.writer(response)
    writer.writerow(['User', 'Action', 'IP Address', 'Timestamp', 'Details'])
    for log in logs:
        writer.writerow([log['user__username'], log['action'], log['ip_address'], log['timestamp'], log['details']])
    return response

# ---------- Candidate Withdrawal ----------
@login_required
@role_required(['candidate'])
def candidate_withdraw(request):
    if not hasattr(request.user, 'candidacy'):
        messages.error(request, "You are not a registered candidate.")
        return redirect('dashboard')
    candidate = request.user.candidacy
    if candidate.election.is_ongoing() or candidate.election.is_closed():
        messages.error(request, "Withdrawal is only allowed before the election starts.")
        return redirect('dashboard')
    if candidate.withdrawn:
        messages.warning(request, "You have already withdrawn.")
        return redirect('dashboard')
    if request.method == 'POST':
        form = CandidateWithdrawalForm(request.POST)
        if form.is_valid():
            candidate.withdrawn = True
            candidate.verified = False  # remove from ballot
            candidate.save()
            # Notify admins
            admins = User.objects.filter(is_staff=True)
            for admin in admins:
                send_notification(admin, f"Candidate Withdrawn: {candidate.user.get_full_name()}", f"{candidate.user.get_full_name()} has withdrawn from {candidate.election.name}.", send_email=True, send_sms=False)

            # --- NEW: Broadcast notification to voters who have not yet voted ---
            from .tasks import broadcast_notification_task
            subject = f"Candidate Withdrawn: {candidate.user.get_full_name()}"
            message = f"{candidate.user.get_full_name()} has withdrawn from {candidate.election.name}. Please update your vote if you had selected them."
            voters = VoterStatus.objects.filter(election=candidate.election, has_voted=False).values_list('user_id', flat=True)
            broadcast_notification_task.delay(list(voters), subject, message, send_email=True, send_sms=False)
            # -----------------------------------------------------------------

            messages.success(request, "You have withdrawn from the election.")
            return redirect('dashboard')
    else:
        form = CandidateWithdrawalForm()
    return render(request, 'voting/candidate_withdraw.html', {'form': form, 'candidate': candidate})

# ---------- Public Results Embed ----------
def results_embed(request, election_id):
    election = get_object_or_404(Election, id=election_id)
    if not election.is_closed():
        return HttpResponse("Results not available yet.", status=403)
    try:
        tally = TallyResult.objects.get(election=election)
        results_data = tally.results
    except TallyResult.DoesNotExist:
        results_data = {}
    # Enrich with position names
    positions = Position.objects.in_bulk(list(results_data.keys()))
    enriched = {}
    for pos_id, cands in results_data.items():
        pos = positions.get(int(pos_id))
        enriched[pos.name if pos else f"Position {pos_id}"] = cands
    return render(request, 'voting/results_embed.html', {'election': election, 'results': enriched})

@login_required
@admin_required
def admin_2fa_setup(request):
    user = request.user
    # If user asks to regenerate QR, delete existing device
    if request.GET.get('regenerate') == 'true':
        TOTPDevice.objects.filter(user=user).delete()
        messages.info(request, "Old 2FA device removed. Please scan the new QR code.")

    # Get or create a TOTP device with tolerance=4 (2 minutes)
    device, created = TOTPDevice.objects.get_or_create(
        user=user,
        defaults={'confirmed': False, 'tolerance': 4}
    )
    if not created and device.tolerance != 4:
        device.tolerance = 4
        device.save()

    if request.method == 'POST':
        token = request.POST.get('token')
        if device.verify_token(token):
            device.confirmed = True
            device.save()
            messages.success(request, "Two‑Factor Authentication enabled successfully (validity: 2 minutes).")
            return redirect('verify_2fa')
        else:
            messages.error(request, "Invalid token. Please try again.")

    config_url = device.config_url
    qr = qrcode.make(config_url)
    buffer = BytesIO()
    qr.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()
    return render(request, 'voting/admin_2fa_setup.html', {
        'qr_code': qr_base64,
        'device': device,
    })
    
def about_page(request):
    return render(request, 'voting/about.html')

def contact_page(request):
    form = ContactForm()
    return render(request, 'voting/contact.html', {'form': form})

def contact_submit(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            # Save the contact instance
            contact = form.save()

            # Prepare email
            subject = contact.subject
            full_message = f"From: {contact.name} <{contact.email}>\n\n{contact.message}"

            try:
                send_mail(
                    subject,
                    full_message,
                    contact.email,  # from_email = user's email (may need adjustment)
                    [settings.CONTACT_EMAIL],  # recipient list (admin)
                    fail_silently=False,
                )
                messages.success(request, "Your message has been sent. We'll get back to you soon.")
            except Exception as e:
                logger.error(f"Contact email failed: {e}")
                messages.error(request, "Could not send email. Please try again later.")

            return redirect('contact')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ContactForm()

    return render(request, 'voting/contact.html', {'form': form})
def stats_api(request):
    """Return JSON with system statistics for the about page."""
    from .models import User, Election, VoterStatus
    registered_voters = User.objects.filter(role='voter', is_verified=True).count()
    elections_held = Election.objects.filter(end_time__lt=timezone.now()).count()
    # Average turnout across all completed elections
    avg_turnout = 0
    completed_elections = Election.objects.filter(end_time__lt=timezone.now())
    if completed_elections.exists():
        turnout_sum = 0
        for election in completed_elections:
            total_voters = User.objects.filter(role='voter', is_verified=True).count()
            voted = VoterStatus.objects.filter(election=election, has_voted=True).count()
            if total_voters:
                turnout_sum += (voted / total_voters) * 100
        avg_turnout = round(turnout_sum / completed_elections.count(), 1)
    security_incidents = AttackLog.objects.count()
    return JsonResponse({
        'registered_voters': registered_voters,
        'elections_held': elections_held,
        'avg_turnout': avg_turnout,
        'security_incidents': security_incidents,
    })
@login_required
def api_notifications(request):
    """Return unread notifications for the logged-in user."""
    notifications = Notification.objects.filter(user=request.user, is_read=False).order_by('-created_at')
    data = [{
        'id': n.id,
        'subject': n.subject,
        'message': n.message,
        'created_at': n.created_at.isoformat(),
        'url': n.get_absolute_url() if hasattr(n, 'get_absolute_url') else '#'
    } for n in notifications]
    return JsonResponse({'count': len(data), 'notifications': data})

@login_required
def api_mark_notification_read(request, notification_id):
    notification = get_object_or_404(Notification, id=notification_id, user=request.user)
    notification.is_read = True
    notification.save()
    return JsonResponse({'status': 'ok'})

@login_required
def api_mark_all_notifications_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'status': 'ok'})

# Election creation (AJAX)
@login_required
@admin_required
def create_election_ajax(request):
    if request.method == 'POST':
        # Try to get data from JSON or POST
        if request.content_type == 'application/json':
            import json
            data = json.loads(request.body)
            name = data.get('name')
            start_time = data.get('start_time')
            end_time = data.get('end_time')
        else:
            name = request.POST.get('name')
            start_time = request.POST.get('start_time')
            end_time = request.POST.get('end_time')
        
        if name and start_time and end_time:
            from datetime import datetime
            start = datetime.fromisoformat(start_time)
            end = datetime.fromisoformat(end_time)
            election = Election.objects.create(name=name, start_time=start, end_time=end, is_active=True)
            return JsonResponse({'success': True, 'election_id': election.id})
        return JsonResponse({'success': False, 'error': 'Missing required fields'})
    return JsonResponse({'success': False, 'error': 'Invalid method'})


# Modified verify_users view (now shows tabs with separate lists)
@login_required
@admin_required
def verify_users(request):
    # Pending voters (identity not verified)
    voters = User.objects.filter(role='voter', is_verified=False).order_by('-created_at')
    
    # Pending candidates (candidacy not verified) – these are candidates who have applied
    pending_candidates = Candidate.objects.filter(verified=False).select_related('user').order_by('-user__created_at')
    candidate_data = []
    for cand in pending_candidates:
        candidate_data.append({
            'candidate_id': cand.id,
            'user_id': cand.user.id,
            'full_name': cand.user.get_full_name(),
            'email': cand.user.email,
            'position': cand.position.name,
            'party': cand.party.name if cand.party else 'Independent',
            'created_at': cand.user.created_at.isoformat(),
        })
    
    # Pending polling officers (identity not verified, but test passed)
    polling_officers = User.objects.filter(
        role='polling_officer',
        is_verified=False,
        polling_officer_test__passed=True
    ).order_by('-created_at')
    
    voter_data = [{
        'id': u.id,
        'username': u.username,
        'email': u.email,
        'full_name': u.get_full_name(),
        'created_at': u.created_at.isoformat(),
    } for u in voters]
    
    officer_data = [{
        'id': u.id,
        'username': u.username,
        'email': u.email,
        'full_name': u.get_full_name(),
        'score': u.polling_officer_test.score,
        'created_at': u.created_at.isoformat(),
    } for u in polling_officers]
    
    import json
    voters_json = json.dumps(voter_data)
    candidates_json = json.dumps(candidate_data)
    officers_json = json.dumps(officer_data)
    
    return render(request, 'voting/verify_users.html', {
        'voters': voters,
        'candidates': pending_candidates,
        'polling_officers': polling_officers,
        'voters_json': voters_json,
        'candidates_json': candidates_json,
        'officers_json': officers_json,
    })

# ---------- Admin AJAX Verification Endpoints ----------
@login_required
@admin_required
def verify_user_ajax(request, user_id):
    """AJAX endpoint to verify a voter."""
    try:
        user = User.objects.get(id=user_id, role='voter')
        user.is_verified = True
        user.save()
        return JsonResponse({'status': 'ok', 'message': 'User verified successfully'})
    except User.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'User not found'}, status=404)


@login_required
@admin_required
def verify_officer_ajax(request, user_id):
    """AJAX endpoint to verify a polling officer (must have passed test)."""
    try:
        user = User.objects.get(id=user_id, role='polling_officer')
        # Check if they passed the test
        test = PollingOfficerTest.objects.filter(user=user, passed=True).first()
        if not test:
            return JsonResponse({'status': 'error', 'message': 'Officer has not passed the qualification test'}, status=400)
        user.is_verified = True
        user.save()
        return JsonResponse({'status': 'ok', 'message': 'Officer verified successfully'})
    except User.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Officer not found'}, status=404)
    
def verify_2fa(request):
    """Verify TOTP code after login, before final authentication."""
    user_id = request.session.get('pre_2fa_user_id')
    if not user_id:
        messages.error(request, "Session expired. Please log in again.")
        return redirect('login')
    user = get_object_or_404(User, id=user_id)
    # If already authenticated (should not happen), just redirect
    if request.user.is_authenticated and request.user != user:
        logout(request)

    if request.method == 'POST':
        token = request.POST.get('token', '').strip()
        device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
        if device and device.verify_token(token):
            login(request, user)
            # Clean up session
            del request.session['pre_2fa_user_id']
            # Remember me
            if request.POST.get('remember_me'):
                request.session.set_expiry(1209600)
            else:
                request.session.set_expiry(0)
            messages.success(request, f"Welcome back, {user.get_full_name()}!")
            # Redirect staff to admin dashboard, others to regular dashboard
            if user.is_staff:
                return redirect('admin_dashboard')
            else:
                return redirect('dashboard')
        else:
            messages.error(request, "Invalid authentication code. Please try again.")
    return render(request, 'voting/verify_2fa.html', {'user': user})

@login_required
def user_status_api(request):
    """Return JSON with user's verification status and role."""
    try:
        # Force all values to be primitive types (str, bool, int)
        data = {
            'is_verified': bool(request.user.is_verified),
            'role': str(request.user.role),
            'full_name': str(request.user.get_full_name() or request.user.username),
            'voter_id': str(request.user.voter_id) if request.user.voter_id else '',
        }
        return JsonResponse(data)
    except Exception as e:
        logger.exception("user_status_api failed")  # logs full traceback
        return JsonResponse({'error': 'Internal server error', 'detail': str(e)}, status=500)

def login_status(request):
    username = request.GET.get('username')
    if not username:
        return JsonResponse({'error': 'Username required'}, status=400)
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    
    election = get_active_election()
    security_required = election and election.is_ongoing()
    
    return JsonResponse({
        'security_required': security_required,
        'question': user.get_security_question_display() if security_required else None
    })
    
def get_security_question(request):
    username = request.GET.get('username')
    if username:
        try:
            user = User.objects.get(username=username)
            return JsonResponse({'question': user.get_security_question_display()})
        except User.DoesNotExist:
            return JsonResponse({'error': 'User not found'}, status=404)
    return JsonResponse({'error': 'No username provided'}, status=400)
    
@login_required
@admin_required
def clear_broadcast_log(request):
    if request.method == 'POST':
        Notification.objects.all().delete()
        messages.success(request, "Broadcast log cleared.")
    return redirect('broadcast_log')

@login_required
@admin_required
def broadcast_log(request):
    sort_by = request.GET.get('sort', '-created_at')
    allowed_sorts = ['user__username', 'user__email', 'subject', 'created_at', '-created_at']
    if sort_by not in allowed_sorts:
        sort_by = '-created_at'
    logs = Notification.objects.all().order_by(sort_by)
    paginator = Paginator(logs, 50)
    page = request.GET.get('page')
    logs_page = paginator.get_page(page)
    return render(request, 'voting/broadcast_log.html', {'logs': logs_page, 'current_sort': sort_by})

@login_required
@admin_required
def close_election(request):
    if request.method == 'POST':
        active = get_active_election()
        if active:
            active.end_time = timezone.now()
            active.is_active = False
            active.save()
            messages.success(request, f"Election '{active.name}' has been closed.")
        else:
            messages.warning(request, "No active election to close.")
    return redirect('admin_dashboard')
   
def faq_page(request):
    return render(request, 'voting/faq.html')

# ---------- Chatbot ----------
def chatbot_view(request):
    return render(request, 'voting/chatbot.html')

# ---------- Error Handlers ----------
def handler404(request, exception):
    return render(request, '404.html', status=404)

def handler500(request):
    return render(request, '500.html', status=500)