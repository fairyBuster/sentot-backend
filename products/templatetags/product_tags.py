from django import template

register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    return dictionary.get(key, 0)

@register.filter(name='to_items')
def to_items(value):
    if isinstance(value, dict):
        return sorted(value.items())
    return []
