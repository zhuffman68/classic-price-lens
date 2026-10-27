"""Shared cross-platform defaults; retain explicitly customized assignments."""
import sys

DEFAULTS={'prices':'Meta+F9','exp':'Meta+F10','chat':'Meta+F11','write':'Meta+F8'}
KEYS={'prices':'hotkey-sequence','exp':'exp-hotkey','chat':'chat-hotkey','write':'write-hotkey'}
LEGACY={'prices':'F10','exp':'F11','chat':'F9' if sys.platform=='win32' else 'F12','write':'F8'}


def load(settings):
    result={}
    migrating=settings.value('shortcut-layout',0,type=int)<2
    for action,key in KEYS.items():
        value=settings.value(key,None)
        if value is None or migrating and value==LEGACY[action] and not settings.value(key+'-custom',False,type=bool):
            value=DEFAULTS[action];settings.setValue(key,value)
            description='hotkey-description' if action=='prices' else action+'-hotkey-description'
            settings.setValue(description,label(value))
        result[action]=value
    settings.setValue('shortcut-layout',2)
    return result


def label(sequence):
    return str(sequence).replace('Meta+',('Win' if sys.platform=='win32' else 'Super')+' + ')
