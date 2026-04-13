import sys
import asyncio
import winsdk.windows.media.control as wmc
import winsdk.windows.storage.streams as streams
import PyQt6.QtWidgets as Widgets
import PyQt6.QtCore as Core
import PyQt6.QtGui as Gui
import keyboard

class MediaWorker(Core.QObject):
    image_ready = Core.pyqtSignal(Gui.QImage)
    status_changed = Core.pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self._loop = asyncio.new_event_loop()

    @Core.pyqtSlot()
    def check_media(self):
        try:
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._fetch_data())
        except: pass

    async def _fetch_data(self):
        manager = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
        session = manager.get_current_session()
        if session:
            info = session.get_playback_info()
            self.status_changed.emit(info.playback_status == wmc.GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING)
            props = await session.try_get_media_properties_async()
            if props.thumbnail:
                stream = await props.thumbnail.open_read_async()
                buffer = streams.Buffer(stream.size)
                await stream.read_async(buffer, stream.size, streams.InputStreamOptions.NONE)
                reader = streams.DataReader.from_buffer(buffer)
                data = bytearray(reader.unconsumed_buffer_length)
                reader.read_bytes(data)
                img = Gui.QImage.fromData(data)
                if not img.isNull(): self.image_ready.emit(img)

class MusicWidget(Widgets.QWidget):
    def __init__(self):
        super().__init__()
        
        self.setWindowFlags(Core.Qt.WindowType.FramelessWindowHint | Core.Qt.WindowType.WindowStaysOnTopHint | Core.Qt.WindowType.Tool)
        self.setAttribute(Core.Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.setFixedSize(150, 150)
        
        self.album_pixmap = None
        self.drag_start_pos = None

        self.click_timer = Core.QTimer()
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(lambda: keyboard.press_and_release('play/pause'))

        self.worker_thread = Core.QThread()
        self.worker = MediaWorker()
        self.worker.moveToThread(self.worker_thread)
        self.data_timer = Core.QTimer()
        self.data_timer.timeout.connect(self.worker.check_media)
        self.data_timer.start(2000)
        self.worker.image_ready.connect(self.update_album)
        self.worker_thread.start()
        self.is_dragging = False

    def update_album(self, img):
        self.album_pixmap = Gui.QPixmap.fromImage(img).scaled(
            150, 150, 
            Core.Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
            Core.Qt.TransformationMode.SmoothTransformation
        )
        self.update()

    def contextMenuEvent(self, event):
        menu = Widgets.QMenu(self)
        
        menu.setStyleSheet("""
            QMenu {
                background-color: #181818;
                color: white;
                border: 1px solid #333;
                border-radius: 10px;
                padding: 5px;
            }
            QMenu::item:selected {
                background-color: #e81123; /* Windows Close Red */
                border-radius: 5px;
            }
        """)

        close_action = menu.addAction("✕  Close Widget")

        action = menu.exec(self.mapToGlobal(event.pos()))
        if action == close_action:
            self.fade_out_and_quit()

    def fade_out_and_quit(self):
        self.anim = Core.QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(400)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(Widgets.QApplication.instance().quit)
        self.anim.start()

    def paintEvent(self, event):
        painter = Gui.QPainter(self)
        painter.setRenderHint(Gui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(Gui.QPainter.RenderHint.SmoothPixmapTransform)
        
        w, h = self.width(), self.height()

        path = Gui.QPainterPath()
        path.addRoundedRect(0, 0, w, h, 15, 15)
        painter.setClipPath(path)
        
        if self.album_pixmap:
            painter.drawPixmap(0, 0, self.album_pixmap)
        else:
            painter.setBrush(Gui.QColor(30, 30, 30))
            painter.drawRect(0, 0, w, h)

        painter.setClipping(False)
        
        painter.setCompositionMode(Gui.QPainter.CompositionMode.CompositionMode_DestinationOut)
        
        hole_size = 16
        margin = 10
        hole_rect = Core.QRect(w - hole_size - margin, margin, hole_size, hole_size)
        
        painter.setBrush(Gui.QColor(255, 255, 255, 255)) 
        painter.setPen(Core.Qt.PenStyle.NoPen)
        painter.drawEllipse(hole_rect)
        
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Core.Qt.MouseButton.LeftButton:
            x, y = event.position().x(), event.position().y()
            w = self.width()
            
            if x > w - 30 and y < 30: 
                self.drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.is_dragging = False
            else:
                self.drag_start_pos = None
    def mouseReleaseEvent(self, event):
        if event.button() == Core.Qt.MouseButton.LeftButton:
            if not self.is_dragging:
                x = event.position().x()
                if x < self.width() - 30:
                    self.click_timer.start(200)
            
            self.is_dragging = False
            self.drag_start_pos = None

    def mouseDoubleClickEvent(self, event):
        self.click_timer.stop()
        if event.position().x() < 75:
            keyboard.press_and_release('previous track')
        else:
            keyboard.press_and_release('next track')

    def mouseMoveEvent(self, event):
        if self.drag_start_pos:
            self.is_dragging = True
            self.move(event.globalPosition().toPoint() - self.drag_start_pos)

if __name__ == "__main__":
    app = Widgets.QApplication(sys.argv)
    window = MusicWidget()
    window.show()
    sys.exit(app.exec())
