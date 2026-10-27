"""Persistent price cards: update fields in place instead of rebuilding on every quote."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame,QHBoxLayout,QPushButton,QVBoxLayout,QWidget

from .domain import WORLD,age_text,compare
from .motion import visibility
from .ui_components import COLORS,mesos,text_label


class PriceCard(QFrame):
    def __init__(self,**data):
        super().__init__()
        self.setObjectName("card")
        layout=QVBoxLayout(self)
        layout.setContentsMargins(14,12,14,12)
        layout.setSpacing(7)
        self.fields={}
        def field(name,parent,style="font-size: 11px; color: #98a3b1",wrap=True):
            widget=text_label("",style,wrap)
            self.fields[name]=widget
            parent.addWidget(widget)
            return widget
        field("name",layout,"font-size: 14px; font-weight: 650")
        field("context",layout,"font-size: 10px; color: #98a3b1")
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
        self.toggle=QPushButton("Details")
        self.toggle.setObjectName("quiet");self.toggle.setCheckable(True)
        self.toggle.toggled.connect(self.change_details)
        layout.addWidget(self.toggle,0,Qt.AlignmentFlag.AlignLeft)
        self.details=QWidget();self.details.setObjectName("cardDetails")
        details=QVBoxLayout(self.details);details.setContentsMargins(0,2,0,0);details.setSpacing(6)
        for name in ("listing","equipment","cash","source","next","margin"):field(name,details,"font-size: 11px; color: #aab5c4")
        self.link=QPushButton("View price source ↗")
        self.link.clicked.connect(self.visit_source)
        details.addWidget(self.link)
        layout.addWidget(self.details)
        self.details.hide()
        self.update_data(**data)

    def put(self,name,text,style=None):
        label=self.fields[name]
        label.setText(text)
        label.setVisible(bool(text))
        if style and label.styleSheet()!=style:label.setStyleSheet(style)

    def change_details(self,checked):
        self.toggle.setText("Hide details" if checked else "Details")
        visibility(self.details,checked)
        callback=self.data.get("details_changed")
        if callback:callback(checked)

    def visit_source(self):
        callback=self.data.get("open_source")
        quote=self.data.get("quote")
        if callback and quote:callback(quote.url)

    def update_data(self,*,item,row,quote,now,ttl,paused=False,old_capture=False,lookup_error=False,
                    lookup_state="",expanded=False,details_changed=None,open_source=None,
                    hovered=False,example=False,context_name=None):
        self.data={"details_changed":details_changed,"open_source":open_source,"quote":quote}
        price=row.get("price") or {}
        verdict=compare(item,price.get("quantity"),price.get("mesos"),quote,now,ttl)
        compatible=bool(item and quote and quote.game_id==item.game_id and quote.world==WORLD
                        and quote.condition=="clean" and quote.per_set==item.per_set)
        fresh=bool(compatible and quote.fresh(now,ttl))
        stale=paused or old_capture
        if not item:message,tone="Item name needs checking","muted"
        elif stale:message,tone=("Paused · last read item" if paused else "Waiting for a fresh screen"),"muted"
        elif not compatible or quote.price is None:
            message=("Market price lookup queued…" if lookup_state=="queued" and not quote else
                     "Price lookup unavailable" if lookup_error else "No market reports" if quote else "Checking market price…")
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
        self.put("age",f"Price checked {age_text(max(0,now-quote.fetched_at))} ago · latest market report "+
                 (f"{age_text(max(0,now-quote.observed_at))} ago" if quote.observed_at else "unknown")+
                 (f" · snapshot {age_text(now-quote.published_at)} old" if quote.published_at is not None else "") if compatible and not example else "")
        self.put("progress",{"queued":"Background refresh queued","refreshing":"Refreshing in the background…",
                             "retry":"Last refresh unavailable · retry later"}.get(lookup_state,"") if fresh and not example else "")
        self.put("explanation","Item name recognised. The price source has no market reference for this item." if compatible and value is None else
                 "Item name recognised. Cached prices will be used when available; another lookup will be tried later." if lookup_error and not compatible else
                 "Keep the full item name visible. A shared name or unclear text can prevent a match." if not item else "")
        self.put("listing",f"Listing: {price.get('quantity') if price.get('quantity') is not None else '?'} for {mesos(price.get('mesos'))} mesos" if price else "")
        self.put("equipment","Equipment is compared as unscrolled. Individual stat rolls are not assessed." if item and item.equipment else "")
        self.put("cash",f"Cash Shop retail: {item.nx_price:,} NX"+(f" / pack of {item.nx_count}" if item.nx_count>1 else "")+". Market references above are in mesos."
                 if item and item.cash and item.nx_price else "")
        self.put("source",f"{quote.source} · {quote.period} median · {quote.sample_count:,} reports\n{quote.basis}" if compatible else "")
        self.put("next",(f"Reference valid for {age_text(quote.expires_at(ttl)-now)}" if quote.cache_valid(now,ttl)
                         else "Cached reference needs a refresh. Older reports cannot receive a comparison rating.") if compatible else "")
        self.put("margin",f"At reference resale: {mesos(verdict.net_margin)} mesos per {'set' if item.per_set else 'item'} after the 3% shop fee."
                 if verdict.net_margin is not None and fresh and not stale else "")
        self.link.setVisible(bool(compatible and quote.url and open_source))
        self.toggle.setVisible(not example)
        self.toggle.blockSignals(True);self.toggle.setChecked(expanded);self.toggle.blockSignals(False)
        self.toggle.setText("Hide details" if expanded else "Details")
        visibility(self.details,expanded and not example)
