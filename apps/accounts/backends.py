from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class UsernameOrEmailBackend(ModelBackend):
    """One login field: a value with "@" is matched against email (case-insensitive), otherwise username."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        login = (username or kwargs.get(UserModel.USERNAME_FIELD) or "").strip()
        if not login or password is None:
            return None
        if "@" in login:
            user = UserModel._default_manager.filter(email__iexact=login).first()
        else:
            user = UserModel._default_manager.filter(username=login).first()
        if user is None:
            UserModel().set_password(password)  # same work as a real check (timing)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
