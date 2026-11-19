from django.urls import path

from . import views

urlpatterns = [path("<str:tipo>/<int:pk>/", views.firmar, name="firmar")]
