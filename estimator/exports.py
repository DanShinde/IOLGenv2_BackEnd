"""Renders the estimate built by calculations.build_project_estimate() into Excel
(openpyxl) and PDF (reportlab). Both consume the exact same data structure so the two
formats -- and the on-screen report -- can never disagree with each other.
"""
from io import BytesIO

from django.http import HttpResponse
from django.utils.text import slugify

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HEADER_FILL = PatternFill(start_color='4F46E5', end_color='4F46E5', fill_type='solid')
HEADER_FONT = Font(color='FFFFFF', bold=True)
TOTAL_FILL = PatternFill(start_color='EEF2FF', end_color='EEF2FF', fill_type='solid')


def _filename(project, ext):
    return f"{slugify(project.name) or 'project'}-estimate.{ext}"


# --------------------------------------------------------------------------- Excel

def render_project_report_excel(estimate):
    wb = Workbook()
    _write_summary_sheet(wb.active, estimate)
    for group in estimate['category_groups']:
        _write_breakdown_sheet(wb.create_sheet(group['label'][:31]), group)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    response = HttpResponse(
        buffer.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{_filename(estimate["project"], "xlsx")}"'
    return response


def _write_summary_sheet(ws, estimate):
    project = estimate['project']
    ws.title = 'Summary'
    ws.sheet_view.showGridLines = False

    ws['A1'] = f"Estimate: {project.name}"
    ws['A1'].font = Font(size=16, bold=True, color='1E293B')
    ws.merge_cells('A1:E1')

    # Headline figure: the final report is about man-days above all else.
    ws['A2'] = f"{float(estimate['grand_total_days']):.2f} man-days"
    ws['A2'].font = Font(size=22, bold=True, color='4F46E5')
    ws.merge_cells('A2:E2')
    ws['A3'] = f"@ {project.minutes_per_working_day} min/working day"
    ws['A3'].font = Font(italic=True, color='64748B')
    ws.merge_cells('A3:E3')

    ws['A4'] = f"Customer: {project.customer or '-'}   |   Complexity: {project.complexity.name} (x{project.complexity.multiplier})"
    ws['A4'].font = Font(italic=True, color='64748B')
    ws.merge_cells('A4:E4')

    row = 5
    for group in estimate['category_groups']:
        row += 1
        ws.cell(row=row, column=1, value=f"{group['label']}:").font = Font(bold=True, color='64748B')
        ws.cell(row=row, column=2, value=f"{float(group['total_days']):.2f} man-days").font = Font(bold=True, color='4F46E5')

    if len(estimate['zone_groups']) > 1:
        row += 1
        ws.cell(row=row, column=1, value='By Zone:').font = Font(bold=True, color='64748B')
        for zg in estimate['zone_groups']:
            row += 1
            ws.cell(row=row, column=1, value=zg['zone']).font = Font(color='64748B')
            ws.cell(row=row, column=2, value=f"{float(zg['grand_total_days']):.2f} man-days").font = Font(bold=True, color='4F46E5')

    row += 2
    headers = ['Zone', 'Segment', 'Module Type', 'Count', 'Row Total (min)', 'Row Total (man-days)']
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=col, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    row += 1

    for r in estimate['rows']:
        ws.cell(row=row, column=1, value=r['zone'])
        ws.cell(row=row, column=2, value=r['segment'].name)
        ws.cell(row=row, column=3, value=r['module_type'].name)
        ws.cell(row=row, column=4, value=r['effective_count'])
        ws.cell(row=row, column=5, value=float(r['row_total_minutes']))
        days_cell = ws.cell(row=row, column=6, value=round(float(r['row_total_days']), 2))
        days_cell.font = Font(bold=True, color='4F46E5')
        row += 1

    row += 1
    ws.cell(row=row, column=1, value='Grand Total').font = Font(bold=True)
    ws.cell(row=row, column=1).fill = TOTAL_FILL
    ws.cell(row=row, column=2, value=f"{float(estimate['grand_total_minutes'])} min").fill = TOTAL_FILL
    ws.cell(row=row, column=3, value=f"{float(estimate['grand_total_hours']):.2f} hrs").fill = TOTAL_FILL
    ws.cell(row=row, column=4, value=f"{float(estimate['grand_total_days']):.2f} man-days").fill = TOTAL_FILL

    ws.column_dimensions['A'].width = 18
    ws.column_dimensions['B'].width = 20
    ws.column_dimensions['C'].width = 24
    ws.column_dimensions['D'].width = 10
    ws.column_dimensions['E'].width = 16
    ws.column_dimensions['F'].width = 18


def _write_breakdown_sheet(ws, group):
    """One row per Activity in this category, with its total man-days -- the
    per-module detail already lives on the Summary sheet's Module Summary table, so
    this sheet answers a different question ("where does the time in this category
    go") rather than repeating the same rows again with a wide activity-per-column
    matrix."""
    ws.sheet_view.showGridLines = False

    ws.cell(row=1, column=1, value=group['label']).font = Font(size=14, bold=True, color='1E293B')
    ws.merge_cells('A1:B1')

    ws.cell(row=2, column=1, value='Activity').font = HEADER_FONT
    ws.cell(row=2, column=1).fill = HEADER_FILL
    ws.cell(row=2, column=2, value='Total (man-days)').font = HEADER_FONT
    ws.cell(row=2, column=2).fill = HEADER_FILL
    ws.cell(row=2, column=2).alignment = Alignment(horizontal='center', wrap_text=True)

    row = 3
    for at in group['activity_totals']:
        ws.cell(row=row, column=1, value=at['activity'].name)
        cell = ws.cell(row=row, column=2, value=round(float(at['total_days']), 3))
        cell.alignment = Alignment(horizontal='center')
        row += 1

    ws.cell(row=row, column=1, value=f"{group['label']} Total").font = Font(bold=True)
    ws.cell(row=row, column=1).fill = TOTAL_FILL
    total_cell = ws.cell(row=row, column=2, value=round(float(group['total_days']), 2))
    total_cell.font = Font(bold=True, color='4F46E5')
    total_cell.fill = TOTAL_FILL
    total_cell.alignment = Alignment(horizontal='center')

    ws.column_dimensions['A'].width = 34
    ws.column_dimensions['B'].width = 20


# --------------------------------------------------------------------------- PDF

def render_project_report_pdf(estimate):
    project = estimate['project']
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('ReportTitle', parent=styles['Title'], textColor=colors.HexColor('#1E293B'))
    headline_style = ParagraphStyle('Headline', parent=styles['Title'], fontSize=32, leading=36,
                                     textColor=colors.HexColor('#4F46E5'), spaceBefore=4, spaceAfter=0)
    heading_style = ParagraphStyle('SectionHeading', parent=styles['Heading2'], textColor=colors.HexColor('#1E293B'),
                                    spaceBefore=14, spaceAfter=6)
    meta_style = ParagraphStyle('Meta', parent=styles['Normal'], textColor=colors.HexColor('#64748B'))

    story = [
        Paragraph(f"Estimate: {project.name}", title_style),
        # The final report is about man-days above all else -- lead with it.
        Paragraph(f"{estimate['grand_total_days']:.2f} man-days", headline_style),
        Paragraph(f"@ {estimate['minutes_per_day']} min/working day", meta_style),
        Spacer(1, 0.3 * cm),
        Paragraph(
            f"Customer: {project.customer or '-'} &nbsp;|&nbsp; "
            f"Complexity: {project.complexity.name} (x{project.complexity.multiplier})",
            meta_style,
        ),
        Spacer(1, 0.4 * cm),
    ]

    if estimate['warnings']:
        for w in estimate['warnings']:
            story.append(Paragraph(f"&#9888; {w}", ParagraphStyle('Warn', parent=meta_style, textColor=colors.HexColor('#D97706'))))
        story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph('Module Summary', heading_style))
    story.append(_module_summary_table(estimate))

    if len(estimate['zone_groups']) > 1:
        story.append(Paragraph('By Zone', heading_style))
        story.append(_zone_summary_table(estimate))

    for group in estimate['category_groups']:
        story.append(Paragraph(
            f"{group['label']} &mdash; Activity Totals "
            f"<font color='#4F46E5'>({group['total_days']:.2f} man-days total)</font>",
            heading_style,
        ))
        story.append(_activity_totals_table(group))
        story.append(Spacer(1, 0.3 * cm))

    story.append(Spacer(1, 0.3 * cm))
    story.append(_grand_total_table(estimate))

    doc.build(story)
    buffer.seek(0)

    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{_filename(project, "pdf")}"'
    return response


