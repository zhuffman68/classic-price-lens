"""One search field style and a readable, accessible trailing clear control."""
from pathlib import Path
from PySide6.QtCore import QSize,Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QLineEdit,QToolButton


class SearchField(QLineEdit):
    def __init__(self,placeholder,parent=None):
        super().__init__(parent);self.setPlaceholderText(placeholder);self.setAccessibleName('Search Classic World')
        self.setClearButtonEnabled(False);self.setMinimumHeight(42)
        self.setStyleSheet('QLineEdit{padding:10px 12px;background:#222c3b;border:1px solid #3b4b61;border-radius:7px;} QLineEdit:focus{border-color:#d9ad66;} QToolButton{background:#3a4b63;border:1px solid #6e809c;border-radius:5px;padding:0;} QToolButton:hover{background:#536b8c;border-color:#b6c9e4;} QToolButton:pressed{background:#657e9f;}')
        self.clear_button=QToolButton(self);self.clear_button.setIcon(QIcon(str(Path(__file__).parent/'resources/search-clear.svg')))
        self.clear_button.setAccessibleName('Clear search');self.clear_button.setToolTip('Clear search')
        self.clear_button.setFixedSize(28,28);self.clear_button.setIconSize(QSize(20,20));self.clear_button.setCursor(Qt.CursorShape.ArrowCursor)
        self.clear_button.setFocusPolicy(Qt.FocusPolicy.NoFocus);self.clear_button.clicked.connect(self.clear)
        self.textChanged.connect(self.update_clear);self.update_clear()

    def update_clear(self,*_):
        visible=bool(self.text());self.clear_button.setVisible(visible)
        self.setTextMargins(0,0,34 if visible else 0,0)

    def setText(self,text):
        super().setText(text)
        if hasattr(self,'clear_button'):self.update_clear()

    def clear(self):
        super().clear();self.update_clear()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.clear_button.move(self.width()-self.clear_button.width()-7,(self.height()-self.clear_button.height())//2)
