from django import template

register = template.Library()


@register.filter
def add_contrast_color(hex_color):
    """Return black or white based on luminance of hex color."""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#FFFFFF" if luminance < 0.5 else "#000000"
