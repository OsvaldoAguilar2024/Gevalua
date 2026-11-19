from django.contrib.auth import views as auth_views

from .forms import FormularioEntrada


class Entrar(auth_views.LoginView):
    template_name = "registration/entrar.html"
    authentication_form = FormularioEntrada
    redirect_authenticated_user = True
