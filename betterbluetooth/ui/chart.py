from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import theme

GAP = 45 * 60


class BatteryChart(QWidget):
    """Battery level over time; gaps longer than GAP break the line."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumHeight(190)
        self._points: list[tuple[int, int]] = []
        self._start = 0
        self._end = 1
        self._hover: tuple[int, int] | None = None
        self.setMouseTracking(True)

    def set_data(self, points: list[tuple[int, int]], start: int, end: int | None = None) -> None:
        self._points = points
        self._start = start
        self._end = end or int(time.time())
        self._hover = None
        self.update()

    def _plot_rect(self) -> QRectF:
        return QRectF(34, 10, self.width() - 44, self.height() - 34)

    def _map(self, r: QRectF, ts: int, level: int) -> QPointF:
        span = max(1, self._end - self._start)
        x = r.left() + (ts - self._start) / span * r.width()
        y = r.bottom() - level / 100 * r.height()
        return QPointF(x, y)

    def mouseMoveEvent(self, e):  # noqa: N802
        if not self._points:
            return
        r = self._plot_rect()
        x = e.position().x()
        best = min(self._points, key=lambda pt: abs(self._map(r, *pt).x() - x))
        if best != self._hover:
            self._hover = best
            self.update()

    def leaveEvent(self, e):  # noqa: N802
        self._hover = None
        self.update()

    def paintEvent(self, _e):  # noqa: N802
        p = theme.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r = self._plot_rect()
        small = painter.font()
        small.setPixelSize(11)
        painter.setFont(small)

        grid = QColor(p.border)
        for level in (0, 25, 50, 75, 100):
            y = r.bottom() - level / 100 * r.height()
            painter.setPen(QPen(grid, 1, Qt.SolidLine if level in (0, 100) else Qt.DashLine))
            painter.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            painter.setPen(p.color("secondary"))
            painter.drawText(QRectF(0, y - 8, r.left() - 6, 16), Qt.AlignRight | Qt.AlignVCenter, f"{level}")

        span = self._end - self._start
        fmt = "%H:%M" if span <= 2 * 86400 else "%m-%d"
        for i in range(5):
            ts = self._start + span * i / 4
            x = r.left() + r.width() * i / 4
            align = Qt.AlignLeft if i == 0 else Qt.AlignRight if i == 4 else Qt.AlignHCenter
            box = QRectF(x - 40, r.bottom() + 6, 80, 16)
            if i == 0:
                box = QRectF(x, r.bottom() + 6, 80, 16)
            elif i == 4:
                box = QRectF(x - 80, r.bottom() + 6, 80, 16)
            painter.drawText(box, align | Qt.AlignTop, datetime.fromtimestamp(ts).strftime(fmt))

        if not self._points:
            painter.setPen(p.color("secondary"))
            f = painter.font()
            f.setPixelSize(13)
            painter.setFont(f)
            painter.drawText(r, Qt.AlignCenter, "暂无数据\n设备连接后会自动记录电量")
            return

        segments: list[list[tuple[int, int]]] = [[self._points[0]]]
        for prev, cur in zip(self._points, self._points[1:]):
            if cur[0] - prev[0] > GAP:
                segments.append([])
            segments[-1].append(cur)

        accent = p.color("accent")
        for seg in segments:
            pts = [self._map(r, *pt) for pt in seg]
            line = QPainterPath(pts[0])
            for a, b in zip(pts, pts[1:]):
                line.lineTo(QPointF(b.x(), a.y()))
                line.lineTo(b)
            if len(pts) == 1:
                line.lineTo(pts[0] + QPointF(2, 0))
            area = QPainterPath(line)
            area.lineTo(QPointF(pts[-1].x(), r.bottom()))
            area.lineTo(QPointF(pts[0].x(), r.bottom()))
            area.closeSubpath()
            grad = QLinearGradient(0, r.top(), 0, r.bottom())
            top = QColor(accent)
            top.setAlpha(70)
            bottom = QColor(accent)
            bottom.setAlpha(5)
            grad.setColorAt(0, top)
            grad.setColorAt(1, bottom)
            painter.fillPath(area, grad)
            painter.setPen(QPen(accent, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(line)

        if self._hover:
            pt = self._map(r, *self._hover)
            painter.setPen(QPen(p.color("secondary"), 1, Qt.DotLine))
            painter.drawLine(QPointF(pt.x(), r.top()), QPointF(pt.x(), r.bottom()))
            painter.setPen(QPen(p.color("bg"), 2))
            painter.setBrush(accent)
            painter.drawEllipse(pt, 4.5, 4.5)
            text = f"{self._hover[1]}%  {datetime.fromtimestamp(self._hover[0]).strftime('%m-%d %H:%M')}"
            fm = painter.fontMetrics()
            w = fm.horizontalAdvance(text) + 14
            box = QRectF(min(max(r.left(), pt.x() - w / 2), r.right() - w), r.top(), w, 20)
            painter.setPen(QPen(p.color("border"), 1))
            painter.setBrush(p.color("menu_bg"))
            painter.drawRoundedRect(box, 4, 4)
            painter.setPen(p.color("text"))
            painter.drawText(box, Qt.AlignCenter, text)
