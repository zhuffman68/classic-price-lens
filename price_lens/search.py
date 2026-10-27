"""Local item search with one explicit cached price lookup at a time."""
import time

from PySide6.QtCore import Qt, QTimer, Signal,QSize
from PySide6.QtGui import QIcon,QPixmap,QPainter
from PySide6.QtWidgets import (QFrame,QHBoxLayout,QLabel,QLineEdit,QListWidget,
    QListWidgetItem,QPushButton,QScrollArea,QVBoxLayout,QWidget)

from .domain import key, item_words, unclipped_name
from .ui_components import price_card, text_label
from .motion import reveal, visibility, fade_away


class PriceSearch(QWidget):
    active_changed=Signal()
    item_selected = Signal(object)
    identity_selected = Signal(object, object)
    source_requested = Signal(str)
    catalog_retry = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.catalog = None
        self.thumbnails=None
        self.thumbnail_timer=QTimer(self);self.thumbnail_timer.setSingleShot(True);self.thumbnail_timer.setInterval(0)
        self.thumbnail_timer.timeout.connect(self.request_thumbnails)
        self.catalog_error = ""
        self.selected = None
        self.pending_identity = None
        self.pending_candidates = ()
        self.identity_errors = {}
        self.quote = None
        self.error = ""
        self.lookup_state = ""
        self.ttl = 900
        self.expanded = False
        self.card_key = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,12,0,0)
        layout.setSpacing(12)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search an item or scroll…")
        self.query.setAccessibleName("Search Classic World items")
        self.query.setClearButtonEnabled(True)
        self.query.setStyleSheet("QLineEdit { padding: 11px 12px; background: #222c3b; border: 1px solid #3b4b61; border-radius: 7px; } QLineEdit:focus { border-color: #d9ad66; }")
        layout.addWidget(self.query)
        self.hint = text_label("Item names are loading…", "color: #9eacbf; font-size: 11px", True)
        hint_row = QHBoxLayout()
        hint_row.addWidget(self.hint,1)
        self.matches_button = QPushButton("Other matches")
        self.matches_button.setObjectName("quiet")
        self.matches_button.hide()
        self.matches_button.clicked.connect(lambda:visibility(self.results,self.results.isHidden()))
        hint_row.addWidget(self.matches_button)
        layout.addLayout(hint_row)
        self.retry_button = QPushButton("Retry item list")
        self.retry_button.clicked.connect(self.catalog_retry.emit)
        self.retry_button.hide()
        layout.addWidget(self.retry_button,0,Qt.AlignmentFlag.AlignLeft)
        self.results = QListWidget()
        self.results.setIconSize(QSize(32,32))
        blank=QPixmap(32,32);blank.fill(Qt.GlobalColor.transparent);self.placeholder_icon=QIcon(blank)
        self.results.verticalScrollBar().valueChanged.connect(self.request_thumbnails)
        self.results.setMaximumHeight(210)
        self.results.setStyleSheet("QListWidget { background: #1e2734; border: 1px solid #354255; border-radius: 7px; } QListWidget::item { padding: 9px 10px; border-bottom: 1px solid #2a3647; } QListWidget::item:selected { background: #35455c; color: #f4e7d1; }")
        self.results.currentItemChanged.connect(self.select_result)
        self.results.itemClicked.connect(lambda *_:visibility(self.results,False))
        self.results.hide()
        layout.addWidget(self.results)
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.detail = QWidget()
        self.detail_layout = QVBoxLayout(self.detail)
        self.detail_layout.setContentsMargins(0,0,0,0)
        self.detail_scroll.setWidget(self.detail)
        layout.addWidget(self.detail_scroll,1)
        self.bottom_spacer=layout.count();layout.addStretch(1)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(180)
        self.timer.timeout.connect(self.find_items)
        self.query.textChanged.connect(self.schedule_search)
        self.query.returnPressed.connect(self.choose_first)
        self.render()

    def set_thumbnails(self,store):
        self.thumbnails=store;store.ready.connect(self.on_thumbnail)

    def request_thumbnails(self,*_):
        if not self.thumbnails:return
        items=[self.selected] if self.selected else []
        if not self.results.isHidden():
            region=self.results.viewport().rect().adjusted(0,-50,0,50)
            for index in range(self.results.count()):
                row=self.results.item(index);item=row.data(Qt.ItemDataRole.UserRole)
                if hasattr(item,'game_id') and self.results.visualItemRect(row).intersects(region):items.append(item)
        self.thumbnails.observe(items)

    def on_thumbnail(self,item_id):
        if not self.thumbnails:return
        image=self.thumbnails.image(item_id)
        if not image.isNull():
            tile=QPixmap(32,32);tile.fill(Qt.GlobalColor.transparent)
            if image.width()>32 or image.height()>32:image=image.scaled(QSize(32,32),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
            painter=QPainter(tile);painter.drawImage((32-image.width())//2,(32-image.height())//2,image);painter.end()
            icon=QIcon(tile)
        for index in range(self.results.count()):
            row=self.results.item(index);item=row.data(Qt.ItemDataRole.UserRole)
            if getattr(item,'game_id',None)==item_id and not image.isNull():row.setIcon(icon)
        card=getattr(self,'price_view',None)
        if self.selected and self.selected.game_id==item_id and card:card.thumbnail.set_image(image)

    def set_catalog(self, catalog):
        self.clear_selection()
        self.catalog = catalog
        self.catalog_error = ""
        self.retry_button.hide()
        self.find_items()

    def show_catalog_error(self, message):
        self.catalog_error = message
        self.hint.setText("Item names are unavailable. Check your connection and retry.")
        self.retry_button.show()

    def schedule_search(self):
        # Stop demand for the previous result immediately. Typing searches the
        # local catalog only; no suggestions trigger remote price requests.
        if not self.query.text().strip():
            fade_away(self.results)
            if getattr(self,"price_view",None):fade_away(self.price_view)
        self.clear_selection()
        self.results.setEnabled(False)
        self.matches_button.hide()
        self.timer.start()
        self.active_changed.emit()

    def clear_selection(self):
        if self.selected is not None or self.pending_identity is not None:
            self.selected = self.quote = None
            self.pending_identity = None
            self.pending_candidates = ()
            self.error = self.lookup_state = ""
            self.item_selected.emit(None)
            self.render()

    def find_items(self):
        query = item_words(unclipped_name(self.query.text()))
        if not query:fade_away(self.results)
        self.results.blockSignals(True)
        self.results.clear()
        found = []
        if self.catalog and len(query) >= 2:
            terms = query.split()
            found = [item for item in self.catalog.items if all(term in item_words(item.name) for term in terms) or str(item.game_id)==query]
            found.sort(key=lambda item:(item_words(item.name)!=query,not item_words(item.name).startswith(query),item.name.casefold(),item.game_id))
            groups = {}
            for item in found:groups.setdefault(key(item.name),[]).append(item)
            found = list(groups.values())
            for candidates in found[:40]:
                item = candidates[0]
                suffix = " · NX item" if item.cash else " · Equipment" if item.equipment else ""
                row = QListWidgetItem(item.name+suffix)
                row.setIcon(self.placeholder_icon);row.setSizeHint(QSize(0,50))
                resolved = self.catalog.resolve(item.name)
                row.setData(Qt.ItemDataRole.UserRole,resolved or (item.name,tuple(candidates)))
                self.results.addItem(row)
                if self.thumbnails and resolved:self.on_thumbnail(resolved.game_id)
        self.results.blockSignals(False)
        self.results.setEnabled(True)
        visibility(self.results,bool(found))
        if found:reveal(self.results)
        self.thumbnail_timer.start()
        self.hint.setText("Item names are unavailable. Check your connection and retry." if self.catalog_error else
                          "Item names are loading…" if not self.catalog else
                          "Type at least two characters. Select a result to check its price." if len(query)<2 else
                          "No matching Classic World items." if not found else
                          f"{len(found):,} matches"+(" · showing the first 40" if len(found)>40 else "")+" · select an item for its price")

    def choose_first(self):
        self.timer.stop()
        self.find_items()
        if self.results.count():self.results.setCurrentRow(0)

    def select_result(self, current, previous=None):
        item = current.data(Qt.ItemDataRole.UserRole) if current else None
        if isinstance(item,tuple):
            name,candidates = item
            self.pending_identity = (name,None)
            self.pending_candidates = candidates
            self.selected = self.quote = None
            self.error = self.identity_errors.get(self.pending_identity, "")
            visibility(self.results,False)
            self.matches_button.show()
            self.identity_selected.emit(self.pending_identity,candidates)
            self.render()
            return
        if item == self.selected:
            return
        self.selected, self.quote = item, None
        self.pending_identity = None
        self.pending_candidates = ()
        self.error = self.lookup_state = ""
        self.expanded = False
        if item:
            visibility(self.results,False)
            self.matches_button.show()
            self.hint.setText("Selected item · market prices in mesos")
        self.item_selected.emit(item)
        self.render()

    def accept_identity(self, identity, item):
        if self.pending_identity != identity:return
        self.pending_identity = None
        self.pending_candidates = ()
        self.identity_errors.pop(identity,None)
        self.selected = item
        self.error = self.lookup_state = ""
        self.item_selected.emit(item)
        self.render()

    def identity_error(self, identity, message):
        if len(self.identity_errors)>=256:self.identity_errors.clear()
        self.identity_errors[identity] = message
        if self.pending_identity == identity:
            self.error = message
            self.render()

    def accept_quote(self, item_id, quote):
        if self.selected and self.selected.game_id == item_id:
            self.quote = quote
            self.error = ""
            self.render()

    def accept_error(self, item_id, message):
        if self.selected and self.selected.game_id == item_id:
            self.error = message
            self.render()

    def set_state(self, state):
        self.lookup_state = state
        self.render()

    def show_details(self, expanded):
        self.expanded = expanded
        self.render()

    def render(self):
        self.detail_scroll.setVisible(bool(self.selected or self.pending_identity))
        self.layout().setStretch(self.bottom_spacer,0 if self.selected or self.pending_identity else 1)
        state = (self.selected,self.pending_identity,self.quote,self.error,self.lookup_state,self.expanded,self.ttl,int(time.time()//5))
        if state == self.card_key:return
        self.card_key = state
        card = getattr(self,"price_view",None)
        if self.selected:
            while self.detail_layout.count():
                widget = self.detail_layout.takeAt(0).widget()
                if widget and widget is not card:widget.hide();widget.deleteLater()
            data = dict(item=self.selected,row={"name":self.selected.name},quote=self.quote,
                        now=time.time(),ttl=self.ttl,hovered=True,lookup_error=bool(self.error),
                        lookup_state=self.lookup_state,expanded=self.expanded,details_changed=self.show_details,
                        open_source=self.source_requested.emit,context_name="Classic World · market price")
            changed = getattr(self,"card_item",None) != self.selected.game_id
            if card:card.update_data(**data)
            else:card = self.price_view = price_card(**data)
            self.card_item = self.selected.game_id
            self.detail_layout.addWidget(card)
            card.show()
            if self.thumbnails:
                card.thumbnail.show();card.thumbnail.set_image(self.thumbnails.image(self.selected.game_id))
            if changed:reveal(card)
            self.request_thumbnails()
        else:
            while self.detail_layout.count():
                widget = self.detail_layout.takeAt(0).widget()
                if widget:
                    widget.hide()
                    if widget is not card:widget.deleteLater()
            self.card_item = None
            if self.pending_identity:
                self.detail_layout.addWidget(text_label(self.pending_identity[0],"font-size: 17px; font-weight: 600"))
                self.detail_layout.addWidget(text_label("The price source couldn't identify this item. Try again later." if self.error else "Checking market price…","color: #9eacbf; font-size: 12px",True))
            else:
                self.detail_layout.addWidget(text_label("Search the Classic World item catalog, then select an item to check its price. Screen sharing is optional.","color: #8f9db1; font-size: 11px",True))
        self.detail_layout.addStretch()
