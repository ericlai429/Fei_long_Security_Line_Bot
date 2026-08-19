import time
import threading
from typing import Tuple, Dict

# Cooldown duration in seconds: 4 hours = 4 * 3600 = 14400 seconds
SCHEDULE_COOLDOWN_SECONDS = 4 * 3600

class RateLimiter:
    def __init__(self, cooldown_seconds: int = SCHEDULE_COOLDOWN_SECONDS):
        self.cooldown_seconds = cooldown_seconds
        self.call_records: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _get_key(self, group_id: str, user_id: str) -> str:
        # If user_id is missing, rate limit by group_id
        return f"{group_id}:{user_id or 'anon'}"

    def check_and_update(self, group_id: str, user_id: str, is_admin: bool = False) -> Tuple[bool, int]:
        """
        Checks if the user can call the schedule.
        If allowed, records the timestamp and returns (True, 0).
        If on cooldown, returns (False, remaining_seconds).
        Admins are exempt from cooldown.
        """
        if is_admin:
            return True, 0

        key = self._get_key(group_id, user_id)
        now = time.time()

        with self._lock:
            last_call = self.call_records.get(key, 0)
            elapsed = now - last_call

            if elapsed < self.cooldown_seconds:
                remaining_seconds = int(self.cooldown_seconds - elapsed)
                return False, remaining_seconds

            # Update call record
            self.call_records[key] = now
            return True, 0

    def get_remaining_time(self, group_id: str, user_id: str) -> int:
        key = self._get_key(group_id, user_id)
        now = time.time()
        with self._lock:
            last_call = self.call_records.get(key, 0)
            elapsed = now - last_call
            if elapsed < self.cooldown_seconds:
                return int(self.cooldown_seconds - elapsed)
            return 0

    def reset(self, group_id: str = "", user_id: str = ""):
        with self._lock:
            if group_id and user_id:
                key = self._get_key(group_id, user_id)
                self.call_records.pop(key, None)
            else:
                self.call_records.clear()

rate_limiter = RateLimiter()
