"""PNG version of the stage roadmap (the detail page's Automation / Emulation timeline),
for the Project Summary Excel export's Timeline sheet. Drawn at 2x and shown at half size
in Excel so it stays sharp when a slide is zoomed."""
import io
import os

from PIL import Image, ImageDraw, ImageFont

SCALE = 2
STEP_W = 92            # px per stage at 1x -- the same for Automation and Emulation
STEPS = 7              # widest stream (Automation incl. Handover); both images use it
GUTTER_W = 64          # room for the "Phase 1" tag -- reserved on every row for a uniform look
CIRCLE = 22
LINE_H = 60            # height of one roadmap line (circle + two label lines)

STATUS_COLORS = {
    'Completed': '#28a745', 'In Progress': '#ffc107', 'Not started': '#adb5bd',
    'Hold': '#dc3545', 'Not Applicable': '#8d99ae',
}
TRACK, PROGRESS, LABEL, TAG_BG, TAG_BORDER = '#dee2e6', '#28a745', '#4b5563', '#f8f9fa', '#ced4da'

_FONT_CANDIDATES = (
    'segoeui.ttf', 'arial.ttf', 'DejaVuSans.ttf',
    os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', 'segoeui.ttf'),
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
)


def _font(size, bold=False):
    names = (('segoeuib.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf') if bold else ()) + _FONT_CANDIDATES
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _wrap(draw, text, font, max_w, max_lines=2):
    lines, current = [], ''
    for word in text.split():
        trial = f'{current} {word}'.strip()
        if draw.textlength(trial, font=font) <= max_w or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and draw.textlength(lines[-1] + '…', font=font) > max_w:
            lines[-1] = lines[-1][:-1]
        lines[-1] += '…'
    return lines


def _icon(draw, status, cx, cy, r):
    s = SCALE
    if status == 'Completed':
        draw.line([(cx - r * 0.42, cy), (cx - r * 0.1, cy + r * 0.32), (cx + r * 0.45, cy - r * 0.32)],
                  fill='white', width=int(2.2 * s), joint='curve')
    elif status == 'In Progress':
        for dx in (-0.4, 0, 0.4):
            d = 1.6 * s
            draw.ellipse([cx + dx * r - d, cy - d, cx + dx * r + d, cy + d], fill='black')
    elif status == 'Hold':
        for dx in (-0.22, 0.22):
            draw.rectangle([cx + dx * r - 1.3 * s, cy - r * 0.38, cx + dx * r + 1.3 * s, cy + r * 0.38], fill='white')
    elif status == 'Not Applicable':
        rr = r * 0.45
        draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline='white', width=int(1.6 * s))
        draw.line([(cx - rr * 0.7, cy + rr * 0.7), (cx + rr * 0.7, cy - rr * 0.7)], fill='white', width=int(1.6 * s))
    else:  # Not started: hollow ring, like the page's far fa-circle
        rr = r * 0.42
        draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline='white', width=int(1.6 * s))


def render_roadmaps(lines, show_tags, steps=STEPS):
    """lines: [(tag, [stages])] -- one roadmap per line, stacked. `steps` sets the width in
    stage slots (spacing is always STEP_W). Returns (png_bytes, w, h) at 1x display size."""
    s = SCALE
    gutter = GUTTER_W if show_tags else 0
    width, height = (gutter + STEP_W * steps) * s, max(len(lines), 1) * LINE_H * s
    img = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(img)
    label_font, tag_font = _font(9 * s), _font(9 * s, bold=True)
    r = CIRCLE * s / 2

    for row, (tag, stages) in enumerate(lines):
        top = row * LINE_H * s
        cy = top + 6 * s + r
        if show_tags and tag:
            tw = draw.textlength(tag, font=tag_font)
            x0, y0 = 2 * s, cy - 8 * s
            draw.rounded_rectangle([x0, y0, x0 + tw + 10 * s, y0 + 16 * s], radius=3 * s,
                                   fill=TAG_BG, outline=TAG_BORDER, width=s)
            draw.text((x0 + 5 * s, cy), tag, font=tag_font, fill='#212529', anchor='lm')
        if not stages:
            continue
        centers = [gutter * s + (i + 0.5) * STEP_W * s for i in range(len(stages))]
        if len(stages) > 1:
            draw.line([(centers[0], cy), (centers[-1], cy)], fill=TRACK, width=3 * s)
            done = [i for i, st in enumerate(stages) if st.status == 'Completed']
            if done:
                draw.line([(centers[0], cy), (centers[max(done)], cy)], fill=PROGRESS, width=3 * s)
        for cx, st in zip(centers, stages):
            status = st.status or 'Not started'
            draw.ellipse([cx - r - 3 * s, cy - r - 3 * s, cx + r + 3 * s, cy + r + 3 * s], fill='white')
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=STATUS_COLORS.get(status, STATUS_COLORS['Not started']))
            _icon(draw, status, cx, cy, r)
            ly = cy + r + 5 * s
            for text in _wrap(draw, st.get_name_display(), label_font, STEP_W * s - 8 * s):
                draw.text((cx, ly), text, font=label_font, fill=LABEL, anchor='mt')
                ly += 11 * s

    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    return buf.getvalue(), width // s, height // s
