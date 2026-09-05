"""Shared helper for the 'On this day' feature — used by the home dashboard
widget, the dedicated browsing page, and the daily notification command."""
from django.utils import timezone

from .models import Memory


def get_on_this_day_memories(user, month=None, day=None):
    """Memories from any board `user` is a member of that happened on the
    given calendar day (defaults to today) in a previous year. Uses
    `memory_date` when the user set one, otherwise falls back to the date
    the memory was created. Most recent year first."""
    today = timezone.localdate()
    month = month or today.month
    day   = day or today.day
    this_year = today.year

    qs = (Memory.objects
          .filter(group__members=user, is_deleted=False)
          .select_related('group', 'creator')
          .distinct())

    matches = []
    for m in qs:
        d = m.memory_date or m.created_at.date()
        if d.month == month and d.day == day and d.year < this_year:
            m.on_this_day_year = d.year
            matches.append(m)

    matches.sort(key=lambda m: -m.on_this_day_year)
    return matches
