# consumers.py

import json
import logging
import time
from datetime import timedelta
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from .models import Election, VoterStatus, TallyResult, User, VoteTimeline, Candidate, Position

logger = logging.getLogger(__name__)


class BaseLiveTrackingConsumer(AsyncWebsocketConsumer):
    """
    Base consumer for live tracking WebSocket connections.
    Subclasses must set `is_admin` to True/False.
    """
    is_admin = False

    async def connect(self):
        self.election_id = self.scope['url_route']['kwargs']['election_id']
        self.group_name = f'live_tracking_{self.election_id}'

        # Verify election exists
        election = await self.get_election()
        if election is None:
            logger.warning(f"Election {self.election_id} not found, closing connection.")
            await self.close()
            return

        # If admin, enforce authentication
        if self.is_admin and not self.scope['user'].is_staff:
            logger.warning(f"Non‑staff user {self.scope['user']} tried to connect to admin WebSocket.")
            await self.close()
            return

        # Add to group and accept
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info(f"WebSocket connected: {self.group_name} (admin={self.is_admin})")

        # Send initial data
        data = await self.get_live_data()
        await self.send(text_data=json.dumps(data))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info(f"WebSocket disconnected: {self.group_name}")

    async def vote_update(self, event):
        """
        Send vote update to client. Can be overridden for throttling.
        """
        await self.send(text_data=json.dumps(event['data']))

    @database_sync_to_async
    def get_election(self):
        """Return election object or None if not found."""
        try:
            return Election.objects.get(id=self.election_id)
        except Election.DoesNotExist:
            return None

    @database_sync_to_async
    def get_live_data(self):
        """Fetch live data from database."""
        election = Election.objects.get(id=self.election_id)

        # Count voters (only verified voters)
        total_voters = User.objects.filter(role='voter', is_verified=True).count()

        # Count votes cast
        voted_count = VoterStatus.objects.filter(election=election, has_voted=True).count()
        turnout_percent = (voted_count / total_voters * 100) if total_voters > 0 else 0

        # Candidate counts (with delay for public, and per‑position structure)
        candidate_data = {}
        if self.is_admin:
            # Admin: always compute full candidate data
            candidate_data = self._build_candidate_data(election)
        else:
            # Public: 5‑minute delay from election start
            now = timezone.now()
            if now >= election.start_time + timedelta(minutes=5):
                candidate_data = self._build_candidate_data(election)
            else:
                candidate_data = {'delayed': True}

        return {
            'total_voters': total_voters,
            'voted': voted_count,
            'turnout': round(turnout_percent, 1),
            'candidates': candidate_data,
            'timestamp': timezone.now().isoformat(),
        }

    def _build_candidate_data(self, election):
        """
        Build a dict of candidate counts per position, using VoteTimeline.
        Returns a structure like:
        {
            "Position Name": [
                {"name": "John Doe", "party": "Party A", "count": 42, "color": "#ff0000"},
                ...
            ],
            ...
        }
        """
        # Get all positions that have at least one candidate in this election
        positions = Position.objects.filter(candidates__election=election).distinct()
        candidate_data = {}

        for pos in positions:
            candidates = Candidate.objects.filter(position=pos, election=election, verified=True)
            pos_candidates = []
            for cand in candidates:
                # Count votes for this candidate using VoteTimeline
                count = VoteTimeline.objects.filter(
                    election=election,
                    candidate_id=cand.id
                ).count()
                pos_candidates.append({
                    'name': cand.user.get_full_name(),
                    'party': cand.party.abbreviation if cand.party else 'Ind',
                    'count': count,
                    'color': cand.party.color if cand.party else '#6c757d',
                })
            if pos_candidates:
                candidate_data[pos.name] = pos_candidates
        return candidate_data


class AdminLiveTrackingConsumer(BaseLiveTrackingConsumer):
    """
    WebSocket consumer for admin users (real‑time dashboard).
    Features:
    - Only staff users can connect.
    - Rate‑limited updates (max 1 per 2 seconds).
    - Full candidate counts (no delay).
    """
    is_admin = True

    # Class-level dict to track last send time per group
    _last_update_time = {}

    async def vote_update(self, event):
        """Throttled vote update (max 1 per 2 seconds)."""
        now = time.time()
        last = self._last_update_time.get(self.group_name, 0)
        if now - last < 2:   # 2 seconds throttle
            return
        self._last_update_time[self.group_name] = now
        await super().vote_update(event)


class PublicLiveTrackingConsumer(BaseLiveTrackingConsumer):
    """
    WebSocket consumer for public viewers (e.g., live turnout page).
    Features:
    - No authentication required.
    - Rate‑limited updates (max 1 per 2 seconds).
    - Candidate counts delayed by 5 minutes.
    """
    is_admin = False

    # Separate class-level dict for public consumers
    _last_update_time = {}

    async def vote_update(self, event):
        """Throttled vote update (max 1 per 2 seconds)."""
        now = time.time()
        last = self._last_update_time.get(self.group_name, 0)
        if now - last < 2:
            return
        self._last_update_time[self.group_name] = now
        await super().vote_update(event)