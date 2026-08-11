"""HTML sanitization for user-submitted rich text.

Every model field that can hold rich (CKEditor-authored) HTML is rendered
with the `safe` template filter, so anything saved here must already be
safe to inject into the page verbatim. A user can always bypass the
client-side editor and POST raw HTML directly, so sanitization has to
happen server-side, not just be assumed from "the editor produced it".
"""
import bleach
from bleach.css_sanitizer import CSSSanitizer

ALLOWED_TAGS = [
    'p', 'br', 'div', 'span', 'strong', 'b', 'em', 'i', 'u', 's', 'strike',
    'ol', 'ul', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote',
    'a', 'img', 'table', 'thead', 'tbody', 'tr', 'td', 'th', 'hr',
    'sub', 'sup', 'pre', 'code',
]

ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title', 'target', 'rel'],
    'img': ['src', 'alt', 'title', 'width', 'height', 'style'],
    'table': ['style'],
    'td': ['style', 'colspan', 'rowspan'],
    'th': ['style', 'colspan', 'rowspan'],
    '*': ['style'],
}

ALLOWED_CSS_PROPERTIES = [
    'color', 'background-color', 'font-family', 'font-size', 'text-align',
    'font-weight', 'font-style', 'text-decoration', 'width', 'height',
]

ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']

_css_sanitizer = CSSSanitizer(allowed_css_properties=ALLOWED_CSS_PROPERTIES)


def sanitize_html(value):
    """Strip anything that isn't in the allowlist. Safe to call on plain text too."""
    if not value:
        return value
    return bleach.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        css_sanitizer=_css_sanitizer,
        strip=True,
    )
