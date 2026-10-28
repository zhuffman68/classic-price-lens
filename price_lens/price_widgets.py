"""Persistent price cards: update fields in place instead of rebuilding on every quote."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame,QHBoxLayout,QPushButton,QVBoxLayout,QWidget

from .domain import WORLD,age_text,compare
from .motion import RollingLabel,visibility
from .ui_components import COLORS,mesos,text_label
from .thumbnails import ItemImage
from .watchlist_ui import WatchButton


class PriceCard(QFrame):
    def __init__(self,watchlist=None,watch_button=None,**data):
        super().__init__()
        self.setObjectName("card")
        layout=QVBoxLayout(self)
        layout.setContentsMargins(14,12,14,12)
        layout.setSpacing(7)
        self.fields={}
        def field(name,parent,style="font-size: 11px; color: #98a3b1",wrap=True):
            numeric = name in ('store','market')
            widget=RollingLabel() if numeric else text_label('',style,wrap)
            widget.setStyleSheet(style)
            self.fields[name]=widget
            parent.addWidget(widget)
            return widget
        header=self.header=QHBoxLayout();self.thumbnail=ItemImage();self.thumbnail.hide();header.addWidget(self.thumbnail)
        names=QVBoxLayout();names.setContentsMargins(0,0,0,0);names.setSpacing(4)
        field("name",names,"font-size: 14px; font-weight: 650")
        field("context",names,"font-size: 10px; color: #98a3b1")
        header.addLayout(names,1)
        self.watch_button=watch_button if watch_button is not None else WatchButton(self)
        if watchlist is not None:self.watch_button.bind(watchlist)
        header.addWidget(self.watch_button,0,Qt.AlignmentFlag.AlignTop);layout.addLayout(header)
        field("status",layout)
        numbers=QHBoxLayout()
        self.store=QWidget()
        self.store.setStyleSheet("background: transparent")
        store=QVBoxLayout(self.store);store.setContentsMargins(0,0,0,0)
        store.addWidget(text_label("Store price","font-size: 10px; color: #98a3b1"))
        field("store",store,"font-size: 17px; font-weight: 650")
        numbers.addWidget(self.store)
        market=QVBoxLayout()
        market.addWidget(text_label("Market reference","font-size: 10px; color: #98a3b1"))
        field("market",market,"font-size: 17px; font-weight: 650")
        numbers.addLayout(market)
        layout.addLayout(numbers)
        for name in ("units","age","progress","explanation"):field(name,layout,"font-size: 10px; color: #98a3b1")
        field('recent',layout,'font-size:11px;color:#b3c0d2')
        self.link=QPushButton('View price source ↗');self.link.setObjectName('quiet')
        self.link.clicked.connect(self.visit_source);layout.addWidget(self.link,0,Qt.AlignmentFlag.AlignLeft)
        self.update_data(**data)

    def put(self,name,text,style=None):
        label=self.fields[name]
        label.setText(text)
        visibility(label,bool(text))
        if style and label.styleSheet()!=style:label.setStyleSheet(style)

    def visit_source(self):
        callback=self.data.get("open_source")
        quote=self.data.get("quote")
        if callback and quote:callback(quote.url)

    def update_data(self,*,item,row,quote,now,ttl,paused=False,old_capture=False,lookup_error=False,
                    lookup_state="",open_source=None,
                    hovered=False,example=False,context_name=None):
        self.data={"open_source":open_source,"quote":quote}
        self.watch_button.set_item(item)
        price=row.get("price") or {}
        verdict=compare(item,price.get("quantity"),price.get("mesos"),quote,now,ttl)
        compatible=bool(item and quote and quote.game_id==item.game_id and quote.world==WORLD
                        and quote.condition=="clean" and quote.per_set==item.per_set)
        fresh=bool(compatible and quote.fresh(now,ttl))
        stale=paused or old_capture
        if not item:message,tone="Item name needs checking","muted"
        elif stale:message,tone=("Paused · last read item" if paused else "Waiting for a fresh screen"),"muted"
        elif not compatible or quote.price is None:
            message=('Updating market prices…' if lookup_state=='refreshing' else
                     'Market update unavailable' if lookup_error else 'No price in the market snapshot' if quote else 'Waiting for market prices…')
            tone="muted"
        elif not fresh:
            message={"refreshing":"Refreshing market reference…","queued":"Market refresh queued…",
                     "retry":"Refresh unavailable · retry later"}.get(lookup_state,
                     ("Market report age unknown · reference only" if quote.observed_at is None else "Older market reports · reference only")
                     if quote.cache_valid(now,ttl) else "Older reference · refresh needed")
            tone="muted"
        elif quote.sample_count<5 or quote.uncertain:message,tone="Few price reports · reference only","muted"
        elif hovered:message,tone=(f"{quote.period} · {quote.sample_count:,} reports" if context_name else "Market reference"),"blue"
        elif verdict.delta is not None:
            direction="below" if verdict.delta<0 else "above"
            message=f"{abs(verdict.delta):.0f}% {direction} reference" if verdict.delta else "Near reference"
            if verdict.tone=="blue" and verdict.delta:message="Near reference · "+message
            tone=verdict.tone
        else:message,tone="Store price unclear","muted"
        self.put("name",item.name if item else row.get("name") or "Item name unclear")
        self.put("context","EXAMPLE PRICES" if example else (context_name or "Inventory / equipment item") if hovered else "")
        self.put("status",message,f"color: {COLORS[tone]}; font-size: 11px")
        self.store.setVisible(not hovered)
        self.put("store",mesos(verdict.unit_price)+(" mesos" if verdict.unit_price is not None else ""))
        value=quote.price if compatible else None
        self.put("market",mesos(value)+(" mesos" if value is not None else ""),
                 f"font-size: 17px; font-weight: 650; color: {'#e8d2ac' if fresh and not stale else '#98a3b1'}")
        self.put("units",(("Prices are per set" if item.per_set else "Prices are per item")+
                          (" · resale value in mesos" if item.cash else "")) if item else "")
        age=f'Price checked {age_text(max(0,now-quote.fetched_at))} ago' if compatible else ''
        if compatible and quote.source!='MesoWatch':
            age+=' · latest market report '+(age_text(max(0,now-quote.observed_at))+' ago' if quote.observed_at else 'unknown')
        if compatible and quote.published_at is not None:age+=f' · snapshot {age_text(now-quote.published_at)} old'
        self.put('age',age if not example else '')
        self.put("progress",{"queued":"Background refresh queued","refreshing":"Refreshing in the background…",
                             "retry":"Last refresh unavailable · retry later"}.get(lookup_state,"") if fresh and not example else "")
        self.put("explanation","Item name recognised. The price source has no market reference for this item." if compatible and value is None else
                 "Item name recognised. Saved prices remain available; the full market will be checked again later." if lookup_error and not compatible else
                 "Keep the full item name visible. A shared name or unclear text can prevent a match." if not item else "")
        if compatible and quote.source=='MesoWatch' and quote.observed_at is not None:
            from datetime import datetime,timezone
            stamp=datetime.fromtimestamp(quote.observed_at,timezone.utc).strftime('%b %d, %H:%M UTC')
            self.put('recent',f'Most recent observed sale · {age_text(max(0,now-quote.observed_at))} ago · {stamp}')
        else:self.put('recent','')
        self.link.setVisible(bool(hovered and compatible and quote.url and open_source))
