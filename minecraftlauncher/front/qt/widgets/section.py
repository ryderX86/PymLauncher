from typing import overload

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLayout


class Section(QWidget):
    def __init__(
        self,
        text: str = "",
        parent=None,
        layout: type[QHBoxLayout | QVBoxLayout] = QVBoxLayout,
    ):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self._meta_layout = QVBoxLayout(self)
        self._meta_layout.setContentsMargins(5, 0, 0, 0)
        self._meta_layout.setSpacing(8)
        self._label = QLabel(text)
        self._label.setProperty("section", True)
        self._meta_layout.addWidget(self._label)
        w = QWidget()
        self._layout = layout(w)
        self._layout.setContentsMargins(10, 0, 10, 0)
        self._meta_layout.addWidget(w)

    def addWidget(
        self,
        w: QWidget,
        stretch: int | None = 0,
        alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft,
    ):
        return self._layout.addWidget(w, stretch, alignment)

    def removeWidget(self, w: QWidget):
        return self._layout.removeWidget(w)

    @overload
    def setAlignment(self, align_or_other: Qt.AlignmentFlag): ...

    @overload
    def setAlignment(
        self, align_or_other: QWidget | QLayout, align: Qt.AlignmentFlag
    ): ...

    def setAlignment(
        self,
        align_or_other: Qt.AlignmentFlag | QLayout | QWidget,
        align: Qt.AlignmentFlag | None = None,
    ):
        if not align:
            return self._layout.setAlignment(align_or_other)  # type: ignore
        else:
            return self._layout.setAlignment(
                align_or_other, align  # type: ignore
            )

    def setText(self, text: str):
        return self._label.setText(text)

    setTitle = setText

    @classmethod
    def subclass_stylesheet(cls, stylesheet: str):
        class SubSection(cls):
            _styles = stylesheet

            def __init__(
                self,
                text: str = "",
                parent=None,
                layout: type[QHBoxLayout | QVBoxLayout] = QVBoxLayout,
            ):
                super().__init__(text, parent, layout)
                self.setStyleSheet(self._styles)

        return SubSection
