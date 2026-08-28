"""Yechimlar — URL manzillari (D1-T8, D1-T10)."""

from django.urls import path

from . import views

urlpatterns = [
    path("ovoz/yechim/<int:pk>/", views.yechim_ovoz, name="yechim_ovoz"),
    # Yechim yozish muammo manzili ostida — u shu muammoga tegishli.
    path("dard/<slug:slug>/yechim/", views.solution_create, name="solution_create"),
    path("yechim/<int:pk>/qabul/", views.solution_accept, name="solution_accept"),
    path("yechim/<int:pk>/bekor/", views.solution_unaccept, name="solution_unaccept"),
]
