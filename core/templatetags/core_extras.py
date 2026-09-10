from django import template

register = template.Library()


@register.filter
def dict_get(d, key):
    """Look up `key` in dict `d` from a template, where `key` is itself a
    template variable (e.g. a for-loop variable) rather than a literal —
    Django's built-in `.` lookup only supports literal keys, so a filter
    is the standard way to do a dynamic-key dict lookup."""
    if not d:
        return ''
    return d.get(key, '')
