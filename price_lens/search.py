"""Local item search with one explicit cached price lookup at a time."""
import time

from PySide6.QtCore import Qt, QTimer, Signal,QSize
from PySide6.QtGui import QIcon,QPixmap,QPainter
from PySide6.QtWidgets import (QFrame,QHBoxLayout,QLabel,QListWidget,
    QListWidgetItem,QPushButton,QScrollArea,QVBoxLayout,QWidget)

from .domain import key, item_words, unclipped_name
from .ui_components import price_card, text_label
from .motion import CardArea, reveal, fade_away
from .tls import catalog_error_text
from .watchlist_ui import WatchedItems,WatchButton
from .search_field import SearchField
from .reference_details import EntryDetails


class PriceSearch(QWidget):
    active_changed=Signal()
    detail_changing=Signal()
    item_selected = Signal(object)
    identity_selected = Signal(object, object)
    source_requested = Signal(str)
    catalog_retry = Signal()
    reference_requested=Signal(object)
    reference_changed=Signal()

    def __init__(self, parent=None, *, inline_detail=True):
        super().__init__(parent)
        self.inline_detail=inline_detail
        self.detail_identity=(None,None)
        self.catalog = None
        self.reference=None;self.store=None;self.media=None;self.market=None
        self.watchlist = None
        self.thumbnails=None
        self.screen_items=()
        self.thumbnail_timer=QTimer(self);self.thumbnail_timer.setSingleShot(True);self.thumbnail_timer.setInterval(0)
        self.thumbnail_timer.timeout.connect(self.request_thumbnails)
        self.catalog_error = ""
        self.selected = None
        self.selection_source = None
        self.watch_focus = False
        self.pending_identity = None
        self.pending_candidates = ()
        self.identity_errors = {}
        self.quote = None
        self.error = ""
        self.lookup_state = ""
        self.ttl = 900
        self.card_key = None
        self.results_current = False
        self.result_rows={}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,12,0,0)
        layout.setSpacing(0)
        self.query = SearchField("Search an item or scroll…")
        self.query.setAccessibleName("Search Classic World items")
        layout.addWidget(self.query)
        self.market_status=text_label('', 'color:#9eacbf;font-size:11px',True)
        self.market_status.setContentsMargins(0,12,0,0)
        self.market_status.hide();layout.addWidget(self.market_status)
        # Count, matches and their spacing leave together. The fixed child
        # canvas prevents a final layout-gap jump when the section reaches zero.
        self.results_area=CardArea(self)
        self.results_area.animation.setDuration(130)
        result_layout=QVBoxLayout(self.results_area.content)
        result_layout.setContentsMargins(0,12,0,0);result_layout.setSpacing(12)
        layout.addWidget(self.results_area)
        self.hint = text_label("Item names are loading…", "color: #9eacbf; font-size: 11px", True)
        self.hint_row=QWidget()
        hint_row = QHBoxLayout(self.hint_row);hint_row.setContentsMargins(0,0,0,0)
        hint_row.addWidget(self.hint,1)
        self.matches_button = QPushButton("Other matches")
        self.matches_button.setObjectName("quiet")
        self.matches_button.hide()
        self.matches_button.clicked.connect(lambda:self.set_results_state(self.results.isHidden()))
        hint_row.addWidget(self.matches_button)
        result_layout.addWidget(self.hint_row)
        self.retry_button = QPushButton("Retry item list")
        self.retry_button.clicked.connect(self.catalog_retry.emit)
        self.retry_button.hide()
        result_layout.addWidget(self.retry_button,0,Qt.AlignmentFlag.AlignLeft)
        self.results = QListWidget()
        self.results.setIconSize(QSize(32,32))
        blank=QPixmap(32,32);blank.fill(Qt.GlobalColor.transparent);self.placeholder_icon=QIcon(blank)
        self.results.verticalScrollBar().valueChanged.connect(self.request_thumbnails)
        self.results.setMaximumHeight(210)
        self.results.setStyleSheet("QListWidget { background: #1e2734; border: 1px solid #354255; border-radius: 7px; } QListWidget::item { padding: 9px 10px; border-bottom: 1px solid #2a3647; } QListWidget::item:selected { background: #35455c; color: #f4e7d1; }")
        self.results.currentItemChanged.connect(self.select_result)
        self.results.itemClicked.connect(lambda *_:self.set_results_state(False) if self.results_current else None)
        self.results.hide()
        result_layout.addWidget(self.results)
        self.watch_gap=QWidget();self.watch_gap.setFixedHeight(12);self.watch_gap.hide();layout.addWidget(self.watch_gap)
        self.watched_items=WatchedItems(self);self.watched_items.hide()
        self.watched_items.item_selected.connect(self.select_watched)
        self.watched_items.visible_changed.connect(self.thumbnail_timer.start)
        layout.addWidget(self.watched_items)
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.detail = QWidget()
        self.detail_layout = QVBoxLayout(self.detail)
        self.detail_layout.setContentsMargins(0,0,0,0)
        self.watch_button = WatchButton(self.detail)
        self.pending_view=QWidget(self.detail)
        pending=QVBoxLayout(self.pending_view);pending.setContentsMargins(0,0,0,0)
        self.pending_name=text_label('', 'font-size:17px;font-weight:600',True)
        self.pending_message=text_label('', 'color:#9eacbf;font-size:12px',True)
        pending.addWidget(self.pending_name);pending.addWidget(self.pending_message)
        self.pending_view.hide();self.detail_layout.addWidget(self.pending_view)
        self.detail_layout.addStretch()
        self.detail_scroll.setWidget(self.detail)
        self.bottom_spacer=None
        if inline_detail:
            layout.addWidget(self.detail_scroll,1)
            self.bottom_spacer=layout.count();layout.addStretch(1)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(180)
        self.timer.timeout.connect(self.find_items)
        self.query.textChanged.connect(self.schedule_search)
        self.query.returnPressed.connect(self.choose_first)
        self.watched_items.expanded_changed.connect(self.on_watch_expanded)
        self.set_results_state(False,hint=self.hint.text())
        self.render()

    def set_watchlist(self, watches):
        self.watchlist = watches
        self.watch_button.bind(watches)
        watches.changed.connect(self.update_watch_controls)
        self.watched_items.set_watchlist(watches);self.watched_items.show();self.watch_gap.show()
        self.update_watch_controls()

    def set_market_status(self,message,error=False):
        if self.market_status.text()==message:return
        if not message:fade_away(self.market_status)
        self.market_status.setText(message)
        self.market_status.setStyleSheet('color:'+('#e4bd7b' if error else '#9eacbf')+';font-size:11px')
        self.market_status.setVisible(bool(message))

    def update_watch_controls(self):
        self.watch_button.set_item(self.selected)

    def set_thumbnails(self,store):
        self.thumbnails=store;store.ready.connect(self.on_thumbnail)

    def set_screen_items(self,items):
        identities=tuple(item.game_id for item in items)
        if identities==tuple(item.game_id for item in self.screen_items):return
        self.screen_items=tuple(items);self.request_thumbnails()

    def request_thumbnails(self,*_):
        if not self.thumbnails:return
        items=[self.selected] if self.selected else []
        if self.catalog:
            watched=set(self.watched_items.visible_ids())
            items.extend(item for item in self.catalog.items if item.game_id in watched)
            for identity in watched:self.watched_items.set_image(identity,self.thumbnails.image(identity))
        if not self.results.isHidden():
            region=self.results.viewport().rect().adjusted(0,-50,0,50)
            for index in range(self.results.count()):
                row=self.results.item(index);item=row.data(Qt.ItemDataRole.UserRole)
                if hasattr(item,'game_id') and self.results.visualItemRect(row).intersects(region):items.append(item)
        self.thumbnails.observe(items+list(self.screen_items))

    def on_thumbnail(self,item_id):
        if not self.thumbnails:return
        image=self.thumbnails.image(item_id)
        self.watched_items.set_image(item_id,image)
        if not image.isNull():
            tile=QPixmap(32,32);tile.fill(Qt.GlobalColor.transparent)
            if image.width()>32 or image.height()>32:image=image.scaled(QSize(32,32),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
            painter=QPainter(tile);painter.drawImage((32-image.width())//2,(32-image.height())//2,image);painter.end()
            icon=QIcon(tile)
            icon.addPixmap(tile,QIcon.Mode.Disabled)
        for index in range(self.results.count()):
            row=self.results.item(index);item=row.data(Qt.ItemDataRole.UserRole)
            if getattr(item,'game_id',None)==item_id and not image.isNull():row.setIcon(icon)
        card=getattr(self,'price_view',None)
        if self.selected and self.selected.game_id==item_id and card:card.thumbnail.set_image(image)

    def set_catalog(self, catalog,*,preserve=False):
        selected=self.selected if preserve else None;quote=self.quote
        if not preserve:self.clear_selection()
        self.catalog = catalog
        self.catalog_error = ""
        self.retry_button.hide()
        self.find_items()
        if selected:
            current=next((item for item in catalog.items if item.game_id==selected.game_id and key(item.name)==key(selected.name)),None)
            if current:
                self.selected=current;self.quote=quote;self.set_results_state(False);self.card_key=None;self.render()
            else:self.clear_selection()

    def set_reference(self,service,media,market):
        self.reference=service;self.store=service.store;self.media=media;self.market=market
        media.ready.connect(self.on_reference_image);service.extra.updated.connect(self.on_reference_reports)
        service.sources.updated.connect(self.on_reference_reports)

    def catalog_item(self,entry):
        return next((item for item in self.catalog.items if item.game_id==entry.id and key(item.name)==key(entry.name)),None) if self.catalog else None

    def open(self,key):self.reference_requested.emit(tuple(key))

    def reference_demand(self):
        card=getattr(self,'price_view',None)
        return card.visible_urls() if isinstance(card,EntryDetails) and self.selected and self.isVisible() and not self.window().isMinimized() else []

    def reference_entry(self):
        card=getattr(self,'price_view',None)
        return card.entry if isinstance(card,EntryDetails) and self.selected and self.isVisible() else None

    def on_reference_image(self,url):
        card=getattr(self,'price_view',None)
        if isinstance(card,EntryDetails):card.image_ready(url)

    def on_reference_reports(self,key):
        card=getattr(self,'price_view',None)
        if isinstance(card,EntryDetails) and self.selected and card.entry.key==tuple(key):card.refresh_drops();self.reference_changed.emit()

    def refresh_reference(self):
        if self.selected:
            self.card_key=None;self.render()
            if isinstance(self.price_view,EntryDetails):self.price_view.refresh_drops()

    def select_watched(self,identity):
        if identity is None:
            if self.selection_source=='watch':
                self.clear_selection();self.set_results_state(False,hint='',matches=False);self.active_changed.emit()
            return
        if not self.watched_items.expanded:return
        item=next((item for item in self.catalog.items if item.game_id==identity),None) if self.catalog else None
        if item is None:return
        self.query.blockSignals(True);self.query.clear();self.query.blockSignals(False);self.timer.stop()
        self.selection_source='watch'
        self.watch_focus=True
        self.selected,self.quote=item,None;self.pending_identity=None;self.pending_candidates=()
        self.error=self.lookup_state=''
        self.set_results_state(False,hint='',matches=False)
        self.item_selected.emit(item);self.render();self.active_changed.emit()

    def select_recent(self,item):
        self.watched_items.set_expanded(False);self.watch_focus=False
        self.query.blockSignals(True);self.query.setText(item.name);self.query.blockSignals(False);self.timer.stop()
        self.selected,self.quote=item,None;self.pending_identity=None;self.pending_candidates=();self.selection_source='recent'
        self.error=self.lookup_state='';self.set_results_state(False,hint='',matches=False)
        self.item_selected.emit(item);self.render();self.active_changed.emit()

    def on_watch_expanded(self,shown):
        if not shown:self.watch_focus=False
        if shown:
            self.timer.stop();self.query.blockSignals(True);self.query.clear();self.query.blockSignals(False)
            self.clear_selection();self.set_results_state(False,hint='',matches=False)
        self.active_changed.emit()

    def show_catalog_error(self, message, retrying=False):
        self.catalog_error = message
        self.retry_button.setVisible(not retrying)
        self.set_results_state(False,hint="Retrying the item connection once…" if retrying else catalog_error_text(message))

    def set_results_state(self,shown,*,hint=None,matches=None):
        """Retarget one clipped section, including its count and layout gaps."""
        text=self.hint.text() if hint is None else hint
        other=not self.matches_button.isHidden() if matches is None else matches
        target=(bool(shown),bool(text),bool(other),not self.retry_button.isHidden())
        if target!=getattr(self,'results_target',None) and self.results_area.before is None:self.results_area.begin()
        self.results_target=target
        self.results.setVisible(shown)
        self.hint.setText(text);self.hint.setVisible(bool(text))
        self.matches_button.setVisible(other)
        self.hint_row.setVisible(bool(text or other))
        self.results_area.complete()

    def schedule_search(self):
        if self.query.text().strip():self.watched_items.set_expanded(False)
        # Stop demand for the previous result immediately. Typing searches the
        # local catalog only; no suggestions trigger remote price requests.
        self.clear_selection()
        # Keep the normal icon palette during debounce. The selection handler
        # gates demand so stale rows cannot start a price request.
        self.results_current = False
        if not self.query.text().strip():
            # Empty text needs no catalog debounce. A delayed count removal
            # used to move the returned shop/card a second time at 180 ms.
            self.timer.stop();self.find_items()
        else:
            self.set_results_state(not self.results.isHidden(),matches=False)
            self.timer.start()
        self.active_changed.emit()

    def clear_selection(self):
        self.selection_source=None
        if self.selected is not None or self.pending_identity is not None:
            self.selected = self.quote = None
            self.pending_identity = None
            self.pending_candidates = ()
            self.error = self.lookup_state = ""
            self.item_selected.emit(None)
            self.render()

    def find_items(self):
        query = item_words(unclipped_name(self.query.text()))
        found = []
        if self.catalog and len(query) >= 2:
            terms = query.split()
            found = [item for item in self.catalog.items if all(term in item_words(item.name) for term in terms) or str(item.game_id)==query]
            found.sort(key=lambda item:(item_words(item.name)!=query,not item_words(item.name).startswith(query),item.name.casefold(),item.game_id))
            groups = {}
            for item in found:groups.setdefault(key(item.name),[]).append(item)
            found = list(groups.values())
        was_hidden=self.results.isHidden()
        tokens=tuple(tuple(item.game_id for item in candidates) for candidates in found[:40])
        if tokens!=tuple(self.result_rows) or bool(found)!=(not was_hidden):
            # Snapshot before removing any rows, so clearing/replacing keeps
            # the outgoing names and thumbnails through the clipped motion.
            self.results_area.begin()
        previous=self.result_rows;current={}
        self.results.blockSignals(True);self.results.setUpdatesEnabled(False)
        try:
            self.results.setCurrentItem(None)
            tokens=set(tokens)
            for token,row in previous.items():
                if token not in tokens:self.results.takeItem(self.results.row(row))
            for index,candidates in enumerate(found[:40]):
                item = candidates[0]
                token=tuple(item.game_id for item in candidates)
                suffix = " · NX item" if item.cash else " · Equipment" if item.equipment else ""
                row=previous.get(token)
                if row is None:
                    row=QListWidgetItem(item.name+suffix)
                    row.setIcon(self.placeholder_icon);row.setSizeHint(QSize(0,50))
                elif row.text()!=item.name+suffix:row.setText(item.name+suffix)
                current[token]=row
                resolved = self.catalog.resolve(item.name)
                row.setData(Qt.ItemDataRole.UserRole,resolved or (item.name,tuple(candidates)))
                if self.results.row(row)!=index:
                    if self.results.row(row)>=0:self.results.takeItem(self.results.row(row))
                    self.results.insertItem(index,row)
                if self.thumbnails and resolved:self.on_thumbnail(resolved.game_id)
            self.result_rows=current
        finally:
            self.results.setUpdatesEnabled(True);self.results.blockSignals(False)
        self.results_current = True
        message=("Item names are unavailable. Check your connection and retry." if self.catalog_error else
                          "Item names are loading…" if not self.catalog else
                          "" if len(query)<2 else
                          "No matching Classic World items." if not found else
                          f"{len(found):,} matches"+(" · showing the first 40" if len(found)>40 else "")+" · select an item for its price")
        self.set_results_state(bool(found),hint=message,matches=False)
        if found and was_hidden:reveal(self.results)
        self.thumbnail_timer.start()

    def choose_first(self):
        self.timer.stop()
        self.find_items()
        if self.results.count():self.results.setCurrentRow(0)

    def select_result(self, current, previous=None):
        if not self.results_current:return
        item = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.selection_source="search" if item is not None else None
        if isinstance(item,tuple):
            name,candidates = item
            self.pending_identity = (name,None)
            self.pending_candidates = candidates
            self.selected = self.quote = None
            self.error = self.identity_errors.get(self.pending_identity, "")
            self.set_results_state(False,matches=True)
            self.identity_selected.emit(self.pending_identity,candidates)
            self.render()
            return
        if item == self.selected:
            return
        self.selected, self.quote = item, None
        self.pending_identity = None
        self.pending_candidates = ()
        self.error = self.lookup_state = ""
        if item:
            self.set_results_state(False,matches=True)
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

    def render(self):
        identity=(self.selected.game_id if self.selected else None,self.pending_identity)
        changed_identity=identity!=self.detail_identity
        if changed_identity:self.detail_changing.emit();self.detail_identity=identity
        self.update_watch_controls()
        if self.inline_detail:
            self.detail_scroll.setVisible(bool(self.selected or self.pending_identity))
            self.layout().setStretch(self.bottom_spacer,0 if self.selected or self.pending_identity else 1)
        from .price_widgets import display_age
        state = (self.selected,self.pending_identity,self.quote,self.error,self.lookup_state,self.ttl,display_age(self.quote,time.time(),self.ttl))
        if state == self.card_key:return
        self.card_key = state
        card = getattr(self,"price_view",None)
        if self.selected:
            self.pending_view.hide()
            data = dict(item=self.selected,row={"name":self.selected.name},quote=self.quote,
                        now=time.time(),ttl=self.ttl,hovered=True,lookup_error=bool(self.error),
                        lookup_state=self.lookup_state,
                        open_source=self.source_requested.emit,context_name="Classic World · market price")
            changed = getattr(self,"card_item",None) != self.selected.game_id
            record=self.store.entry('items',self.selected.game_id) if self.store else None
            if record:
                if not isinstance(card,EntryDetails) or card.entry.id!=self.selected.game_id or card.row!=record[1]:
                    old=card;previous=old.state() if isinstance(old,EntryDetails) and old.entry.id==self.selected.game_id else None
                    if old:self.detail_layout.removeWidget(old);old.hide();old.deleteLater()
                    else:self.watch_button.hide();self.watch_button.deleteLater()
                    card=self.price_view=EntryDetails(self,*record);self.watch_button=card.watch_button
                    card.media_changed.connect(self.reference_changed.emit);self.detail_layout.insertWidget(0,card)
                    if previous:card.restore(previous)
                card.update_data(**data)
            elif card:card.update_data(**data)
            else:
                card = self.price_view = price_card(watch_button=self.watch_button,**data)
                self.detail_layout.insertWidget(0,card)
            self.card_item = self.selected.game_id
            card.show()
            if self.thumbnails:
                image=self.thumbnails.image(self.selected.game_id)
                card.thumbnail.show()
                if not image.isNull() or not record:card.thumbnail.set_image(image)
            if changed and self.inline_detail:reveal(card)
            self.request_thumbnails()
            self.reference_changed.emit()
        else:
            if card:card.hide()
            self.card_item = None
            self.pending_view.setVisible(bool(self.pending_identity))
            if self.pending_identity:
                self.pending_name.setText(self.pending_identity[0])
                self.pending_message.setText("The price source couldn't identify this item. Try again later." if self.error else "Checking market price…")
            self.reference_changed.emit()
        if changed_identity:self.active_changed.emit()