def _module_summary_table(estimate):
    data = [['Zone', 'Segment', 'Module Type', 'Count', 'Row Total (min)', 'Row Total (man-days)']]
    for r in estimate['rows']:
        data.append([
            r['zone'],
            r['segment'].name,
            r['module_type'].name,
            str(r['effective_count']),
            f"{r['row_total_minutes']:.1f}",
            f"{r['row_total_days']:.2f}",
        ])
    table = Table(data, colWidths=[3.5 * cm, 4 * cm, 5.5 * cm, 2 * cm, 4.5 * cm, 4.5 * cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('FONTNAME', (5, 1), (5, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (5, 1), (5, -1), colors.HexColor('#4F46E5')),
    ]))
    return table


def _zone_summary_table(estimate):
    data = [['Zone', 'Module Rows', 'Man-days']]
    for zg in estimate['zone_groups']:
        data.append([zg['zone'], str(len(zg['rows'])), f"{zg['grand_total_days']:.2f}"])
    table = Table(data, colWidths=[8 * cm, 5 * cm, 5 * cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('FONTNAME', (2, 1), (2, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (2, 1), (2, -1), colors.HexColor('#4F46E5')),
    ]))
    return table


def _activity_totals_table(group):
    """One row per Activity in this category, with its total man-days -- see
    _write_breakdown_sheet's docstring for why this replaced the old wide
    activity-per-column matrix of every module row."""
    data = [['Activity', 'Total (man-days)']]
    for at in group['activity_totals']:
        data.append([at['activity'].name, f"{at['total_days']:.3f}"])
    data.append([f"{group['label']} Total", f"{group['total_days']:.2f}"])

    table = Table(data, colWidths=[12 * cm, 6 * cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EEF2FF')),
        ('TEXTCOLOR', (1, -1), (1, -1), colors.HexColor('#4F46E5')),
    ]))
    return table


def _grand_total_table(estimate):
    data = [
        ['Man-days', 'Hours', 'Minutes'],
        [
            f"{estimate['grand_total_days']:.2f}",
            f"{estimate['grand_total_hours']:.2f}",
            f"{estimate['grand_total_minutes']:.1f}",
        ],
    ]
    table = Table(data, colWidths=[7 * cm] * 3)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, 1), 14),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#4F46E5')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    return table
