import json
import uuid
import logging
from django.conf import settings
from django.db import models
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import ChatSession, ChatMessage
from django.views.decorators.clickjacking import xframe_options_exempt
from voting.models import Candidate, Position, VoterStatus, User as VotingUser, TallyResult
from voting.utils import get_active_election


logger = logging.getLogger(__name__)

# Simple rule-based intent detection (can be enhanced with ML)
def detect_intent(message):
    msg = message.lower()
    if any(word in msg for word in ['hi', 'hello', 'hey', 'greetings']):
        return 'greeting'
    elif any(word in msg for word in ['election', 'when', 'date', 'period']):
        return 'election'
    elif any(word in msg for word in ['candidate', 'who', 'running', 'contest']):
        return 'candidate'
    elif any(word in msg for word in ['vote', 'how', 'ballot', 'cast']):
        return 'vote'
    elif any(word in msg for word in ['result', 'winner', 'won', 'outcome']):
        return 'result'
    elif any(word in msg for word in ['turnout', 'live', 'count', 'participation']):
        return 'turnout'
    elif any(word in msg for word in ['help', 'support', 'guide']):
        return 'help'
    else:
        return 'other'

def get_live_stats(election):
    """Return live turnout stats for the given election."""
    if not election:
        return None
    total_voters = VotingUser.objects.filter(role='voter', is_verified=True).count()
    voted = VoterStatus.objects.filter(election=election, has_voted=True).count()
    turnout_percent = (voted / total_voters * 100) if total_voters else 0
    return {
        'total': total_voters,
        'voted': voted,
        'turnout': round(turnout_percent, 1),
        'ongoing': election.is_ongoing(),
    }

def get_live_stats(election):
    """Helper to get live turnout stats."""
    total = VoterStatus.objects.filter(election=election).count()
    voted = VoterStatus.objects.filter(election=election, has_voted=True).count()
    turnout = round((voted / total) * 100, 1) if total > 0 else 0
    return {'total': total, 'voted': voted, 'turnout': turnout}

def get_openai_response(message, context):
    """Placeholder for OpenAI integration. Replace with actual implementation."""
    # Example: use openai.ChatCompletion.create(...)
    # Return response text or None if fails
    return None

def generate_response(message, intent, session, election=None, use_openai=True):
    """
    Generate a response based on detected intent and context.
    If use_openai is True and intent is not one of the core voting intents,
    try to get a response from OpenAI. Otherwise fall back to rule-based logic.
    """
    if not election:
        election = get_active_election()

    # Core intents handled by reliable rule-based logic
    if intent in ('election', 'candidate', 'vote', 'result', 'turnout', 'help', 'greeting'):
        if intent == 'greeting':
            return "Hello! I'm the MMUST Voting Assistant. How can I help you today? You can ask about elections, candidates, voting, results, or live turnout."

        elif intent == 'election':
            if election:
                if election.is_ongoing():
                    return (f"Voting is ongoing for the '{election.name}' election. It started on {election.start_time.strftime('%d %b %Y, %H:%M')} "
                            f"and ends on {election.end_time.strftime('%d %b %Y, %H:%M')}. Make sure to cast your vote!")
                elif election.is_upcoming():
                    return (f"The next election is '{election.name}', starting on {election.start_time.strftime('%d %b %Y, %H:%M')}. Stay tuned!")
                else:
                    return (f"The last election was '{election.name}', held from {election.start_time.strftime('%d %b %Y')} to {election.end_time.strftime('%d %b %Y')}. "
                            f"Results are available on the Results page.")
            else:
                return "There is no active or upcoming election at the moment. Please check back later."

        elif intent == 'candidate':
            if election and election.is_ongoing():
                positions = Position.objects.filter(
                    models.Q(candidates__election=election) &
                    (models.Q(school__isnull=True) | models.Q(school=session.user.school if session.user else None))
                ).distinct()
                if positions:
                    response = "Here are the candidates:\n"
                    for pos in positions:
                        candidates = Candidate.objects.filter(election=election, position=pos, verified=True)
                        if candidates:
                            response += f"\n*{pos.name}*:\n"
                            for c in candidates:
                                response += f"  - {c.user.get_full_name()} ({c.party.name if c.party else 'Independent'})\n"
                    return response
                else:
                    return "No candidates have been registered for the current election yet."
            else:
                return "Candidates will be listed when an election is active. You can check the Candidates page for details."

        elif intent == 'vote':
            if not session.user or not session.user.is_authenticated:
                return "You need to be logged in to vote. Please go to the login page."
            if not election or not election.is_ongoing():
                return "Voting is not open at the moment."
            if VoterStatus.objects.filter(user=session.user, election=election, has_voted=True).exists():
                return "You have already voted in this election. Thank you for participating!"
            return "To vote, please visit the Voting page. You'll see a list of positions and candidates. Select your choices and confirm your vote."

        elif intent == 'result':
            if not election:
                return "No recent elections found. Check back after the next election."
            if election.is_ongoing() or election.is_upcoming():
                return f"Results for '{election.name}' will be published after the voting ends on {election.end_time.strftime('%d %b %Y, %H:%M')}."
            else:
                try:
                    tally = TallyResult.objects.get(election=election)
                    results = tally.results
                    if not results:
                        return f"The election '{election.name}' has ended, but results are not yet available. Please check later."
                    response = f"Results for '{election.name}':\n"
                    for pos_id, cands in results.items():
                        position = Position.objects.get(id=pos_id)
                        response += f"\n*{position.name}*:\n"
                        for cand_id, data in cands.items():
                            response += f"  - {data['name']} ({data['party']}) – {data['votes']} votes\n"
                    return response
                except TallyResult.DoesNotExist:
                    return f"The election '{election.name}' has ended, but results are being tallied. Please check later."

        elif intent == 'turnout':
            if not election or not election.is_ongoing():
                return "There is no active election to show turnout for."
            stats = get_live_stats(election)
            if stats:
                return (f"Current turnout for '{election.name}': {stats['voted']} out of {stats['total']} voters have cast their votes. "
                        f"That's {stats['turnout']}% participation.")
            else:
                return "Unable to fetch turnout at the moment."

        elif intent == 'help':
            return ("I can help with:\n- Election dates and status\n- Candidate lists\n- How to vote\n- Live turnout statistics\n- Election results\n"
                    "Just ask me!")

    # For other intents, use OpenAI if available and requested
    else:
        if use_openai and getattr(settings, 'OPENAI_API_KEY', None):
            # Build context from recent messages in the session
            context_messages = session.messages.order_by('-timestamp')[:3] if session else []
            context_str = "\n".join([f"{'User' if not m.is_bot else 'Bot'}: {m.message}" for m in reversed(context_messages)])
            context = f"Previous conversation:\n{context_str}\nCurrent question: {message}"
            response = get_openai_response(message, context)
            if response:
                return response
            else:
                return "I'm having trouble connecting to my brain. Please try again later or ask a specific voting question."
        else:
            return "I'm not sure I understand. You can ask about elections, candidates, voting, results, or turnout. For a list of topics, say 'help'."

