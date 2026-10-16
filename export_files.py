"""Cria arquivos para download a partir do texto aprovado na conversa."""
from io import BytesIO
import csv


def create_export(content: str, kind: str) -> tuple[BytesIO, str, str]:
    if kind == 'docx':
        from docx import Document
        document = Document()
        for paragraph in content.splitlines():
            if paragraph.strip().startswith('# '):
                document.add_heading(paragraph.strip()[2:], 1)
            else:
                document.add_paragraph(paragraph)
        output = BytesIO()
        document.save(output)
        mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    elif kind == 'xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'Conteúdo'
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        pipe_rows = [line.strip('| ') for line in lines if '|' in line]
        if pipe_rows:
            rows = [[cell.strip() for cell in line.split('|')] for line in pipe_rows]
            rows = [row for row in rows if not all(set(cell) <= set('-: ') for cell in row)]
        else:
            rows = list(csv.reader(lines)) if any(',' in line for line in lines) else [[line] for line in lines]
        for row in rows[:3000]:
            sheet.append([str(cell)[:30000] for cell in row[:50]])
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for column in sheet.columns:
            from openpyxl.utils import get_column_letter
            sheet.column_dimensions[get_column_letter(column[0].column)].width = min(55, max(14, max(len(str(c.value or '')) for c in list(column)[:100]) + 2))
        output = BytesIO()
        workbook.save(output)
        mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif kind == 'pdf':
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import simpleSplit
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from pathlib import Path
        import reportlab
        output = BytesIO()
        pdf = canvas.Canvas(output, pagesize=(595, 842))
        fontpath = Path(reportlab.__file__).resolve().parent / 'fonts' / 'Vera.ttf'
        font = 'Helvetica'
        if fontpath.exists():
            if 'DejaVuSans' not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont('DejaVuSans', str(fontpath)))
            font = 'DejaVuSans'
        pdf.setFont(font, 10)
        y = 800
        for paragraph in content.splitlines():
            for line in simpleSplit(paragraph or ' ', font, 10, 505) or [' ']:
                if y < 45:
                    pdf.showPage()
                    pdf.setFont(font, 10)
                    y = 800
                pdf.drawString(45, y, line)
                y -= 15
            y -= 5
        pdf.save()
        mime = 'application/pdf'
    else:
        raise ValueError('Formato de arquivo inválido.')
    output.seek(0)
    return output, mime, f'mark-shaney.{kind}'
