"""Compact accessible paths that keep every ancestor reachable at narrow widths."""
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QHBoxLayout,QMenu,QSizePolicy,QToolButton,QWidget


class Breadcrumb(QWidget):
    chosen=Signal(int)

    def __init__(self,parent=None):
        super().__init__(parent);self.parts=[];self.full_text=''
        self.setMinimumWidth(0);self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        layout=QHBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(2)
        self.root=QToolButton();self.root.clicked.connect(lambda:self.chosen.emit(0));layout.addWidget(self.root)
        self.path=QToolButton();self.path.setMinimumWidth(0);self.path.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.path.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);self.menu=QMenu(self.path);self.path.setMenu(self.menu)
        layout.addWidget(self.path,1)
        self.empty=QWidget();layout.addWidget(self.empty,1)
        self.setStyleSheet('QToolButton{color:#b9c8dc;background:transparent;border:0;border-radius:5px;padding:5px 3px;font-size:11px;} QToolButton:hover{background:#2b394d;color:#f0d5a8;} QToolButton::menu-indicator{image:none;}')

    def set_path(self,kind,scope,selected=None):
        parts=[kind.capitalize(),*[str(label) for field,value,label in scope]]
        if selected:parts.append(selected.name)
        signature=(tuple(parts),len(scope))
        if signature==getattr(self,'signature',None):return
        self.signature=signature;self.parts=parts;self.full_text=' › '.join(parts);self.setToolTip(self.full_text)
        self.root.setText(parts[0]);self.root.setAccessibleName('Browse all '+kind);self.menu.clear()
        for depth,label in enumerate(parts):
            action=self.menu.addAction(label.replace('&','&&'))
            if depth>len(scope):action.setEnabled(False)
            else:action.triggered.connect(lambda checked=False,depth=depth:self.chosen.emit(depth))
        self.path.setVisible(len(parts)>1);self.empty.setVisible(len(parts)==1);self.path.setToolTip(self.full_text);self.path.setAccessibleName(self.full_text)
        self.fit()

    def text(self):return self.full_text

    def fit(self):
        if not self.parts:return
        width=max(0,self.width()-self.root.sizeHint().width()-4)
        text=' › '.join(self.parts[1:])
        self.path.setText(self.path.fontMetrics().elidedText('› '+text+' ▾',Qt.TextElideMode.ElideMiddle,width).replace('&','&&'))

    def resizeEvent(self,event):super().resizeEvent(event);self.fit()
