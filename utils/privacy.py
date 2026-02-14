import uuid


def mask_user_id(user_id: str | int | None) -> str:
    value = str(user_id or "").strip()
    if not value:
        return "unknown"
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}***{value[-2:]}"


def text_meta(text: str | None) -> str:
    value = (text or "").strip()
    return f"len={len(value)}"


def new_request_id() -> str:
    return uuid.uuid4().hex[:8]

