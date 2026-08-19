import os
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from reportlab.lib.pagesizes import letter, A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from app.config import settings

logger = logging.getLogger(__name__)

PDF_OUTPUT_DIR = "generated_pdfs"
os.makedirs(PDF_OUTPUT_DIR, exist_ok=True)

# Register Traditional Chinese Font
def init_chinese_font():
    font_name = "Helvetica"
    # Try common Windows font paths first
    windows_fonts = [
        ("MSJhengHei", "C:/Windows/Fonts/msjh.ttc"),
        ("MSJhengHeiBold", "C:/Windows/Fonts/msjhbd.ttc"),
        ("MingLiU", "C:/Windows/Fonts/mingliu.ttc"),
        ("KaiU", "C:/Windows/Fonts/kaiu.ttf"),
        ("NotoSansTC", "app/static/fonts/NotoSansTC-Regular.ttf")
    ]
    for name, path in windows_fonts:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                logger.info(f"Registered TTF Font: {name} from {path}")
                return name
            except Exception as e:
                logger.warning(f"Failed to register TTF {name}: {e}")

    # Fallback to ReportLab built-in Asian CID Fonts
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("MSung-Light"))
        return "MSung-Light"
    except Exception as e:
        logger.warning(f"Could not register CID Font: {e}")
        return "Helvetica"

CHINESE_FONT = init_chinese_font()

class PDFService:
    def __init__(self):
        self.font_name = CHINESE_FONT

    def generate_schedule_pdf(self, schedule_data: Dict[str, Any], group_name: str = "三總保全內部群") -> Dict[str, str]:
        """
        Generates an A4 Landscape Shift Schedule PDF.
        Returns: {"file_id": "...", "file_path": "...", "filename": "..."}
        """
        file_id = str(uuid.uuid4())
        tab_name = schedule_data.get("tab_name", "排班表")
        filename = f"班表_{tab_name}_{datetime.now().strftime('%Y%m%d_%H%M')}_{file_id[:8]}.pdf"
        file_path = os.path.join(PDF_OUTPUT_DIR, f"{file_id}.pdf")

        # Landscape A4 for wide table view
        doc = SimpleDocTemplate(
            file_path,
            pagesize=landscape(A4),
            rightMargin=20,
            leftMargin=20,
            topMargin=20,
            bottomMargin=20
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            name="TitleStyle",
            fontName=self.font_name,
            fontSize=16,
            leading=22,
            alignment=1, # Center
            textColor=colors.HexColor("#1e293b")
        )
        subtitle_style = ParagraphStyle(
            name="SubtitleStyle",
            fontName=self.font_name,
            fontSize=10,
            leading=14,
            alignment=1, # Center
            textColor=colors.HexColor("#64748b")
        )
        cell_style = ParagraphStyle(
            name="CellStyle",
            fontName=self.font_name,
            fontSize=8.5,
            leading=11,
            alignment=1, # Center
            textColor=colors.HexColor("#1e293b")
        )
        header_cell_style = ParagraphStyle(
            name="HeaderCellStyle",
            fontName=self.font_name,
            fontSize=9,
            leading=12,
            alignment=1, # Center
            textColor=colors.white
        )

        elements = []

        # Header Title
        title_text = f"【三軍總醫院 保全勤務排班表】 - {group_name} ({tab_name})"
        subtitle_text = f"製表時間：{datetime.now().strftime('%Y年%m月%d日 %H:%M')} ｜ 權限控制：內部機密 請勿轉傳"

        elements.append(Paragraph(title_text, title_style))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(subtitle_text, subtitle_style))
        elements.append(Spacer(1, 12))

        # Build Table Data
        columns = schedule_data.get("columns", [])
        rows = schedule_data.get("rows", [])

        if not columns or not rows:
            elements.append(Paragraph("查無排班明細資料", subtitle_style))
        else:
            table_data = []
            # Table Header
            header_row = [Paragraph(f"<b>{col}</b>", header_cell_style) for col in columns]
            table_data.append(header_row)

            # Table Rows (limit to first 35 rows per PDF if too large, or page auto wraps)
            for r in rows[:35]:
                row_items = [Paragraph(str(r.get(col, "")), cell_style) for col in columns]
                table_data.append(row_items)

            col_count = len(columns)
            # Total width for landscape A4 is ~800pt
            avail_width = 800
            col_widths = [avail_width / col_count] * col_count

            # Table Styling
            t = Table(table_data, colWidths=col_widths, repeatRows=1)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0284c7")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#94a3b8")),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(t)

        # Footer notes
        elements.append(Spacer(1, 10))
        footer_style = ParagraphStyle(
            name="FooterStyle",
            fontName=self.font_name,
            fontSize=8,
            leading=10,
            alignment=2, # Right
            textColor=colors.HexColor("#94a3b8")
        )
        elements.append(Paragraph("本文件由 LINE 保全排班機器人即時產生，手機端無暫存，資料以雲端 Google 試算表最新版為準。", footer_style))

        doc.build(elements)
        logger.info(f"Generated PDF at {file_path} for group {group_name}")

        return {
            "file_id": file_id,
            "file_path": file_path,
            "filename": filename
        }

pdf_service = PDFService()
