"""One shortcut editor for Windows/X11; Wayland uses its shared OS chooser."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QDialog,QVBoxLayout,QGridLayout,QLabel,QKeySequenceEdit,QCheckBox,QDialogButtonBox,QPushButton
from .hotkeys import parse_shortcut
from .shortcut_defaults import DEFAULTS,KEYS


def edit_shortcuts(window,focus='prices'):
    dialog=QDialog(window);dialog.setObjectName('hotkeyDialog');dialog.setWindowTitle('Lupin shortcuts');dialog.setMinimumWidth(450)
    layout=QVBoxLayout(dialog);layout.setSpacing(12)
    hint=QLabel('Choose a shortcut for each tool. Win is the Windows/Super key.');hint.setWordWrap(True);layout.addWidget(hint)
    enabled=QCheckBox('Enable global hotkeys');enabled.setChecked(window.hotkey_enabled);layout.addWidget(enabled)
    grid=QGridLayout();editors={}
    managers={'prices':window.hotkeys,'exp':window.exp_hotkeys,'chat':window.chat_hotkeys,'write':window.write_hotkeys}
    previous={'prices':window.hotkey_sequence,'exp':window.exp_sequence,'chat':window.chat_sequence,'write':window.write_sequence}
    previous_enabled=window.hotkey_enabled
    for row,(action,title) in enumerate((('prices','Prices'),('exp','EXP tracking'),('chat','Read Korean'),('write','Write Korean'))):
        editor=QKeySequenceEdit(QKeySequence(previous[action]));editor.setMaximumSequenceLength(1);editor.setObjectName('shortcut-'+action)
        editors[action]=editor;grid.addWidget(QLabel(title),row,0);grid.addWidget(editor,row,1)
    layout.addLayout(grid)
    details=QLabel('');details.setWordWrap(True);layout.addWidget(details)
    defaults=QPushButton('Restore defaults');defaults.clicked.connect(lambda:[editors[k].setKeySequence(QKeySequence(v)) for k,v in DEFAULTS.items()]);layout.addWidget(defaults,0,Qt.AlignmentFlag.AlignLeft)
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Close);layout.addWidget(buttons)
    buttons.rejected.connect(dialog.reject)
    applied=False
    # Release only this app's registrations while the key editors have focus.
    for manager in managers.values():manager.close()
    window.hotkey_dialog_open=True
    def apply():
        nonlocal applied
        try:
            values={action:parse_shortcut(editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText)).text for action,editor in editors.items()}
            if len(set(values.values()))!=4:raise ValueError('Each tool needs a different shortcut.')
            if enabled.isChecked():
                for action,manager in managers.items():
                    if not manager.start(values[action]):
                        for entry in managers.values():entry.close()
                        if previous_enabled:
                            for key,entry in managers.items():entry.start(previous[key])
                        raise ValueError('The '+action+' shortcut is reserved or already in use. Choose another combination.')
            window.hotkey_sequence=values['prices'];window.exp_sequence=values['exp'];window.chat_sequence=values['chat'];window.write_sequence=values['write']
            window.hotkey_enabled=enabled.isChecked();window.settings.setValue('hotkey-enabled',window.hotkey_enabled)
            for action,value in values.items():
                window.settings.setValue(KEYS[action],value);window.settings.setValue(KEYS[action]+'-custom',value!=DEFAULTS[action])
            applied=True;dialog.accept()
        except ValueError as error:details.setText(str(error))
    buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(apply)
    if focus in editors:editors[focus].setFocus()
    try:dialog.exec()
    finally:
        window.hotkey_dialog_open=False
        if not applied:
            for manager in managers.values():manager.close()
        window.initialize_hotkey();dialog.deleteLater()
