"""Manage watched items without issuing price or thumbnail requests."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout


class WatchlistDialog(QDialog):
    def __init__(self, watches, parent=None):
        super().__init__(parent)
        self.watches = watches
        self.setWindowTitle("Watched items")
        self.resize(400, 340)
        layout = QVBoxLayout(self)
        help_text = QLabel("Select an item in Prices and choose Watch item. Its on-screen price label will pulse twice, then keep a star.")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.empty = QLabel("No watched items yet.")
        layout.addWidget(self.empty)
        self.items = QListWidget()
        layout.addWidget(self.items, 1)
        self.remove_button = QPushButton("Remove selected item")
        self.remove_button.clicked.connect(self.remove_selected)
        self.items.currentItemChanged.connect(lambda *_: self.remove_button.setEnabled(self.items.currentItem() is not None))
        layout.addWidget(self.remove_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        watches.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        selected = self.items.currentItem()
        identity = selected.data(Qt.ItemDataRole.UserRole) if selected else None
        self.items.clear()
        for item_id, name in sorted(self.watches.entries.items(), key=lambda pair: (pair[1].casefold(), pair[0])):
            row = QListWidgetItem(name)
            row.setData(Qt.ItemDataRole.UserRole, item_id)
            row.setToolTip(f"Item ID: {item_id}")
            self.items.addItem(row)
            if item_id == identity:self.items.setCurrentItem(row)
        self.empty.setVisible(not self.watches.ids)
        self.items.setVisible(bool(self.watches.ids))
        self.remove_button.setEnabled(self.items.currentItem() is not None)

    def remove_selected(self):
        item = self.items.currentItem()
        if item:self.watches.remove(item.data(Qt.ItemDataRole.UserRole))
