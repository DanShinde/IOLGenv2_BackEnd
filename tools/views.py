"""HTTP only -- bind a form, call the pure module, pick a response. No business rules.

Every view here is deliberately public: /tools/ is matched by none of the per-software
access middleware, and nothing in this app touches the database.
"""
from django.shortcuts import render
from django.views.decorators.http import require_POST

from . import exports
from .forms import SclForm, TextListForm
from .registry import TOOLS
from .scl import SclParams, render_scl
from .textlist import TextListError, analyse, build_workbook


def tools_home(request):
    return render(request, 'tools/home.html', {'tools': TOOLS})


# ------------------------------------------------------------------ IO text lists

def _textlist_context(form, summary=None, error=None, interactive=True):
    return {
        'form': form,
        'summary': summary,
        'error': error,
        # The Download button re-posts the file straight from the still-populated file
        # input, which only survives if the page was never reloaded -- i.e. if HTMX
        # swapped the summary in. Without that, there is nothing left to download.
        'interactive': interactive,
    }


def textlist_view(request):
    """GET renders the form. POST validates the upload and reports what would be
    written -- it never streams the file; the Download button does that."""
    if request.method != 'POST':
        return render(request, 'tools/textlist.html', _textlist_context(TextListForm()))

    form = TextListForm(request.POST, request.FILES)
    summary = error = None
    if form.is_valid():
        try:
            summary = analyse(form.cleaned_data['workbook'], form.cleaned_data['text_format'])
        except TextListError as exc:
            error = str(exc)

    htmx = bool(request.headers.get('HX-Request'))
    context = _textlist_context(form, summary, error, interactive=htmx)
    template = 'tools/_textlist_summary.html' if htmx else 'tools/textlist.html'
    return render(request, template, context)


@require_POST
def textlist_download(request):
    """Builds and streams the workbook. Re-runs the full analysis rather than trusting
    the summary the browser was shown, so a file edited between the two posts can never
    produce a workbook that disagrees with what the user approved."""
    form = TextListForm(request.POST, request.FILES)
    if not form.is_valid():
        if 'workbook' in form.errors and not request.FILES.get('workbook'):
            # The file input was empty -- the page reloaded, or JS is off.
            error = ("Your file wasn't re-sent. Choose it again, press Validate, "
                     'then Download.')
        else:
            error = ' '.join(
                str(message) for messages in form.errors.values() for message in messages
            )
        return render(request, 'tools/textlist.html',
                      _textlist_context(TextListForm(), error=error))

    uploaded = form.cleaned_data['workbook']
    text_format = form.cleaned_data['text_format']
    try:
        buffer, summary = build_workbook(uploaded, text_format)
    except TextListError as exc:
        return render(request, 'tools/textlist.html', _textlist_context(form, error=str(exc)))

    expected = (request.POST.get('fingerprint') or '').strip()
    if expected and expected != summary.fingerprint:
        # The file changed on disk between Validate and Download. Show the new summary
        # and make the user press Download again, rather than handing them a workbook
        # built from bytes they never saw checked.
        return render(request, 'tools/textlist.html', _textlist_context(
            form, summary=summary,
            error='This file changed since it was checked. Here is the updated summary '
                  '-- press Download again if it looks right.',
        ))

    return exports.xlsx_response(buffer, exports.textlist_filename(uploaded.name, text_format))


# ------------------------------------------------------------------ SCL IO mapping

def scl_view(request):
    """The preview is rendered server-side by the same function the download uses, so
    what is on screen is exactly what the .txt will contain."""
    if request.method == 'POST':
        form = SclForm(request.POST)
        code = render_scl(form.to_params()) if form.is_valid() else ''
    else:
        form = SclForm()
        code = render_scl(SclParams())
    return render(request, 'tools/scl.html', {'form': form, 'code': code})


@require_POST
def scl_download(request):
    form = SclForm(request.POST)
    if not form.is_valid():
        return render(request, 'tools/scl.html', {'form': form, 'code': ''})
    params = form.to_params()
    return exports.text_response(render_scl(params), exports.scl_filename(params))
