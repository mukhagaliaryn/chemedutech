from decimal import Decimal

from ..models import SectionVideo, VideoWatch
from .base import Provider


class VideoProvider(Provider):
    """Section 3 — the video (guide @S3): the share watched. No video yet → 100 %: the section counts as done and does
    not hold the students back while the video is being prepared (agreed with the author, D72)."""

    def percent(self, enrollment, section) -> Decimal:
        video = SectionVideo.objects.filter(section=section).first()
        if video is None or not video.youtube_id:
            return Decimal(100)
        watch = VideoWatch.objects.filter(enrollment=enrollment, section=section).first()
        return Decimal(watch.percent if watch else 0)
