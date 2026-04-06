from rest_framework.throttling import UserRateThrottle


class RoleBasedUserRateThrottle(UserRateThrottle):
    """
    User throttle dengan rate berbeda untuk admin.
    - user biasa: gunakan scope 'user'
    - admin (is_staff): gunakan scope 'admin_user'
    """

    def allow_request(self, request, view):
        original_scope = getattr(self, 'scope', None)
        try:
            if getattr(request, 'user', None) and request.user.is_authenticated and request.user.is_staff:
                self.scope = 'admin_user'
            else:
                self.scope = 'user'
            return super().allow_request(request, view)
        finally:
            # Kembalikan scope agar tidak bocor ke request lain
            self.scope = original_scope