from django.apps import AppConfig


class LinksConfig(AppConfig):
    name = "links"

    def ready(self):
        import links.signals  # noqa: F401
