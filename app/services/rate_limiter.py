from collections import defaultdict, deque
from time import monotonic


class InMemoryRateLimiter:
    """Rate limit liviano por contacto para evitar respuestas repetitivas."""

    def __init__(self, max_messages: int, window_seconds: int) -> None:
        self.max_messages = max(1, max_messages)
        self.window_seconds = max(1, window_seconds)
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = monotonic()
        events = self._events[key]
        while events and now - events[0] > self.window_seconds:
            events.popleft()
        if len(events) >= self.max_messages:
            return False
        events.append(now)
        return True
