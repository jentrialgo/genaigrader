from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from users.models import CustomUser


class ApiTokenAuthentication(BaseAuthentication):
    keyword = "Token"

    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith(self.keyword):
            return None

        token = auth_header[len(self.keyword) + 1 :].strip()
        if not token:
            return None

        try:
            user = CustomUser.objects.get(api_token=token)
        except CustomUser.DoesNotExist:
            raise AuthenticationFailed("Invalid token")

        return (user, None)

    def authenticate_header(self, request):
        return self.keyword
