from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class AdminEmpresaRequerido(LoginRequiredMixin, UserPassesTestMixin):
    raise_exception = False

    def test_func(self):
        return self.request.user.es_admin_empresa

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        return super().handle_no_permission()


class JefeRequerido(AdminEmpresaRequerido):
    def test_func(self):
        u = self.request.user
        return u.es_jefe or u.es_admin_empresa
