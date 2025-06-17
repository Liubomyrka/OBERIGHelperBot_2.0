from googleapiclient.discovery import build
from config import YOUTUBE_API_KEY, OBERIG_PLAYLIST_ID
from database import get_value, set_value
import json
import time


def get_youtube_service():
    """
    Ініціалізує та повертає сервіс YouTube API.
    """
    return build("youtube", "v3", developerKey=YOUTUBE_API_KEY)


def get_playlist_items(playlist_id, max_results=50):
    """
    Отримує елементи плейлиста.
    """
    youtube = get_youtube_service()

    request = youtube.playlistItems().list(
        part="snippet", playlistId=playlist_id, maxResults=max_results
    )
    response = request.execute()

    return response.get("items", [])


def get_video_details(video_id):
    """
    Отримує деталі відео за його ID.
    """
    youtube = get_youtube_service()

    request = youtube.videos().list(part="snippet,statistics", id=video_id)
    response = request.execute()

    return response.get("items", [])[0] if response.get("items") else None


def get_latest_video(playlist_id):
    """
    Отримує інформацію про останнє відео в плейлисті.
    """
    items = get_playlist_items(playlist_id, max_results=1)

    if not items:
        return None

    latest_video_id = items[0]["snippet"]["resourceId"]["videoId"]
    video_details = get_video_details(latest_video_id)

    if not video_details:
        return None

    return {
        "title": video_details["snippet"]["title"],
        "url": f"https://youtu.be/{latest_video_id}",
    }


def get_most_popular_video(playlist_id):
    """
    Отримує найпопулярніше відео з плейлиста за кількістю переглядів.
    """
    items = get_playlist_items(playlist_id)

    most_popular = None
    max_views = 0

    for item in items:
        video_id = item["snippet"]["resourceId"]["videoId"]
        video_details = get_video_details(video_id)

        if video_details:
            views = int(video_details["statistics"].get("viewCount", 0))

            if views > max_views:
                max_views = views
                most_popular = {
                    "title": video_details["snippet"]["title"],
                    "views": views,
                    "url": f"https://youtu.be/{video_id}",
                }

    return most_popular


def get_top_5_videos(playlist_id):
    """
    Отримує топ-5 відео з плейлиста за кількістю переглядів.
    """
    items = get_playlist_items(playlist_id)

    video_stats = []

    for item in items:
        video_id = item["snippet"]["resourceId"]["videoId"]
        video_details = get_video_details(video_id)

        if video_details:
            views = int(video_details["statistics"].get("viewCount", 0))
            video_stats.append(
                {
                    "title": video_details["snippet"]["title"],
                    "views": views,
                    "url": f"https://youtu.be/{video_id}",
                }
            )

    # Сортування за кількістю переглядів
    top_5_videos = sorted(video_stats, key=lambda x: x["views"], reverse=True)[:5]

    return top_5_videos


def _get_cached_value(key: str, ttl: int):
    try:
        cached = get_value(key)
        ts = get_value(f"{key}_ts")
        now = time.time()
        if cached and ts and now - float(ts) < ttl:
            return json.loads(cached)
    except Exception:
        pass
    return None


def _set_cached_value(key: str, value):
    try:
        set_value(key, json.dumps(value))
        set_value(f"{key}_ts", str(time.time()))
    except Exception:
        pass


def get_latest_video_cached(ttl: int = 300):
    cached = _get_cached_value("yt_latest", ttl)
    if cached is not None:
        return cached
    result = get_latest_video(OBERIG_PLAYLIST_ID)
    _set_cached_value("yt_latest", result)
    return result


def get_most_popular_video_cached(ttl: int = 300):
    cached = _get_cached_value("yt_popular", ttl)
    if cached is not None:
        return cached
    result = get_most_popular_video(OBERIG_PLAYLIST_ID)
    _set_cached_value("yt_popular", result)
    return result


def get_top_5_videos_cached(ttl: int = 300):
    cached = _get_cached_value("yt_top5", ttl)
    if cached is not None:
        return cached
    result = get_top_5_videos(OBERIG_PLAYLIST_ID)
    _set_cached_value("yt_top5", result)
    return result


__all__ = [
    "get_youtube_service",
    "get_playlist_items",
    "get_video_details",
    "get_latest_video",
    "get_most_popular_video",
    "get_top_5_videos",
    "get_latest_video_cached",
    "get_most_popular_video_cached",
    "get_top_5_videos_cached",
]
