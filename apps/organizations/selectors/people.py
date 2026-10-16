from ..models import ResearchCohort, StudentProfile


def group_of(user):
    """The student's academic group, or None."""
    profile = StudentProfile.objects.filter(user=user).select_related("group").first()
    return profile.group if profile else None


def research_cohort_for(user):
    """control / experimental / "" — taken from the student's group (snapshotted by callers)."""
    group = group_of(user)
    return group.research_cohort if group else ResearchCohort.NONE
