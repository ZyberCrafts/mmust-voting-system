import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Avg
from django.core.serializers.json import DjangoJSONEncoder
from .models import RatingSession, ManifestoItem, LeaderRating
from .forms import RatingForm
from voting.models import Candidate
@login_required
def questionnaire(request, session_id):
    """Display rating form for a specific session."""
    session = get_object_or_404(RatingSession, id=session_id, is_active=True)
    # Ensure session is within date range
    if not (session.start_date <= timezone.now() <= session.end_date):
        messages.error(request, "This rating session is not active.")
        return redirect('home')

    # Get all manifesto items for leaders who won in the related election
    winners = Candidate.objects.filter(election=session.election, is_winner=True)
    items = ManifestoItem.objects.filter(candidate__in=winners).order_by('candidate', 'order')

    if request.method == 'POST':
        form = RatingForm(items, request.POST)
        if form.is_valid():
            # Save ratings
            for item in items:
                rating_value = form.cleaned_data.get(f'rating_{item.id}')
                comment = form.cleaned_data.get(f'comment_{item.id}')
                if rating_value:
                    LeaderRating.objects.update_or_create(
                        session=session,
                        user=request.user,
                        item=item,
                        defaults={'rating': rating_value, 'comment': comment or ''}
                    )
            messages.success(request, "Thank you for your feedback!")
            return redirect('dashboard')
    else:
        # Pre-populate if user has already rated some items
        initial = {}
        existing_ratings = LeaderRating.objects.filter(session=session, user=request.user)
        for r in existing_ratings:
            initial[f'rating_{r.item.id}'] = r.rating
            initial[f'comment_{r.item.id}'] = r.comment
        form = RatingForm(items, initial=initial)

    return render(request, 'accountability/questionnaire.html', {
        'form': form,
        'session': session,
        'items': items,
    })

@login_required
def leader_dashboard(request):
    """View for leaders to see aggregated ratings for their items."""
    # Only show to users who are winners in any election
    winners = Candidate.objects.filter(user=request.user, is_winner=True)
    if not winners:
        messages.warning(request, "You are not a recognized leader.")
        return redirect('dashboard')

    # Gather all sessions where this leader has items
    items = ManifestoItem.objects.filter(candidate__in=winners)
    sessions = RatingSession.objects.filter(ratings__item__in=items).distinct()

    # Build data for display
    data = {}
    for session in sessions:
        data[session] = []
        for item in items:
            ratings = LeaderRating.objects.filter(session=session, item=item)
            avg = ratings.aggregate(Avg('rating'))['rating__avg'] or 0
            data[session].append({
                'item': item,
                'avg_rating': round(avg, 1),
                'count': ratings.count(),
                'comments': [r.comment for r in ratings if r.comment]
            })

    # Build JSON-serialized data for frontend charts
    sessions_data = []
    for session, items_data in data.items():
        session_obj = {
            'id': session.id,
            'name': f"{session.election.name} – {session.start_date.strftime('%b %Y')}",
            'start_date': session.start_date.isoformat(),
            'end_date': session.end_date.isoformat(),
            'items': []
        }
        for item_data in items_data:
            item = item_data['item']
            # Compute rating distribution (counts per rating 1-5)
            distribution = [0, 0, 0, 0, 0]
            for rating in LeaderRating.objects.filter(session=session, item=item):
                distribution[rating.rating - 1] += 1
            session_obj['items'].append({
                'id': item.id,
                'description': item.description,
                'avg_rating': item_data['avg_rating'],
                'count': item_data['count'],
                'comments': item_data['comments'],
                'distribution': distribution
            })
        sessions_data.append(session_obj)

    sessions_json = json.dumps(sessions_data, cls=DjangoJSONEncoder)

    return render(request, 'accountability/leader_dashboard.html', {
        'winners': winners,
        'data': data,               # kept for template backward compatibility
        'sessions_json': sessions_json,
    })