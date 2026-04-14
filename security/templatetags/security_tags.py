from django import template
register = template.Library()

@register.filter
def attack_badge(attack_type):
    mapping = {
        'bruteforce': 'danger',
        'sqli': 'danger',
        'xss': 'warning',
        'idor': 'warning',
        'dos': 'danger',
        'unknown': 'secondary',
    }
    return mapping.get(attack_type, 'secondary')