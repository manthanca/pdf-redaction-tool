"""
PDF Redaction Tool
==================
A professional PDF redaction application with PyQt5 + PyMuPDF (fitz) + Pillow.
Libraries are installed automatically on first run only (tracked via a flag file).
"""

import sys
import os
import subprocess

# ──────────────────────────────────────────────
# ONE-TIME LIBRARY INSTALLATION
# ──────────────────────────────────────────────
FLAG_FILE = os.path.join(os.path.expanduser("~"), ".pdf_redaction_tool_installed")

if not os.path.exists(FLAG_FILE):
    print("Installing required libraries (first-time setup) ...")
    packages = ["PyQt5", "PyMuPDF", "Pillow"]
    for pkg in packages:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--quiet"])
    with open(FLAG_FILE, "w") as f:
        f.write("installed")
    print("Installation complete.\n")

# ──────────────────────────────────────────────
# IMPORTS (after install)
# ──────────────────────────────────────────────
import fitz                        # PyMuPDF
from PIL import Image              # Pillow

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QScrollArea, QSizePolicy,
    QMessageBox, QLineEdit, QFrame, QStatusBar, QSpacerItem,
    QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, QRect, QPoint, QSize, pyqtSignal
from PyQt5.QtGui import (
    QPixmap, QImage, QPainter, QColor, QPen, QBrush, QFont,
    QIcon, QCursor, QLinearGradient
)


# ──────────────────────────────────────────────
# COLOUR PALETTE  (White + Blue professional)
# ──────────────────────────────────────────────
C = {
    "bg":          "#F0F4FF",   # very light blue-white background
    "sidebar":     "#1A3A6B",   # deep navy sidebar
    "sidebar_btn": "#1E4D9B",   # slightly lighter nav button
    "accent":      "#2563EB",   # vivid blue – primary actions
    "accent2":     "#1D4ED8",   # darker blue hover
    "danger":      "#DC2626",   # red – destructive actions
    "danger2":     "#B91C1C",
    "success":     "#16A34A",   # green – save
    "success2":    "#15803D",
    "warn":        "#D97706",   # amber – undo/clear
    "warn2":       "#B45309",
    "canvas_bg":   "#E8EDF5",   # page canvas area
    "text_light":  "#FFFFFF",
    "text_dark":   "#1E293B",
    "divider":     "#CBD5E1",
    "header_from": "#1A3A6B",
    "header_to":   "#2563EB",
}

BTN_BASE = """
    QPushButton {{
        background-color: {bg};
        color: {fg};
        border: none;
        border-radius: 8px;
        padding: 10px 18px;
        font-size: 13px;
        font-weight: 600;
        letter-spacing: 0.3px;
    }}
    QPushButton:hover {{
        background-color: {hover};
    }}
    QPushButton:pressed {{
        background-color: {hover};
        padding-top: 12px;
        padding-bottom: 8px;
    }}
    QPushButton:disabled {{
        background-color: #94A3B8;
        color: #CBD5E1;
    }}
"""

def btn_style(bg, hover, fg="#FFFFFF"):
    return BTN_BASE.format(bg=bg, hover=hover, fg=fg)


