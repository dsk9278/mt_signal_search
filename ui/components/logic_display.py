from typing import Any, Dict, List

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class LogicDisplayComponent(QWidget):
    """ロジック表示（グレーのカード3段）"""

    def __init__(self, favorites_service, parent=None):
        super().__init__(parent)
        self._favorites_service = favorites_service
        self._logic_slots: Dict[int, List[Dict[str, Any]]] = {1: [], 2: [], 3: []}
        self._slot_layouts: Dict[int, QVBoxLayout] = {}
        self.setup_ui()

    def setup_ui(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        for i in range(1, 4):
            layout.addWidget(self._create_logic_widget(i, f"ロジック{i}"))
        layout.addStretch()
        self.setLayout(layout)

    def _create_logic_widget(self, slot_no: int, logic_name: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet(
            "QWidget { background-color: #f5f5f5; border-radius: 8px; margin: 5px; }"
        )
        w.setMinimumHeight(120)
        lay = QVBoxLayout()

        head = QHBoxLayout()
        title = QLabel(logic_name)
        f = QFont()
        f.setBold(True)
        title.setFont(f)
        star_btn = QPushButton("⭐")
        star_btn.setFixedSize(30, 30)
        self._update_star(star_btn, logic_name)
        star_btn.clicked.connect(lambda: self._toggle_fav(logic_name, star_btn))
        head.addWidget(title)
        head.addStretch()
        head.addWidget(star_btn)
        lay.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet('QScrollArea { border: none; }')

        container = QWidget()
        container.setStyleSheet('background-color: #d9d9d9; border-radius: 6px;')
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(12, 12, 12, 12)
        container_layout.setSpacing(8)
        scroll.setWidget(container)

        lay.addWidget(scroll)

        self._slot_layouts[slot_no] = container_layout
        self._refresh_slot(slot_no)

        lay.addStretch()
        w.setLayout(lay)
        return w

    def _update_star(self, b: QPushButton, logic_name: str) -> None:
        is_fav = self._favorites_service.is_favorite(logic_name)
        color = "#ffeb3b" if is_fav else "white"
        hover = "#fdd835" if is_fav else "#f0f0f0"
        b.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {color};
                border: 1px solid #ddd;
                border-radius: 15px;
            }}
            QPushButton:hover {{ background-color: {hover}; }}
        """
        )

    def _toggle_fav(self, logic_name: str, b: QPushButton) -> None:
        if self._favorites_service.toggle_favorite(logic_name):
            self._update_star(b, logic_name)
            QMessageBox.information(self, "お気に入り", f"'{logic_name}' を切り替えました。")

    def add_signal(self, slot_no: int, signal: Any) -> None:
        if slot_no not in self._logic_slots:
            return
        normalized = self._normalize_signal(signal)
        self._logic_slots[slot_no].append(normalized)
        self._refresh_slot(slot_no)

    def remove_signal(self, slot_no: int, signal: Dict[str, Any]) -> None:
        if slot_no not in self._logic_slots:
            return
        slot = self._logic_slots[slot_no]
        try:
            slot.remove(signal)
        except ValueError:
            sid = signal.get("signal_id")
            self._logic_slots[slot_no] = [s for s in slot if s.get("signal_id") != sid]
        self._refresh_slot(slot_no)

    def _refresh_slot(self, slot_no: int) -> None:
        layout = self._slot_layouts.get(slot_no)
        if layout is None:
            return
        self._clear_layout(layout)
        signals = self._logic_slots.get(slot_no, [])
        if not signals:
            placeholder = QLabel("信号が追加されていません。")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet(
                "color: #666666; background-color: rgba(255,255,255,0.4); padding: 12px; border-radius: 6px;"
            )
            placeholder.setWordWrap(True)
            layout.addWidget(placeholder)
            layout.addStretch()
            return

        for sig in signals:
            layout.addWidget(self._create_signal_row(slot_no, sig))
        layout.addStretch()

    def _create_signal_row(self, slot_no: int, signal: Dict[str, Any]) -> QWidget:
        row = QWidget()
        row.setStyleSheet(
            "QWidget { background-color: white; border: 1px solid #cccccc; border-radius: 6px; }"
        )
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(12, 8, 12, 8)
        row_layout.setSpacing(8)

        label = QLabel(self._format_signal_text(signal))
        label.setWordWrap(True)

        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(28, 28)
        remove_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #f5f5f5;
                border: 1px solid #cccccc;
                border-radius: 14px;
            }
            QPushButton:hover {
                background-color: #ffdddd;
            }
            """
        )
        remove_btn.clicked.connect(lambda _, s=signal: self.remove_signal(slot_no, s))

        row_layout.addWidget(label, 1)
        row_layout.addWidget(remove_btn, 0, Qt.AlignTop)
        return row

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                del item

    def _normalize_signal(self, signal: Any) -> Dict[str, Any]:
        if isinstance(signal, dict):
            return dict(signal)
        attrs = {
            "signal_id": getattr(signal, "signal_id", ""),
            "signal_type": getattr(signal, "signal_type", ""),
            "description": getattr(signal, "description", ""),
            "from_box": getattr(signal, "from_box", ""),
            "via_boxes": getattr(signal, "via_boxes", ()),
            "to_box": getattr(signal, "to_box", ""),
        }
        if hasattr(signal, "program_address"):
            attrs["program_address"] = getattr(signal, "program_address")
        if hasattr(signal, "logic_group"):
            attrs["logic_group"] = getattr(signal, "logic_group")
        return attrs

    def _format_signal_text(self, signal: Dict[str, Any]) -> str:
        signal_id = signal.get("signal_id") or "(不明)"
        signal_type = signal.get("signal_type")
        if hasattr(signal_type, "value"):
            signal_type = signal_type.value
        signal_type = signal_type or ""
        description = signal.get("description") or ""
        from_box = signal.get("from_box") or ""
        to_box = signal.get("to_box") or ""
        via_boxes = signal.get("via_boxes") or []
        via_text = ", ".join(via_boxes) if isinstance(via_boxes, (list, tuple)) else str(via_boxes)

        parts = [signal_id]
        if signal_type:
            parts.append(f"[{signal_type}]")
        if description:
            parts.append(description)

        location_parts = []
        if from_box:
            location_parts.append(f"From: {from_box}")
        if via_text:
            location_parts.append(f"Via: {via_text}")
        if to_box:
            location_parts.append(f"To: {to_box}")

        if location_parts:
            parts.append(" | ".join(location_parts))

        return " - ".join(parts)
