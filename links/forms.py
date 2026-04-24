import nh3
from django import forms

from .models import Bookmark


class TagsField(forms.CharField):
    """Space-separated tag input that stores/retrieves a list."""

    def prepare_value(self, value):
        if isinstance(value, list):
            return " ".join(value)
        return value or ""

    def to_python(self, value):
        if not value:
            return []
        return sorted({t.lower().strip() for t in value.split() if t.strip()})


class BookmarkForm(forms.ModelForm):
    tags = TagsField(
        required=False,
        label="Tags",
        help_text="Space-separated. Lowercase, no special characters.",
        widget=forms.TextInput(attrs={"autocomplete": "off", "spellcheck": "false"}),
    )

    class Meta:
        model = Bookmark
        fields = ["url", "title", "description", "tags"]
        widgets = {
            "url": forms.URLInput(attrs={"autocomplete": "url"}),
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_title(self):
        value = self.cleaned_data.get("title", "")
        return nh3.clean(value, tags=set()).strip()

    def clean_description(self):
        value = self.cleaned_data.get("description", "")
        return nh3.clean(value, tags=set()).strip()
