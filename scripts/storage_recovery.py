"""Pure decision gate for the original optional storage-full routine.

Only called after a verified victory/summary and a replay click. The
caller must verify the exact foreground window before sending any input.
"""


def storage_action(*, enabled, routine_done, replay_seen, storage_streak,
                   summary_streak, replay_button, replay_attempts,
                   backup_after, retry_due):
    if storage_streak >= 2:
        if not enabled or routine_done or replay_seen:
            return "stop"
        return "smelt"
    if storage_streak or replay_seen or routine_done or not enabled:
        return "wait"
    if not backup_after or not retry_due or summary_streak < 2 or not replay_button:
        return "wait"
    return "smelt" if replay_attempts >= backup_after else "retry"
