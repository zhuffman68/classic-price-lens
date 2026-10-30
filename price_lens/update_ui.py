"""Update settings and a compact install sheet; no changes to the main layout."""
from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QCheckBox,QDialog,QDialogButtonBox,QHBoxLayout,QLabel,QProgressBar,QPushButton,QSpinBox,QVBoxLayout,QWidget
from . import __version__
from .motion import MotionLabel
from .updates import RELEASES


class UpdatePanel(QWidget):
    def __init__(self,service,parent=None,*,settings=False):
        super().__init__(parent);self.service=service;self.settings_mode=settings
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(8)
        title=QLabel('Lupin updates' if settings else 'Update Lupin');title.setStyleSheet('font-size:16px;font-weight:650');layout.addWidget(title)
        self.status=MotionLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        self.detail=QLabel();self.detail.setTextFormat(Qt.TextFormat.PlainText);self.detail.setWordWrap(True);self.detail.setStyleSheet('color:#a6b1bf;font-size:11px');layout.addWidget(self.detail)
        if settings:
            self.launch=QCheckBox('Check for updates on launch');self.launch.setChecked(service.settings.value('update-on-launch',True,type=bool))
            self.launch.toggled.connect(lambda value:service.settings.setValue('update-on-launch',value));layout.addWidget(self.launch)
            row=QHBoxLayout();row.addWidget(QLabel('Check every'));row.addStretch()
            self.interval=QSpinBox();self.interval.setRange(15,10080);self.interval.setSuffix(' min');self.interval.setMinimumWidth(105)
            value=service.settings.value('update-interval-minutes',360,type=int);self.interval.setValue(value if value else 360)
            self.periodic=QCheckBox('While Lupin is open');self.periodic.setChecked(bool(value));self.interval.setEnabled(bool(value))
            def configure(*_):
                self.interval.setEnabled(self.periodic.isChecked());service.settings.setValue('update-interval-minutes',self.interval.value() if self.periodic.isChecked() else 0);service.configure()
            self.interval.valueChanged.connect(configure);self.periodic.toggled.connect(configure)
            row.addWidget(self.interval);layout.addLayout(row);layout.addWidget(self.periodic)
        self.progress=QProgressBar();self.progress.setRange(0,100);layout.addWidget(self.progress)
        actions=QHBoxLayout();self.check=QPushButton('Check now');self.check.clicked.connect(service.check);self.check.setVisible(settings);actions.addWidget(self.check)
        self.install=QPushButton('Download && install');self.install.setObjectName('primary');self.install.clicked.connect(service.download_install);actions.addWidget(self.install,1)
        self.cancel=QPushButton('Cancel');self.cancel.clicked.connect(service.cancel);actions.addWidget(self.cancel)
        self.notes=QPushButton('Release notes');self.notes.setObjectName('ghost');self.notes.clicked.connect(lambda:QDesktopServices.openUrl(QUrl(RELEASES)));actions.addWidget(self.notes)
        layout.addLayout(actions);service.changed.connect(self.refresh);self.refresh()

    def refresh(self):
        s=self.service;offer=s.offer;new=offer['manifest']['version'] if offer else ''
        value=f'Lupin {__version__} → {new}' if offer else f'Lupin {__version__}'
        if s.state=='checking':value='Checking for updates…'
        elif s.state=='downloading':value='Downloading Lupin '+new+'…'
        elif s.state=='preparing':value='Preparing installation…'
        elif s.state=='cancelling':value='Cancelling…'
        elif s.state=='installing':value='Restarting to install…'
        elif s.last_checked and not offer and not s.error:value+=' · up to date'
        self.status.setText(value)
        detail=s.error
        if not detail and offer:detail=f"Up to {offer['package']['bytes']/1_000_000:.1f} MB · Lupin restarts after installation"
        if s.state=='downloading':detail=f'{s.progress[0]/1_000_000:.1f} / {s.progress[1]/1_000_000:.1f} MB downloaded'
        if not detail and s.last_checked:detail='Last checked '+datetime.fromtimestamp(s.last_checked).strftime('%b %d, %H:%M')
        if s.state=='preparing':detail='Approve the system authentication prompt to continue. Cancelling keeps Lupin open.' if s.target.name.startswith('linux-') else 'Verifying the installer before closing Lupin.'
        if not s.target.installable:detail=(detail+'\n' if detail else '')+'Automatic installation is available in packaged builds.'
        self.detail.setText(detail);self.progress.setVisible(s.state=='downloading')
        count,total=s.progress;self.progress.setValue(round(count/max(1,total)*100))
        self.install.setVisible(bool(offer));self.install.setEnabled(s.target.installable and not s.busy and not s.committed)
        self.check.setEnabled(not s.busy and not s.committed);self.cancel.setVisible(s.busy);self.notes.setVisible(bool(offer))


class UpdateDialog(QDialog):
    def __init__(self,service,parent=None):
        super().__init__(parent);self.setWindowTitle('Lupin update');self.setMinimumWidth(390)
        layout=QVBoxLayout(self);layout.addWidget(UpdatePanel(service,self))
        buttons=QDialogButtonBox();buttons.addButton('Later',QDialogButtonBox.ButtonRole.RejectRole);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
