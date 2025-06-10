from googleapiclient.discovery import build
from config import YOUTUBE_API_KEY, OBERIG_PLAYLIST_ID


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
