"""Delete rows whose research log is PROTECTed (attempts, events): the protected rows go first, then the rest."""

from collections import defaultdict

from django.db.models import ProtectedError, RestrictedError


def purge(queryset, depth: int = 0) -> None:
    if depth > 20:
        raise RuntimeError("purge: the protection chain is too deep")
    for _round in range(50):
        try:
            queryset.delete()
            return
        except ProtectedError as exc:
            blocking = exc.protected_objects
        except RestrictedError as exc:
            blocking = exc.restricted_objects
        by_model = defaultdict(set)
        for obj in blocking:
            by_model[type(obj)].add(obj.pk)
        for model, pks in by_model.items():
            purge(model._base_manager.filter(pk__in=pks), depth + 1)
    raise RuntimeError("purge: rows are still protected")
