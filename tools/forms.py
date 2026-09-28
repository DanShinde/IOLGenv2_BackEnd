from django import forms

from .scl import SclParams
from .textlist import FORMAT_CHOICES, FORMAT_IO_AND_TAG


class BootstrapFormMixin:
    """Same widget styling the estimator uses (estimator/forms.py). Copied rather than
    imported, because importing from estimator.forms would pull estimator.models into an
    app that deliberately has none."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'form-check-input'
            elif isinstance(field.widget, (forms.Select, forms.SelectMultiple)):
                field.widget.attrs['class'] = 'form-select'
            else:
                field.widget.attrs['class'] = 'form-control'


class TextListForm(BootstrapFormMixin, forms.Form):
    """Backs both the validate step and the download step, so the two can never disagree
    about what counts as an acceptable upload."""

    # Django's DATA_UPLOAD_MAX_MEMORY_SIZE does not cap uploaded files (it counts only
    # non-file fields), so the limit has to be enforced here rather than in settings --
    # which is just as well, since other apps in this project post very wide forms.
    MAX_UPLOAD_BYTES = 15 * 1024 * 1024

    workbook = forms.FileField(
        label='IO list',
        help_text='An .xlsx workbook. Sheets need Tag, Channel and I/O Address columns; '
                  'Ferrules is needed for the two ferrule formats.',
        widget=forms.ClearableFileInput(attrs={'accept': '.xlsx'}),
    )
    text_format = forms.TypedChoiceField(
        label='Text format',
        choices=FORMAT_CHOICES,
        coerce=int,
        initial=FORMAT_IO_AND_TAG,
        help_text='What each cell of the generated list should contain.',
    )

    def clean_workbook(self):
        uploaded = self.cleaned_data['workbook']
        if not uploaded.name.lower().endswith('.xlsx'):
            # xlrd is not installed, so .xls genuinely cannot be read -- say so rather
            # than letting pandas fail with a library error.
            raise forms.ValidationError(
                'Only .xlsx files are supported. Save the IO list as .xlsx '
                '(not .xls or .csv) and try again.'
            )
        if uploaded.size > self.MAX_UPLOAD_BYTES:
            raise forms.ValidationError(
                f'This file is {uploaded.size / (1024 * 1024):.1f} MB. The limit is '
                f'{self.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.'
            )
        return uploaded


class SclForm(BootstrapFormMixin, forms.Form):
    output_bytes = forms.IntegerField(
        label='Output bytes', min_value=0, max_value=65535, initial=SclParams.output_bytes,
        help_text='The count of the output POKE_BLK -- total bytes in the output image.',
    )
    input_bytes = forms.IntegerField(
        label='Input bytes', min_value=0, max_value=65535, initial=SclParams.input_bytes,
        help_text='Total bytes in the input image. Recorded in the header comment.',
    )
    input_db = forms.IntegerField(
        label='Input DB', min_value=1, max_value=59999, initial=SclParams.input_db,
        help_text='DB number holding the input image.',
    )
    output_db = forms.IntegerField(
        label='Output DB', min_value=1, max_value=59999, initial=SclParams.output_db,
        help_text='DB number holding the output image.',
    )
    hmi_io_db = forms.IntegerField(
        label='HMI IO DB', min_value=1, max_value=59999, initial=SclParams.hmi_io_db,
        help_text='DB number the HMI IO screen reads and writes.',
    )

    def to_params(self):
        return SclParams(**self.cleaned_data)
