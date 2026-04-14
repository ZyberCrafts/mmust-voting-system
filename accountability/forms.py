from django import forms
from .models import LeaderRating, ManifestoItem

class RatingForm(forms.Form):
    """Dynamic form for rating multiple manifesto items."""
    def __init__(self, items, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for item in items:
            self.fields[f'rating_{item.id}'] = forms.ChoiceField(
                label=item.description,
                choices=[(i, f"{i} ★") for i in range(1, 6)],
                widget=forms.RadioSelect,
                required=False
            )
            self.fields[f'comment_{item.id}'] = forms.CharField(
                label="Comment (optional)",
                widget=forms.Textarea(attrs={'rows': 2}),
                required=False
            )