# ──────────────────────────────────────────────
# DRAWING CANVAS  – shows one PDF page as image
# ──────────────────────────────────────────────
class DrawingCanvas(QLabel):
    """QLabel that lets the user paint black redaction rectangles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setCursor(QCursor(Qt.CrossCursor))

        self._base_pixmap: QPixmap = None   # rendered page
        self._rects: list[QRect] = []       # committed rectangles
        self._start: QPoint = None          # drag start
        self._current: QRect = None         # live rectangle while dragging
        self._enabled = False

    # ── public API ────────────────────────────
    def set_page_pixmap(self, pixmap: QPixmap):
        self._base_pixmap = pixmap
        self._rects = []
        self._current = None
        self.setFixedSize(pixmap.size())
        self._repaint()

    def clear_rects(self):
        self._rects = []
        self._current = None
        self._repaint()

    def undo_last(self):
        if self._rects:
            self._rects.pop()
            self._repaint()

    def get_rects(self) -> list[QRect]:
        return list(self._rects)

    def set_drawing_enabled(self, val: bool):
        self._enabled = val
        self.setCursor(QCursor(Qt.CrossCursor if val else Qt.ArrowCursor))

    # ── mouse events ──────────────────────────
    def mousePressEvent(self, e):
        if self._enabled and e.button() == Qt.LeftButton and self._base_pixmap:
            self._start = e.pos()
            self._current = None

    def mouseMoveEvent(self, e):
        if self._enabled and self._start and self._base_pixmap:
            self._current = QRect(self._start, e.pos()).normalized()
            self._repaint()

    def mouseReleaseEvent(self, e):
        if self._enabled and self._start and self._base_pixmap:
            rect = QRect(self._start, e.pos()).normalized()
            if rect.width() > 2 and rect.height() > 2:
                self._rects.append(rect)
            self._start = None
            self._current = None
            self._repaint()

    # ── painting ──────────────────────────────
    def _repaint(self):
        if not self._base_pixmap:
            return
        canvas = self._base_pixmap.copy()
        painter = QPainter(canvas)
        painter.setBrush(QBrush(QColor(0, 0, 0)))
        painter.setPen(Qt.NoPen)
        for r in self._rects:
            painter.drawRect(r)
        if self._current:
            painter.setBrush(QBrush(QColor(0, 0, 0, 200)))
            painter.drawRect(self._current)
        painter.end()
        self.setPixmap(canvas)


# ──────────────────────────────────────────────
# MAIN WINDOW
# ──────────────────────────────────────────────
class PDFRedactionTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Redaction Tool")
        self.setMinimumSize(1100, 750)
        self.resize(1280, 820)

        # state
        self._pdf_path: str = None
        self._doc: fitz.Document = None
        self._page_idx: int = 0
        self._zoom: float = 1.0
        self._zoom_min = 0.3
        self._zoom_max = 4.0
        # per-page redaction rectangles stored in PDF-space coords
        # { page_idx: [ fitz.Rect, ... ] }
        self._page_redactions: dict = {}

        self._build_ui()
        self._update_ui_state()

    # ══════════════════════════════════════════
    # UI CONSTRUCTION
    # ══════════════════════════════════════════
    def _build_ui(self):
        self.setStyleSheet(f"QMainWindow {{ background: {C['bg']}; }}")

        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        main_layout.addWidget(self._make_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._make_sidebar())
        body.addWidget(self._make_canvas_area(), stretch=1)
        main_layout.addLayout(body, stretch=1)

        main_layout.addWidget(self._make_status_bar())

    # ── Header ────────────────────────────────
    def _make_header(self):
        header = QFrame()
        header.setFixedHeight(64)
        header.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {C['header_from']},
                    stop:1 {C['header_to']}
                );
            }}
        """)
        lay = QHBoxLayout(header)
        lay.setContentsMargins(24, 0, 24, 0)

        icon_lbl = QLabel("🔒")
        icon_lbl.setStyleSheet("font-size: 28px;")

        title = QLabel("PDF Redaction Tool")
        title.setStyleSheet("""
            color: #FFFFFF;
            font-size: 22px;
            font-weight: 700;
            letter-spacing: 1px;
        """)

        sub = QLabel("Permanently hide sensitive information")
        sub.setStyleSheet("color: #93C5FD; font-size: 12px;")

        lay.addWidget(icon_lbl)
        lay.addSpacing(10)
        lay.addWidget(title)
        lay.addSpacing(12)
        lay.addWidget(sub)
        lay.addStretch()

        badge = QLabel("v1.0")
        badge.setStyleSheet("""
            color: #BFDBFE;
            font-size: 11px;
            font-weight: 600;
            background: rgba(255,255,255,0.15);
            border-radius: 6px;
            padding: 3px 10px;
        """)
        lay.addWidget(badge)
        return header

    # ── Sidebar ───────────────────────────────
    def _make_sidebar(self):
        sidebar = QFrame()
        sidebar.setFixedWidth(210)
        sidebar.setStyleSheet(f"QFrame {{ background: {C['sidebar']}; }}")

        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(14, 20, 14, 20)
        lay.setSpacing(10)

        def section_label(text):
            lbl = QLabel(text)
            lbl.setStyleSheet("""
                color: #93C5FD;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1.5px;
                padding-top: 10px;
            """)
            return lbl

        # FILE
        lay.addWidget(section_label("FILE"))
        self.btn_open = self._sb_btn("📂  Open PDF", C["accent"], C["accent2"])
        self.btn_open.clicked.connect(self._open_pdf)
        lay.addWidget(self.btn_open)

        self.btn_save = self._sb_btn("💾  Save Redacted PDF", C["success"], C["success2"])
        self.btn_save.clicked.connect(self._save_pdf)
        lay.addWidget(self.btn_save)

        # REDACTION
        lay.addWidget(section_label("REDACTION"))
        self.btn_clear = self._sb_btn("🗑  Clear Page Marks", C["warn"], C["warn2"])
        self.btn_clear.clicked.connect(self._clear_page)
        lay.addWidget(self.btn_clear)

        self.btn_undo = self._sb_btn("↩  Undo Last Mark", C["warn"], C["warn2"])
        self.btn_undo.clicked.connect(self._undo_last)
        lay.addWidget(self.btn_undo)

        # ZOOM
        lay.addWidget(section_label("ZOOM"))
        zoom_row = QHBoxLayout()
        self.btn_zoom_in  = self._sb_btn("＋", C["sidebar_btn"], C["accent"], small=True)
        self.btn_zoom_out = self._sb_btn("－", C["sidebar_btn"], C["accent"], small=True)
        self.btn_zoom_fit = self._sb_btn("⤢  Fit", C["sidebar_btn"], C["accent"])
        self.btn_zoom_in.clicked.connect(self._zoom_in)
        self.btn_zoom_out.clicked.connect(self._zoom_out)
        self.btn_zoom_fit.clicked.connect(self._zoom_fit)
        zoom_row.addWidget(self.btn_zoom_in)
        zoom_row.addWidget(self.btn_zoom_out)
        lay.addLayout(zoom_row)
        lay.addWidget(self.btn_zoom_fit)

        self.zoom_label = QLabel("Zoom: 100%")
        self.zoom_label.setStyleSheet("color:#93C5FD; font-size:11px; padding-left:4px;")
        lay.addWidget(self.zoom_label)

        # NAVIGATION
        lay.addWidget(section_label("NAVIGATION"))
        nav_row = QHBoxLayout()
        self.btn_prev = self._sb_btn("◀", C["sidebar_btn"], C["accent"], small=True)
        self.btn_next = self._sb_btn("▶", C["sidebar_btn"], C["accent"], small=True)
        self.btn_prev.clicked.connect(self._prev_page)
        self.btn_next.clicked.connect(self._next_page)
        nav_row.addWidget(self.btn_prev)
        nav_row.addWidget(self.btn_next)
        lay.addLayout(nav_row)

        # jump to page
        jump_row = QHBoxLayout()
        self.jump_input = QLineEdit()
        self.jump_input.setPlaceholderText("Page #")
        self.jump_input.setFixedWidth(70)
        self.jump_input.setStyleSheet("""
            QLineEdit {
                background: #243B67;
                color: #FFFFFF;
                border: 1px solid #3B5EA6;
                border-radius: 6px;
                padding: 6px 8px;
                font-size: 12px;
            }
        """)
        self.jump_input.returnPressed.connect(self._jump_to_page)
        btn_go = self._sb_btn("Go", C["accent"], C["accent2"], small=True)
        btn_go.clicked.connect(self._jump_to_page)
        jump_row.addWidget(self.jump_input)
        jump_row.addWidget(btn_go)
        lay.addLayout(jump_row)

        lay.addStretch()

        # instructions box
        info = QLabel(
            "🖱 Draw on the page to\nblack out sensitive info.\n\n"
            "💾 Save to permanently\napply all redactions."
        )
        info.setStyleSheet("""
            color: #93C5FD;
            font-size: 11px;
            background: rgba(255,255,255,0.07);
            border-radius: 8px;
            padding: 10px;
            line-height: 160%;
        """)
        info.setWordWrap(True)
        lay.addWidget(info)

        return sidebar

    def _sb_btn(self, text, bg, hover, small=False):
        btn = QPushButton(text)
        btn.setStyleSheet(btn_style(bg, hover))
        if small:
            btn.setFixedHeight(34)
        else:
            btn.setFixedHeight(40)
        return btn

    # ── Canvas Area ───────────────────────────
    def _make_canvas_area(self):
        frame = QFrame()
        frame.setStyleSheet(f"QFrame {{ background: {C['canvas_bg']}; }}")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{ background: {C['canvas_bg']}; border: none; }}
            QScrollBar:vertical {{
                background: #CBD5E1; width: 10px; border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: {C['accent']}; border-radius: 5px;
            }}
            QScrollBar:horizontal {{
                background: #CBD5E1; height: 10px; border-radius: 5px;
            }}
            QScrollBar::handle:horizontal {{
                background: {C['accent']}; border-radius: 5px;
            }}
        """)

        self.canvas = DrawingCanvas()
        self.canvas.setStyleSheet("background: white;")
        self.scroll.setWidget(self.canvas)
        lay.addWidget(self.scroll, stretch=1)

        # placeholder when no PDF
        self.placeholder = QLabel(
            "📄\n\nOpen a PDF file to get started\n\nClick  📂 Open PDF  in the sidebar"
        )
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet(f"""
            color: #64748B;
            font-size: 16px;
            background: {C['canvas_bg']};
        """)
        lay.addWidget(self.placeholder, stretch=1)
        self.scroll.hide()

        return frame

    # ── Status Bar ────────────────────────────
    def _make_status_bar(self):
        bar = QFrame()
        bar.setFixedHeight(40)
        bar.setStyleSheet(f"""
            QFrame {{
                background: {C['header_from']};
                border-top: 2px solid {C['accent']};
            }}
        """)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 20, 0)

        self.status_lbl = QLabel("Ready — Open a PDF to begin")
        self.status_lbl.setStyleSheet("color: #93C5FD; font-size: 12px;")
        lay.addWidget(self.status_lbl)

        lay.addStretch()

        # page counter   (1 / 7)
        self.page_counter = QLabel("")
        self.page_counter.setStyleSheet("""
            color: #FFFFFF;
            font-size: 14px;
            font-weight: 700;
            background: rgba(255,255,255,0.12);
            border-radius: 8px;
            padding: 4px 16px;
        """)
        self.page_counter.setAlignment(Qt.AlignCenter)
        lay.addStretch()
        lay.addWidget(self.page_counter)
        lay.addStretch()

        self.redact_count = QLabel("")
        self.redact_count.setStyleSheet("color: #FCA5A5; font-size: 12px;")
        lay.addWidget(self.redact_count)

        return bar

    # ══════════════════════════════════════════
    # STATE HELPERS
    # ══════════════════════════════════════════
    def _update_ui_state(self):
        has_doc = self._doc is not None
        self.btn_save.setEnabled(has_doc)
        self.btn_prev.setEnabled(has_doc and self._page_idx > 0)
        self.btn_next.setEnabled(has_doc and self._doc and self._page_idx < len(self._doc) - 1)
        self.btn_clear.setEnabled(has_doc)
        self.btn_undo.setEnabled(has_doc)
        self.btn_zoom_in.setEnabled(has_doc)
        self.btn_zoom_out.setEnabled(has_doc)
        self.btn_zoom_fit.setEnabled(has_doc)
        self.canvas.set_drawing_enabled(has_doc)

        if has_doc:
            total = len(self._doc)
            self.page_counter.setText(f"  {self._page_idx + 1} / {total}  ")
            self._update_redact_count()
        else:
            self.page_counter.setText("")
            self.redact_count.setText("")

        self.zoom_label.setText(f"Zoom: {int(self._zoom * 100)}%")

    def _update_redact_count(self):
        total = sum(len(v) for v in self._page_redactions.values())
        if total:
            self.redact_count.setText(f"🔲 {total} redaction(s)")
        else:
            self.redact_count.setText("")

    def _set_status(self, msg: str):
        self.status_lbl.setText(msg)

    # ══════════════════════════════════════════
    # PAGE RENDERING
    # ══════════════════════════════════════════
    def _render_page(self):
        if not self._doc:
            return
        page = self._doc[self._page_idx]

        # Render at zoom
        mat = fitz.Matrix(self._zoom, self._zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        base_pm = QPixmap.fromImage(img)

        # overlay already-committed PDF-space redactions for THIS page
        if self._page_idx in self._page_redactions and self._page_redactions[self._page_idx]:
            painter = QPainter(base_pm)
            painter.setBrush(QBrush(QColor(0, 0, 0)))
            painter.setPen(Qt.NoPen)
            for frect in self._page_redactions[self._page_idx]:
                # convert PDF coords → screen coords
                x0 = frect.x0 * self._zoom
                y0 = frect.y0 * self._zoom
                x1 = frect.x1 * self._zoom
                y1 = frect.y1 * self._zoom
                painter.drawRect(int(x0), int(y0), int(x1 - x0), int(y1 - y0))
            painter.end()

        self.canvas.set_page_pixmap(base_pm)
        self.scroll.show()
        self.placeholder.hide()
        self._update_ui_state()

    # ══════════════════════════════════════════
    # ACTIONS
    # ══════════════════════════════════════════
    def _open_pdf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open PDF File", "", "PDF Files (*.pdf)"
        )
        if not path:
            return
        try:
            self._doc = fitz.open(path)
            self._pdf_path = path
            self._page_idx = 0
            self._page_redactions = {}
            self._zoom = 1.0
            self._render_page()
            self._set_status(f"Opened: {os.path.basename(path)}  ({len(self._doc)} pages)")
        except Exception as ex:
            QMessageBox.critical(self, "Error", f"Could not open PDF:\n{ex}")

    def _prev_page(self):
        if not self._doc or self._page_idx == 0:
            return
        self._commit_canvas_rects()
        self._page_idx -= 1
        self._render_page()

    def _next_page(self):
        if not self._doc or self._page_idx >= len(self._doc) - 1:
            return
        self._commit_canvas_rects()
        self._page_idx += 1
        self._render_page()

    def _jump_to_page(self):
        if not self._doc:
            return
        try:
            target = int(self.jump_input.text()) - 1
        except ValueError:
            QMessageBox.warning(self, "Invalid", "Please enter a valid page number.")
            return
        if target < 0 or target >= len(self._doc):
            QMessageBox.warning(self, "Out of Range",
                                f"Page must be between 1 and {len(self._doc)}.")
            return
        self._commit_canvas_rects()
        self._page_idx = target
        self.jump_input.clear()
        self._render_page()

    def _clear_page(self):
        if not self._doc:
            return
        self.canvas.clear_rects()
        self._page_redactions.pop(self._page_idx, None)
        self._update_ui_state()
        self._set_status(f"Cleared marks on page {self._page_idx + 1}")

    def _undo_last(self):
        if not self._doc:
            return
        self.canvas.undo_last()
        # Also trim from stored list if any committed rects
        if self._page_idx in self._page_redactions and self._page_redactions[self._page_idx]:
            self._page_redactions[self._page_idx].pop()
        self._update_ui_state()
        self._set_status("Undone last redaction mark")

    # ── Zoom ──────────────────────────────────
    def _zoom_in(self):
        self._commit_canvas_rects()
        self._zoom = min(self._zoom * 1.25, self._zoom_max)
        self._render_page()

    def _zoom_out(self):
        self._commit_canvas_rects()
        self._zoom = max(self._zoom / 1.25, self._zoom_min)
        self._render_page()

    def _zoom_fit(self):
        if not self._doc:
            return
        self._commit_canvas_rects()
        page = self._doc[self._page_idx]
        avail_w = self.scroll.viewport().width() - 20
        avail_h = self.scroll.viewport().height() - 20
        zoom_w = avail_w / page.rect.width
        zoom_h = avail_h / page.rect.height
        self._zoom = max(self._zoom_min, min(zoom_w, zoom_h, self._zoom_max))
        self._render_page()

    # ── Commit canvas rects to PDF-space ──────
    def _commit_canvas_rects(self):
        """
        Take whatever is drawn on the canvas and store in PDF-space coordinates
        so they survive zoom changes and page navigation.
        """
        if not self._doc:
            return
        screen_rects = self.canvas.get_rects()
        if not screen_rects:
            return

        page = self._doc[self._page_idx]
        pdf_rects = []
        for sr in screen_rects:
            # convert screen coords back to PDF coords
            x0 = sr.left()   / self._zoom
            y0 = sr.top()    / self._zoom
            x1 = sr.right()  / self._zoom
            y1 = sr.bottom() / self._zoom
            # clamp to page bounds
            x0 = max(0, min(x0, page.rect.width))
            y0 = max(0, min(y0, page.rect.height))
            x1 = max(0, min(x1, page.rect.width))
            y1 = max(0, min(y1, page.rect.height))
            pdf_rects.append(fitz.Rect(x0, y0, x1, y1))

        self._page_redactions[self._page_idx] = pdf_rects
        self._update_ui_state()

    # ── Save ──────────────────────────────────
    def _save_pdf(self):
        if not self._doc:
            return

        # commit any unsaved canvas marks
        self._commit_canvas_rects()

        if not any(self._page_redactions.values()):
            QMessageBox.information(self, "Nothing to Redact",
                                    "No redaction marks found.\nDraw black marks first.")
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save Redacted PDF",
            os.path.splitext(self._pdf_path)[0] + "_REDACTED.pdf",
            "PDF Files (*.pdf)"
        )
        if not save_path:
            return

        try:
            # Work on a fresh copy to avoid modifying open document
            tmp_doc = fitz.open(self._pdf_path)

            for page_idx, rects in self._page_redactions.items():
                if not rects:
                    continue
                page = tmp_doc[page_idx]
                for frect in rects:
                    # add_redact_annot + apply_redactions truly DESTROYS
                    # the underlying content (text, images) – making it
                    # completely unrecoverable.
                    annot = page.add_redact_annot(frect, fill=(0, 0, 0))
                # apply all redact annotations on this page
                page.apply_redactions(
                    images=fitz.PDF_REDACT_IMAGE_PIXELS,   # erase image pixels too
                    graphics=fitz.PDF_REDACT_LINE_ART_NONE
                )

            tmp_doc.save(save_path, garbage=4, deflate=True)
            tmp_doc.close()

            self._set_status(f"Saved: {os.path.basename(save_path)}")
            QMessageBox.information(
                self, "Saved Successfully",
                f"Redacted PDF saved to:\n{save_path}\n\n"
                "All marked content has been permanently and irrecoverably removed."
            )

        except Exception as ex:
            QMessageBox.critical(self, "Save Error", f"Could not save PDF:\n{ex}")

    # ── Window close – clean up ───────────────
    def closeEvent(self, e):
        if self._doc:
            self._doc.close()
        e.accept()


# ──────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("PDF Redaction Tool")

    # Global font
    font = QFont("Segoe UI", 10)
    font.setHintingPreference(QFont.PreferFullHinting)
    app.setFont(font)

    window = PDFRedactionTool()
    window.show()
    sys.exit(app.exec_())
