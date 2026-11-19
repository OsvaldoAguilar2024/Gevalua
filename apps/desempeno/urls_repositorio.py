from django.urls import path

from .views_repositorio import repositorio

urlpatterns = [path("", repositorio, name="repositorio")]
