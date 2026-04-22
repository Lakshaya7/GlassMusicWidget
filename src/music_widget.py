import sys
import asyncio
import random
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
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._fetch())

    async def _fetch(self):
        try:
            manager = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
            session = manager.get_current_session()
            
            if session:
                info = session.get_playback_info()
                is_playing = info.playback_status == wmc.GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING
                self.status_changed.emit(is_playing)

                props = await session.try_get_media_properties_async()
                if props.thumbnail:
                    stream = await props.thumbnail.open_read_async()
                    buffer = streams.Buffer(stream.size)
                    await stream.read_async(buffer, stream.size, streams.InputStreamOptions.NONE)
                    reader = streams.DataReader.from_buffer(buffer)
                    data = bytearray(reader.unconsumed_buffer_length)
                    reader.read_bytes(data)
                    img = Gui.QImage.fromData(data)
                    if not img.isNull():
                        self.image_ready.emit(img)
            else:
                self.status_changed.emit(False)
        except Exception as e:
            pass

class MusicWidget(Widgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Core.Qt.WindowType.FramelessWindowHint | Core.Qt.WindowType.WindowStaysOnTopHint | Core.Qt.WindowType.Tool)
        self.setAttribute(Core.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(150, 150)

        self.album_pixmap = None
        self.is_playing = False
        self.eq_heights = [2.0] * 5
        self.target_heights = [2.0] * 5
        self.drag_start_pos = None
        self.is_dragging = False

        self.feedback_icon = None
        self.feedback_opacity = 0.0

        self.worker_thread = Core.QThread()
        self.worker = MediaWorker()
        self.worker.moveToThread(self.worker_thread)
        
        self.data_timer = Core.QTimer()
        self.data_timer.timeout.connect(self.worker.check_media)
    
        self.data_timer.start(200) 

        self.anim_timer = Core.QTimer()
        self.anim_timer.timeout.connect(self.animate_ui)
        self.anim_timer.start(16) # 60 FPS

        self.worker.image_ready.connect(self.update_album)
        self.worker.status_changed.connect(self.update_status)
        self.worker_thread.start()

    
        self.click_timer = Core.QTimer()
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self.toggle_play_pause)

    def toggle_play_pause(self):
        keyboard.press_and_release('play/pause')
        
        guessed_state = not self.is_playing 
        self.is_playing = guessed_state
        self.trigger_feedback('play' if guessed_state else 'pause')

    def trigger_feedback(self, icon_type):
        self.feedback_icon = icon_type
        self.feedback_opacity = 180.0
        self.update()

    def update_status(self, playing):
        if self.is_playing != playing:
            self.is_playing = playing
            self.trigger_feedback('play' if playing else 'pause')

    def update_album(self, img):
        self.album_pixmap = Gui.QPixmap.fromImage(img)
        self.update()

    def animate_ui(self):
        if self.is_playing:
            if random.random() < 0.10: 
                self.target_heights = [random.uniform(5, 24) for _ in range(5)]
            lerp = 0.15
        else:
            self.target_heights = [2.0] * 5
            lerp = 0.2

        for i in range(5):
            self.eq_heights[i] += (self.target_heights[i] - self.eq_heights[i]) * lerp

        if self.feedback_opacity > 0:
            self.feedback_opacity *= 0.95 
            
            if self.feedback_opacity < 2.0:
                self.feedback_opacity = 0.0
                self.feedback_icon = None

        self.update()

    def paintEvent(self, event):
        painter = Gui.QPainter(self)
        painter.setRenderHints(Gui.QPainter.RenderHint.Antialiasing | Gui.QPainter.RenderHint.SmoothPixmapTransform)

        path = Gui.QPainterPath()
        path.addRoundedRect(0, 0, 150, 150, 15, 15)
        painter.setClipPath(path)
        if self.album_pixmap:
            painter.drawPixmap(self.rect(), self.album_pixmap)
        else:
            painter.setBrush(Gui.QColor(30, 30, 30))
            painter.drawRect(0, 0, 150, 150)

        painter.setClipping(False)
        alpha = 200 if self.is_playing else 100
        painter.setBrush(Gui.QColor(255, 255, 255, alpha))
        painter.setPen(Core.Qt.PenStyle.NoPen)
        for i, h in enumerate(self.eq_heights):
            painter.drawRoundedRect(15 + (i * 7), 135 - int(h), 4, int(h), 2, 2)

        if self.feedback_opacity > 0 and self.feedback_icon:
            painter.setBrush(Gui.QColor(255, 255, 255, int(self.feedback_opacity)))
            
            if self.feedback_icon == 'play':
                poly = Gui.QPolygonF([Core.QPointF(64, 61), Core.QPointF(64, 89), Core.QPointF(88, 75)])
                painter.drawPolygon(poly)
            elif self.feedback_icon == 'pause':
                painter.drawRoundedRect(63, 61, 8, 28, 2, 2)
                painter.drawRoundedRect(79, 61, 8, 28, 2, 2)
            elif self.feedback_icon == 'next':
                poly1 = Gui.QPolygonF([Core.QPointF(92, 65), Core.QPointF(92, 85), Core.QPointF(104, 75)])
                poly2 = Gui.QPolygonF([Core.QPointF(104, 65), Core.QPointF(104, 85), Core.QPointF(116, 75)])
                painter.drawPolygon(poly1)
                painter.drawPolygon(poly2)
                painter.drawRoundedRect(117, 65, 3, 20, 1, 1)
            elif self.feedback_icon == 'prev':
                poly1 = Gui.QPolygonF([Core.QPointF(58, 65), Core.QPointF(58, 85), Core.QPointF(46, 75)])
                poly2 = Gui.QPolygonF([Core.QPointF(46, 65), Core.QPointF(46, 85), Core.QPointF(34, 75)])
                painter.drawPolygon(poly1)
                painter.drawPolygon(poly2)
                painter.drawRoundedRect(30, 65, 3, 20, 1, 1)

        painter.setCompositionMode(Gui.QPainter.CompositionMode.CompositionMode_DestinationOut)
        painter.setBrush(Gui.QColor(255, 255, 255))
        painter.drawEllipse(126, 10, 14, 14)

    def contextMenuEvent(self, event):
        menu = Widgets.QMenu(self)
        menu.setStyleSheet("QMenu { background: #1DB954; color: white; border-radius: 10px; font-weight: bold; }")
        close_action = menu.addAction("✕ Close")
        spawn_pos = self.mapToGlobal(Core.QPoint(75, 75)) - Core.QPoint(40, 20)
        if menu.exec(spawn_pos) == close_action:
            Widgets.QApplication.instance().quit()

    def mousePressEvent(self, event):
        if event.button() == Core.Qt.MouseButton.LeftButton:
            if event.position().x() > 120 and event.position().y() < 40:
                self.drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.is_dragging = False
            else: self.drag_start_pos = None

    def mouseMoveEvent(self, event):
        if self.drag_start_pos:
            self.is_dragging = True
            self.move(event.globalPosition().toPoint() - self.drag_start_pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Core.Qt.MouseButton.LeftButton and not self.is_dragging:
            if event.position().x() < 120: 
                self.click_timer.start(150) 
        self.is_dragging = False

    def mouseDoubleClickEvent(self, event):
        self.click_timer.stop()
        if event.position().x() < 75:
            keyboard.press_and_release('previous track')
            self.trigger_feedback('prev')
        else:
            keyboard.press_and_release('next track')
            self.trigger_feedback('next')

if __name__ == "__main__":
    import os
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    app = Widgets.QApplication(sys.argv)
    window = MusicWidget()
    window.show()
    sys.exit(app.exec())