def get_suggested_questions(election=None):
    base_questions = [
        "When is the next election?",
        "Who are the candidates?",
        "How do I vote?",
        "What is the live turnout?",
        "Where can I see results?",
    ]
    if election:
        if election.is_ongoing():
            base_questions.append("How do I cast my vote?")
            base_questions.append("Can I change my vote?")
        elif election.is_upcoming():
            base_questions.append("When does voting start?")
        else:
            base_questions.append("Who won the last election?")
    return base_questions       

@csrf_exempt
@require_http_methods(["POST"])
def chatbot_api(request):
    try:
        data = json.loads(request.body)
        message = data.get('message', '').strip()
        session_id = data.get('session_id')
        user_id = data.get('user_id')  # optional, if user is logged in
    except:
        message = request.POST.get('message', '').strip()
        session_id = request.POST.get('session_id')
        user_id = request.POST.get('user_id')

    if not message:
        return JsonResponse({'error': 'Empty message'}, status=400)

    # Get or create session
    if session_id:
        try:
            session = ChatSession.objects.get(session_id=session_id)
        except ChatSession.DoesNotExist:
            session = None
    else:
        session = None

    if not session:
        session_id = str(uuid.uuid4())
        user = None
        if user_id:
            try:
                user = VotingUser.objects.get(id=user_id)
            except VotingUser.DoesNotExist:
                pass
        session = ChatSession.objects.create(session_id=session_id, user=user)
    else:
        # Update last_activity automatically via auto_now
        session.save()

    # Detect intent
    intent = detect_intent(message)

    # Generate response
    election = get_active_election()  # current active election
    response_text = generate_response(message, intent, session, election)

    # Save user message and bot response
    ChatMessage.objects.create(session=session, message=message, is_bot=False, intent=intent)
    bot_msg = ChatMessage.objects.create(session=session, message=response_text, is_bot=True)

    return JsonResponse({
        'response': response_text,
        'session_id': session.session_id,
        'intent': intent,
    })


def chatbot_ui(request):
    """Render the chatbot UI page."""
    session_id = request.COOKIES.get('chat_session')
    if not session_id:
        session_id = str(uuid.uuid4())
    session = ChatSession.objects.filter(session_id=session_id).first()
    messages = session.messages.all() if session else []

    response = render(request, 'chatbot/chat.html', {'messages': messages})
    election = get_active_election()
    suggested_questions = get_suggested_questions(election)
    response = render(request, 'chatbot/chat.html', {
        'messages': messages,
        'suggested_questions': suggested_questions,
    })
    response.set_cookie('chat_session', session_id, max_age=60*60*24*30, httponly=True)
    return response

@xframe_options_exempt
def chatbot_embed(request):
    """Return a minimal chat interface for embedding in iframes."""
    # Create or get session from cookie (same as original)
    session_id = request.COOKIES.get('chat_session')
    if not session_id:
        import uuid
        session_id = str(uuid.uuid4())
    session, _ = ChatSession.objects.get_or_create(session_id=session_id)
    messages = ChatMessage.objects.filter(session=session).order_by('timestamp')
    # We don't pass Django messages to this template; it uses its own JS.
    return render(request, 'chatbot/embed.html', {'messages': messages})