"""Validate native IPC association proofs without opening any screen share."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtGui import QColor,QImage
from PySide6.QtWidgets import QApplication

from price_lens.capture import PixelReader


class AssociationCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_native_cache_rejects_changed_slot_guards_even_with_an_unchanged_name(self):
        root=Path(__file__).resolve().parents[1]
        reader=PixelReader(root);reader.timer.stop();reader.auto_enabled=False
        frame=QImage(800,600,QImage.Format.Format_RGBA8888);frame.fill(QColor('navy'))
        reader.image=reader.submitted_image=frame
        reader.pointer=reader.last_pointer=(340,190)
        # A newer frame can retain this proof only if all source guards match.
        reader.image_sequence=1;reader.submitted_sequence=0
        result={'atMs':0,'shop':None,'tooltip':{'found':{'name':'Example Hat',
                'area':dict(x=58,y=111,width=180,height=12)}},
                'tooltipAssociation':{'state':'inventory-primary','token':'context:slot',
                'source':dict(x=300,y=150,width=230,height=300),
                'slot':dict(x=324,y=174,width=36,height=36),
                'panel':dict(x=50,y=100,width=240,height=330),
                'guards':[dict(x=300,y=150,width=230,height=20)]}}
        received=[];reader.reading.connect(received.append)
        try:
            self.assertTrue(reader.process.waitForStarted(3000))
            # Prevent the usual next-frame scheduler; this test supplies IPC only.
            with patch('price_lens.capture.QTimer.singleShot'):
                def receive():
                    message=(json.dumps(result)+'\n').encode()
                    with patch.object(reader.process,'readAllStandardOutput',return_value=message):reader.on_output()
                receive()
                self.assertEqual(received[-1]['tooltip']['found']['name'],'Example Hat')
                self.assertIsNotNone(reader.tooltip_fingerprint)
                self.assertIsNotNone(reader.tooltip_association)
                reader.image=frame.copy();reader.image.setPixelColor(301,151,QColor('red'))
                receive()
                self.assertEqual(received[-1]['tooltipAssociation']['state'],'rejected')
                self.assertIsNone(received[-1]['tooltip']['found'])
                self.assertIsNone(reader.tooltip_rect)
                self.assertIsNone(reader.tooltip_fingerprint)
                self.assertIsNone(reader.tooltip_association)
        finally:
            reader.close();reader.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()


if __name__=='__main__':unittest.main()
