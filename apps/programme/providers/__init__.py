"""Section kind providers (docs/icpai/SPEC.md §3): each kind says how much of a section a student has done.

A provider reads the lower apps only. The percent formulas live here, one class per kind, so a pass rule can
change in one place. Kinds that are not built yet report 0 % and ``ready = False`` («in development»).
"""

from ..models import Section
from .base import Provider, Upcoming
from .course import CourseProvider
from .designer import DesignerProvider
from .diagnostic import DiagnosticProvider
from .video import VideoProvider

PROVIDERS: dict[str, Provider] = {
    Section.Kind.COURSE: CourseProvider(),
    Section.Kind.DIAGNOSTIC: DiagnosticProvider(),
    Section.Kind.VIDEO: VideoProvider(),
    Section.Kind.DESIGNER: DesignerProvider(),
}


def provider_for(section) -> Provider:
    return PROVIDERS.get(section.kind) or Upcoming()


__all__ = ["PROVIDERS", "Provider", "provider_for"]
