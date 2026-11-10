"""Gerador de ícones vetoriais nativos em alta fidelidade com QPainter.

Elimina emojis e dependências de fontes externas, garantindo renderização
nítida em qualquer resolução (1x, 2x HiDPI) e suporte a cores customizadas.
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

_ICON_CACHE: Dict[Tuple[str, int, str], QIcon] = {}
_PIXMAP_CACHE: Dict[Tuple[str, int, str], QPixmap] = {}
_ROTATED_SYNC_ICON_CACHE: Dict[Tuple[int, str, int], QIcon] = {}


def render_vector_pixmap(
    name: str,
    size: int = 24,
    color: str = "#8B949E",
    dpr: float = 1.0,
) -> QPixmap:
    """Renderiza um ícone vetorial de alta definição para um QPixmap com suporte a HiDPI."""
    cache_key = (name, size, color, dpr)
    # Gera pixmap físico considerando a densidade de pixels do dispositivo
    phys_size = int(math.ceil(size * dpr))
    pixmap = QPixmap(phys_size, phys_size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.scale(dpr, dpr)

    qcol = QColor(color)
    pen = QPen(qcol)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

    # Coordenadas relativas ao canvas (0, 0, size, size)
    s = float(size)
    rect = QRectF(0, 0, s, s)

    if name in ("dashboard", "home", "visao_geral"):
        # 4 retângulos arredondados representando visão geral / dashboard
        pen.setWidthF(max(1.5, s * 0.08))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        m = s * 0.14
        w = s * 0.32
        h1 = s * 0.36
        h2 = s * 0.28
        # Superior esquerdo
        painter.drawRoundedRect(QRectF(m, m, w, h1), 2.5, 2.5)
        # Inferior esquerdo
        painter.drawRoundedRect(QRectF(m, m + h1 + s * 0.08, w, h2), 2.5, 2.5)
        # Superior direito
        painter.drawRoundedRect(QRectF(m + w + s * 0.08, m, w, h2), 2.5, 2.5)
        # Inferior direito
        painter.drawRoundedRect(QRectF(m + w + s * 0.08, m + h2 + s * 0.08, w, h1), 2.5, 2.5)

    elif name in ("folder", "pastas"):
        # Pasta elegante com aba superior
        pen.setWidthF(max(1.5, s * 0.08))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        m = s * 0.14
        path.moveTo(m, m + s * 0.22)
        path.lineTo(m, m + s * 0.68)
        path.quadTo(m, m + s * 0.72, m + s * 0.06, m + s * 0.72)
        path.lineTo(s - m - s * 0.06, m + s * 0.72)
        path.quadTo(s - m, m + s * 0.72, s - m, m + s * 0.68)
        path.lineTo(s - m, m + s * 0.28)
        path.quadTo(s - m, m + s * 0.22, s - m - s * 0.06, m + s * 0.22)
        path.lineTo(m + s * 0.44, m + s * 0.22)
        path.lineTo(m + s * 0.36, m + s * 0.12)
        path.quadTo(m + s * 0.32, m + s * 0.08, m + s * 0.26, m + s * 0.08)
        path.lineTo(m + s * 0.06, m + s * 0.08)
        path.quadTo(m, m + s * 0.08, m, m + s * 0.14)
        path.closeSubpath()
        painter.drawPath(path)

    elif name in ("activity", "atividade"):
        # Linha de pulso com nós suaves
        pen.setWidthF(max(1.6, s * 0.085))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(s * 0.12, s * 0.54)
        path.lineTo(s * 0.34, s * 0.54)
        path.lineTo(s * 0.44, s * 0.22)
        path.lineTo(s * 0.56, s * 0.78)
        path.lineTo(s * 0.68, s * 0.42)
        path.lineTo(s * 0.76, s * 0.54)
        path.lineTo(s * 0.88, s * 0.54)
        painter.drawPath(path)

    elif name in ("settings", "ajustes", "gear"):
        # Engrenagem moderna com furo central
        pen.setWidthF(max(1.5, s * 0.08))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = s * 0.5, s * 0.5
        r_out = s * 0.36
        r_in = s * 0.28
        r_hole = s * 0.13
        path = QPainterPath()
        num_teeth = 6
        for i in range(num_teeth * 2):
            ang = i * (math.pi / num_teeth)
            r = r_out if i % 2 == 0 else r_in
            x = cx + r * math.cos(ang)
            y = cy + r * math.sin(ang)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawEllipse(QPointF(cx, cy), r_hole, r_hole)

    elif name in ("check_circle", "sucesso", "ok"):
        # Círculo com checkmark
        cx, cy = s * 0.5, s * 0.5
        r = s * 0.40
        pen.setWidthF(max(1.8, s * 0.09))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), r, r)
        # Checkmark
        ck = QPainterPath()
        ck.moveTo(s * 0.30, s * 0.50)
        ck.lineTo(s * 0.44, s * 0.65)
        ck.lineTo(s * 0.72, s * 0.36)
        painter.drawPath(ck)

    elif name in ("check", "checkmark"):
        # Checkmark avulso
        pen.setWidthF(max(2.0, s * 0.10))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        ck = QPainterPath()
        ck.moveTo(s * 0.22, s * 0.50)
        ck.lineTo(s * 0.42, s * 0.72)
        ck.lineTo(s * 0.78, s * 0.28)
        painter.drawPath(ck)

    elif name in ("sync", "refresh"):
        # Duas setas circulares de sincronização
        pen.setWidthF(max(1.6, s * 0.085))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = s * 0.5, s * 0.5
        r = s * 0.34
        # Arco 1
        arc_rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        painter.drawArc(arc_rect, int(25 * 16), int(130 * 16))
        painter.drawArc(arc_rect, int(205 * 16), int(130 * 16))
        # Ponta de seta 1
        painter.setBrush(QBrush(qcol))
        a1 = QPainterPath()
        p1 = QPointF(cx + r * math.cos(math.radians(25)), cy - r * math.sin(math.radians(25)))
        a1.moveTo(p1)
        a1.lineTo(p1.x() + s * 0.08, p1.y() - s * 0.12)
        a1.lineTo(p1.x() - s * 0.10, p1.y() - s * 0.06)
        a1.closeSubpath()
        painter.drawPath(a1)
        # Ponta de seta 2
        a2 = QPainterPath()
        p2 = QPointF(cx + r * math.cos(math.radians(205)), cy - r * math.sin(math.radians(205)))
        a2.moveTo(p2)
        a2.lineTo(p2.x() - s * 0.08, p2.y() + s * 0.12)
        a2.lineTo(p2.x() + s * 0.10, p2.y() + s * 0.06)
        a2.closeSubpath()
        painter.drawPath(a2)

    elif name in ("pause",):
        # Duas barras verticais de pausa
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(qcol))
        w = s * 0.15
        h = s * 0.50
        y = s * 0.25
        painter.drawRoundedRect(QRectF(s * 0.30, y, w, h), 2, 2)
        painter.drawRoundedRect(QRectF(s * 0.55, y, w, h), 2, 2)

    elif name in ("play", "retomar"):
        # Triângulo play
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(qcol))
        path = QPainterPath()
        path.moveTo(s * 0.32, s * 0.24)
        path.lineTo(s * 0.74, s * 0.50)
        path.lineTo(s * 0.32, s * 0.76)
        path.closeSubpath()
        painter.drawPath(path)

    elif name in ("alert", "warning", "atencao"):
        # Triângulo com exclamação
        pen.setWidthF(max(1.6, s * 0.085))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        tri = QPainterPath()
        tri.moveTo(s * 0.50, s * 0.16)
        tri.lineTo(s * 0.86, s * 0.80)
        tri.lineTo(s * 0.14, s * 0.80)
        tri.closeSubpath()
        painter.drawPath(tri)
        # Exclamação
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(qcol))
        painter.drawRoundedRect(QRectF(s * 0.47, s * 0.36, s * 0.06, s * 0.24), 1.5, 1.5)
        painter.drawEllipse(QPointF(s * 0.50, s * 0.69), s * 0.035, s * 0.035)

    elif name in ("lock", "cadeado", "bloqueado"):
        # Cadeado vetorial
        pen.setWidthF(max(1.6, s * 0.085))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Alça do cadeado (arco invertido)
        shackle = QPainterPath()
        shackle.moveTo(s * 0.32, s * 0.44)
        shackle.lineTo(s * 0.32, s * 0.30)
        shackle.arcTo(QRectF(s * 0.32, s * 0.16, s * 0.36, s * 0.28), 180, -180)
        shackle.lineTo(s * 0.68, s * 0.44)
        painter.drawPath(shackle)
        # Corpo do cadeado
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(s * 0.24, s * 0.44, s * 0.52, s * 0.42), 2.5, 2.5)
        # Orifício da fechadura
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(qcol))
        painter.drawEllipse(QPointF(s * 0.50, s * 0.60), s * 0.045, s * 0.045)
        painter.drawRoundedRect(QRectF(s * 0.48, s * 0.62, s * 0.04, s * 0.10), 1.0, 1.0)

    elif name in ("google_drive", "drive"):
        # Losango/triângulo estilizado do Google Drive
        pen.setWidthF(max(1.5, s * 0.08))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(s * 0.36, s * 0.20)
        path.lineTo(s * 0.64, s * 0.20)
        path.lineTo(s * 0.86, s * 0.60)
        path.lineTo(s * 0.72, s * 0.84)
        path.lineTo(s * 0.14, s * 0.84)
        path.lineTo(s * 0.28, s * 0.60)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(QPointF(s * 0.36, s * 0.20), QPointF(s * 0.64, s * 0.68))
        painter.drawLine(QPointF(s * 0.64, s * 0.20), QPointF(s * 0.36, s * 0.68))

    elif name in ("clock", "aguardando", "tempo"):
        # Círculo com ponteiros de relógio
        cx, cy = s * 0.5, s * 0.5
        r = s * 0.38
        pen.setWidthF(max(1.6, s * 0.085))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), r, r)
        painter.drawLine(QPointF(cx, cy), QPointF(cx, cy - r * 0.60))
        painter.drawLine(QPointF(cx, cy), QPointF(cx + r * 0.45, cy))

    elif name in ("open_folder", "external"):
        # Pasta com setinha de abertura externa
        pen.setWidthF(max(1.5, s * 0.08))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Caixa de pasta
        box = QPainterPath()
        box.moveTo(s * 0.16, s * 0.32)
        box.lineTo(s * 0.16, s * 0.80)
        box.lineTo(s * 0.76, s * 0.80)
        box.lineTo(s * 0.76, s * 0.46)
        painter.drawPath(box)
        # Seta apontando para cima e direita
        painter.drawLine(QPointF(s * 0.40, s * 0.56), QPointF(s * 0.82, s * 0.18))
        painter.drawLine(QPointF(s * 0.58, s * 0.18), QPointF(s * 0.82, s * 0.18))
        painter.drawLine(QPointF(s * 0.82, s * 0.18), QPointF(s * 0.82, s * 0.42))

    elif name in ("info", "sobre"):
        # Círculo com letra 'i'
        cx, cy = s * 0.5, s * 0.5
        r = s * 0.38
        pen.setWidthF(max(1.6, s * 0.085))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), r, r)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(qcol))
        painter.drawEllipse(QPointF(cx, cy - r * 0.45), s * 0.04, s * 0.04)
        painter.drawRoundedRect(QRectF(cx - s * 0.035, cy - r * 0.15, s * 0.07, s * 0.40), 1.5, 1.5)

    elif name in ("chevron_down", "down"):
        pen.setWidthF(max(1.6, s * 0.085))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(s * 0.25, s * 0.38)
        path.lineTo(s * 0.50, s * 0.63)
        path.lineTo(s * 0.75, s * 0.38)
        painter.drawPath(path)

    elif name in ("chevron_right", "right"):
        pen.setWidthF(max(1.6, s * 0.085))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(s * 0.38, s * 0.25)
        path.lineTo(s * 0.63, s * 0.50)
        path.lineTo(s * 0.38, s * 0.75)
        painter.drawPath(path)

    elif name in ("trash", "clear", "limpar"):
        pen.setWidthF(max(1.5, s * 0.07))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Linha horizontal da tampa
        painter.drawLine(QPointF(s * 0.22, s * 0.30), QPointF(s * 0.78, s * 0.30))
        # Alça da tampa
        lid = QPainterPath()
        lid.moveTo(s * 0.38, s * 0.30)
        lid.lineTo(s * 0.38, s * 0.22)
        lid.lineTo(s * 0.62, s * 0.22)
        lid.lineTo(s * 0.62, s * 0.30)
        painter.drawPath(lid)
        # Cesto da lixeira
        basket = QPainterPath()
        basket.moveTo(s * 0.28, s * 0.30)
        basket.lineTo(s * 0.32, s * 0.82)
        basket.lineTo(s * 0.68, s * 0.82)
        basket.lineTo(s * 0.72, s * 0.30)
        painter.drawPath(basket)
        # Linhas internas
        painter.drawLine(QPointF(s * 0.43, s * 0.42), QPointF(s * 0.43, s * 0.70))
        painter.drawLine(QPointF(s * 0.57, s * 0.42), QPointF(s * 0.57, s * 0.70))

    else:
        # Padrão: círculo com ponto
        cx, cy = s * 0.5, s * 0.5
        pen.setWidthF(max(1.5, s * 0.08))
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), s * 0.35, s * 0.35)
        painter.drawPoint(QPointF(cx, cy))

    painter.end()
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def get_vector_icon(
    name: str,
    size: int = 24,
    color: str = "#8B949E",
    active_color: str | None = None,
) -> QIcon:
    """Retorna um QIcon com variantes normal (1x e 2x HiDPI) e ativa se fornecida."""
    cache_key = (name, size, color, active_color or "")
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]

    icon = QIcon()
    # Adiciona resoluções 1x e 2x HiDPI para o estado Normal
    pix_1x = render_vector_pixmap(name, size, color, dpr=1.0)
    pix_2x = render_vector_pixmap(name, size, color, dpr=2.0)
    icon.addPixmap(pix_1x, QIcon.Mode.Normal)
    icon.addPixmap(pix_2x, QIcon.Mode.Normal)

    # Se uma cor ativa for especificada, adiciona para Selected/Active
    if active_color:
        pix_act_1x = render_vector_pixmap(name, size, active_color, dpr=1.0)
        pix_act_2x = render_vector_pixmap(name, size, active_color, dpr=2.0)
        icon.addPixmap(pix_act_1x, QIcon.Mode.Selected)
        icon.addPixmap(pix_act_2x, QIcon.Mode.Selected)
        icon.addPixmap(pix_act_1x, QIcon.Mode.Active)
        icon.addPixmap(pix_act_2x, QIcon.Mode.Active)

    _ICON_CACHE[cache_key] = icon
    return icon


def render_rotated_sync_pixmap(
    size: int = 16,
    color: str = "#0B0F15",
    angle_degrees: float = 0.0,
    dpr: float = 1.0,
) -> QPixmap:
    """Renderiza as setas circulares de sincronização rotacionadas com precisão e suporte HiDPI."""
    phys_size = int(math.ceil(size * dpr))
    pixmap = QPixmap(phys_size, phys_size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.scale(dpr, dpr)

    s = float(size)
    cx, cy = s * 0.5, s * 0.5

    # Rotação suave no sentido horário em torno do centro geométrico
    painter.translate(cx, cy)
    painter.rotate(angle_degrees)
    painter.translate(-cx, -cy)

    qcol = QColor(color)
    pen = QPen(qcol)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setWidthF(max(1.6, s * 0.085))
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    r = s * 0.34
    arc_rect = QRectF(cx - r, cy - r, r * 2, r * 2)
    painter.drawArc(arc_rect, int(25 * 16), int(130 * 16))
    painter.drawArc(arc_rect, int(205 * 16), int(130 * 16))

    painter.setBrush(QBrush(qcol))
    a1 = QPainterPath()
    p1 = QPointF(cx + r * math.cos(math.radians(25)), cy - r * math.sin(math.radians(25)))
    a1.moveTo(p1)
    a1.lineTo(p1.x() + s * 0.08, p1.y() - s * 0.12)
    a1.lineTo(p1.x() - s * 0.10, p1.y() - s * 0.06)
    a1.closeSubpath()
    painter.drawPath(a1)

    a2 = QPainterPath()
    p2 = QPointF(cx + r * math.cos(math.radians(205)), cy - r * math.sin(math.radians(205)))
    a2.moveTo(p2)
    a2.lineTo(p2.x() - s * 0.08, p2.y() + s * 0.12)
    a2.lineTo(p2.x() + s * 0.10, p2.y() + s * 0.06)
    a2.closeSubpath()
    painter.drawPath(a2)

    painter.end()
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def render_rotated_sync_icon(
    size: int = 16,
    color: str = "#0B0F15",
    angle_degrees: float = 0.0,
) -> QIcon:
    """Retorna um QIcon com as setas de sincronização rotacionadas para todos os modos visuais."""
    norm_angle = int(round(angle_degrees)) % 360
    cache_key = (size, color, norm_angle)
    if cache_key in _ROTATED_SYNC_ICON_CACHE:
        return _ROTATED_SYNC_ICON_CACHE[cache_key]

    icon = QIcon()
    pix_1x = render_rotated_sync_pixmap(size=size, color=color, angle_degrees=norm_angle, dpr=1.0)
    pix_2x = render_rotated_sync_pixmap(size=size, color=color, angle_degrees=norm_angle, dpr=2.0)

    # Fornece pixmaps para Normal, Active, Selected e Disabled
    # O registro explícito em Disabled previne o dimming cinza automático do Qt,
    # preservando fidelidade visual e contraste com o botão desabilitado.
    icon.addPixmap(pix_1x, QIcon.Mode.Normal)
    icon.addPixmap(pix_2x, QIcon.Mode.Normal)
    icon.addPixmap(pix_1x, QIcon.Mode.Active)
    icon.addPixmap(pix_2x, QIcon.Mode.Active)
    icon.addPixmap(pix_1x, QIcon.Mode.Selected)
    icon.addPixmap(pix_2x, QIcon.Mode.Selected)
    icon.addPixmap(pix_1x, QIcon.Mode.Disabled)
    icon.addPixmap(pix_2x, QIcon.Mode.Disabled)

    _ROTATED_SYNC_ICON_CACHE[cache_key] = icon
    return icon


