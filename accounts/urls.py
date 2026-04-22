from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.register, name="register"),
    path("register/begin/", views.register_begin, name="register_begin"),
    path("register/complete/", views.register_complete, name="register_complete"),
    path("login/", views.login_view, name="login"),
    path("login/begin/", views.login_begin, name="login_begin"),
    path("login/complete/", views.login_complete, name="login_complete"),
    path("logout/", views.logout_view, name="logout"),
    path("settings/", views.settings_view, name="settings"),
]
