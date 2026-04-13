import sys
import asyncio
import winsdk.windows.media.control as wmc
import winsdk.windows.storage.streams as streams
import PyQt6.QtWidgets as Widgets
import PyQt6.QtCore as Core
import PyQt6.QtGui as Gui
import keyboard

# --- DATA WORKER (Media Sync) ---
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

# --- THE WIDGET ---
class MusicWidget(Widgets.QWidget):
    def __init__(self):
        super().__init__()
        
        # Frameless, On Top, No Taskbar Icon
        self.setWindowFlags(Core.Qt.WindowType.FramelessWindowHint | Core.Qt.WindowType.WindowStaysOnTopHint | Core.Qt.WindowType.Tool)
        self.setAttribute(Core.Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # FIXED SMALL SIZE
        self.setFixedSize(150, 150)
        
        self.album_pixmap = None
        self.drag_start_pos = None

        # Logic Timer for Single/Double Click
        self.click_timer = Core.QTimer()
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(lambda: keyboard.press_and_release('play/pause'))

        # Background Worker
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
        # High-quality scaling for the small window
        self.album_pixmap = Gui.QPixmap.fromImage(img).scaled(
            150, 150, 
            Core.Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
            Core.Qt.TransformationMode.SmoothTransformation
        )
        self.update()

    def contextMenuEvent(self, event):
        # Create a stylish context menu
        menu = Widgets.QMenu(self)
        
        # Style the menu to match the dark theme
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

        # Add the 'Close' action with an icon-like feel
        close_action = menu.addAction("✕  Close Widget")
        
        # Execute the menu and quit if "Close" is clicked
        action = menu.exec(self.mapToGlobal(event.pos()))
        if action == close_action:
            # Optional: Add a fade-out animation before quitting
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

        # 1. DRAW ALBUM COVER
        path = Gui.QPainterPath()
        path.addRoundedRect(0, 0, w, h, 15, 15)
        painter.setClipPath(path)
        
        if self.album_pixmap:
            painter.drawPixmap(0, 0, self.album_pixmap)
        else:
            painter.setBrush(Gui.QColor(30, 30, 30))
            painter.drawRect(0, 0, w, h)

        # 2. THE INTERACTIVE PUNCHHOLE
        # We stop clipping so we can draw the hole clearly
        painter.setClipping(False)
        
        # We use DestinationOut to create the hole effect
        painter.setCompositionMode(Gui.QPainter.CompositionMode.CompositionMode_DestinationOut)
        
        hole_size = 16
        margin = 10
        hole_rect = Core.QRect(w - hole_size - margin, margin, hole_size, hole_size)
        
        # DRAWING THE HOLE:
        # We use a color with '1' alpha. 
        # 0 = Click falls through (Non-interactive)
        # 1-255 = Click registers (Interactive)
        # We use 255 here but because the Mode is 'DestinationOut', it stays transparent!
        painter.setBrush(Gui.QColor(255, 255, 255, 255)) 
        painter.setPen(Core.Qt.PenStyle.NoPen)
        painter.drawEllipse(hole_rect)
        
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Core.Qt.MouseButton.LeftButton:
            x, y = event.position().x(), event.position().y()
            w = self.width()
            
            # Hitbox for the punchhole
            if x > w - 30 and y < 30: 
                self.drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.is_dragging = False # Reset flag on new press
            else:
                self.drag_start_pos = None
    def mouseReleaseEvent(self, event):
        if event.button() == Core.Qt.MouseButton.LeftButton:
            # ONLY pause if we were NOT dragging
            if not self.is_dragging:
                x = event.position().x()
                # Ensure we only pause if clicking the album area, not the hole
                if x < self.width() - 30:
                    self.click_timer.start(200)
            
            # Reset everything
            self.is_dragging = False
            self.drag_start_pos = None

    def mouseDoubleClickEvent(self, event):
        self.click_timer.stop() # Prevent Play/Pause
        if event.position().x() < 75:
            keyboard.press_and_release('previous track')
        else:
            keyboard.press_and_release('next track')

    def mouseMoveEvent(self, event):
        if self.drag_start_pos:
            # If the mouse moves even a little, mark it as a drag
            self.is_dragging = True
            self.move(event.globalPosition().toPoint() - self.drag_start_pos)

if __name__ == "__main__":
    app = Widgets.QApplication(sys.argv)
    window = MusicWidget()
    window.show()
    sys.exit(app.exec())