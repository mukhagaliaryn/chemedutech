from ..models import LabContent, Stage, TestContent, TheoryContent, VideoContent

CONTENT_MODELS = {
    Stage.Kind.THEORY: TheoryContent,
    Stage.Kind.VIDEO: VideoContent,
    Stage.Kind.LAB: LabContent,
    Stage.Kind.TEST: TestContent,
    # Stage.Kind.PRACTICE → apps.practice.PracticeTask (STEP-07a)
}


def ensure_stage_content(stage: Stage, **fields):
    """Create the (empty) content object of the stage's kind if it does not exist yet; update ``fields``."""
    model = CONTENT_MODELS.get(stage.kind)
    if model is None:
        return None
    content, _created = model.objects.update_or_create(stage=stage, defaults=fields)
    return content
