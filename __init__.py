try:
    from utils.calendar_utils import get_today_events
except Exception:  # pragma: no cover - optional import for package init
    get_today_events = None
