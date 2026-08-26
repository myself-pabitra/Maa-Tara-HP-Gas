from django import template

register = template.Library()

@register.simple_tag(takes_context=True)
def query_transform(context, **kwargs):
    """
    Returns the URL-encoded query string for the current page,
    updating the parameters with the provided keyword arguments.
    Usage: {% query_transform page=2 %}
    """
    request = context.get('request')
    if not request:
        return ''
    
    updated = request.GET.copy()
    for k, v in kwargs.items():
        if v is not None:
            updated[k] = v
        else:
            updated.pop(k, 0)
            
    return f"?{updated.urlencode()}" if updated else "?"
