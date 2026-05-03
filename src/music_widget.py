import sys
import os
import asyncio
import random
from PyQt6 import QtWidgets as Widgets, QtCore as Core, QtGui as Gui, QtNetwork as Network
import winsdk.windows.media.control as wmc
import winsdk.windows.storage.streams as streams
import keyboard

class MediaWorker(Core.QObject):
    image_ready = Core.pyqtSignal(Gui.QImage)
    status_changed = Core.pyqtSignal(bool)
    metadata_ready = Core.pyqtSignal(str, str)

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
                self.status_changed.emit(info.playback_status == wmc.GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING)
                props = await session.try_get_media_properties_async()
                self.metadata_ready.emit(props.title, props.artist)
                if props.thumbnail:
                    stream = await props.thumbnail.open_read_async()
                    buffer = streams.Buffer(stream.size)
                    await stream.read_async(buffer, stream.size, streams.InputStreamOptions.NONE)
                    reader = streams.DataReader.from_buffer(buffer)
                    data = bytearray(reader.unconsumed_buffer_length)
                    reader.read_bytes(data)
                    img = Gui.QImage.fromData(data)
                    if not img.isNull(): self.image_ready.emit(img)
            else:
                self.status_changed.emit(False)
        except: pass

class MusicWidget(Widgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Core.Qt.WindowType.FramelessWindowHint | Core.Qt.WindowType.WindowStaysOnTopHint | Core.Qt.WindowType.Tool)
        self.setAttribute(Core.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(150, 150)
        self.setMouseTracking(True)

        self.album_pixmap = None
        self.is_playing = False
        self.eq_heights = [2.0] * 5
        self.target_heights = [2.0] * 5
        self.track_title, self.artist_name = "", ""
        self.info_opacity = 0
        self.feedback_icon = None
        self.feedback_opacity = 0.0 # Float for smoother fading
        self.drag_start_pos = None

        self.click_timer = Core.QTimer(); self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self.toggle_play_pause)

        self.reset_to_center()

        self.worker_thread = Core.QThread()
        self.worker = MediaWorker()
        self.worker.moveToThread(self.worker_thread)
        self.data_timer = Core.QTimer(); self.data_timer.timeout.connect(self.worker.check_media); self.data_timer.start(500)
        self.worker.image_ready.connect(self.update_album)
        self.worker.status_changed.connect(self.update_status)
        self.worker.metadata_ready.connect(self.update_metadata)
        self.worker_thread.start()

        self.anim_timer = Core.QTimer(); self.anim_timer.timeout.connect(self.animate_ui); self.anim_timer.start(16)

    def reset_to_center(self):
        screen = Widgets.QApplication.primaryScreen().geometry()
        self.move((screen.width() - 150) // 2, (screen.height() - 150) // 2)
        self.show()

    def update_metadata(self, t, a): self.track_title, self.artist_name = t, a

    def update_album(self, img):
        self.album_pixmap = Gui.QPixmap.fromImage(img).scaled(150, 150, Core.Qt.AspectRatioMode.KeepAspectRatioByExpanding, Core.Qt.TransformationMode.SmoothTransformation)
        self.update()

    def update_status(self, p):
        if self.is_playing != p: self.is_playing = p; self.update()

    def toggle_play_pause(self):
        keyboard.press_and_release('play/pause')
        self.trigger_feedback('play' if not self.is_playing else 'pause')

    def trigger_feedback(self, icon):
        self.feedback_icon = icon
        self.feedback_opacity = 160.0 # Started lower (160/255) for transparency
        self.update()

    def animate_ui(self):
        # 1. EQ Logic
        if self.is_playing:
            for i in range(5):
                if random.random() < 0.1: self.target_heights[i] = random.uniform(8, 22)
                else: self.target_heights[i] *= 0.95
            lerp = 0.07
        else:
            self.target_heights = [2.0] * 5
            lerp = 0.05
        for i in range(5): self.eq_heights[i] += (self.target_heights[i] - self.eq_heights[i]) * lerp

        # 2. Resizing & Info logic
        m = self.mapFromGlobal(Gui.QCursor.pos())
        is_hovering_bar = 50 < m.x() < 100 and 130 < m.y() < 155
        if is_hovering_bar:
            if self.height() < 185: self.setFixedHeight(185)
            self.info_opacity = min(255, self.info_opacity + 20)
        else:
            self.info_opacity = max(0, self.info_opacity - 15)
            if self.info_opacity == 0 and self.height() > 150: self.setFixedHeight(150)

        # 3. Transparent Control Animation Logic
        if self.feedback_opacity > 0:
            self.feedback_opacity *= 0.92 # Exponential decay for smoother transparency fade
            if self.feedback_opacity < 5: self.feedback_opacity = 0; self.feedback_icon = None
        self.update()

    def paintEvent(self, event):
        painter = Gui.QPainter(self)
        painter.setRenderHints(Gui.QPainter.RenderHint.Antialiasing | Gui.QPainter.RenderHint.SmoothPixmapTransform | Gui.QPainter.RenderHint.TextAntialiasing)
        
        # 1. High-Quality Album Art
        path = Gui.QPainterPath()
        path.addRoundedRect(0, 0, 150, 150, 15, 15)
        painter.setClipPath(path)
        if self.album_pixmap: painter.drawPixmap(0, 0, self.album_pixmap)
        else:
            painter.setBrush(Gui.QColor(30, 30, 30)); painter.drawRect(0, 0, 150, 150)
        
        painter.setClipping(False)
        painter.setCompositionMode(Gui.QPainter.CompositionMode.CompositionMode_DestinationOut)
        painter.setBrush(Gui.QColor(255, 255, 255))
        painter.drawRoundedRect(130, 10, 10, 10, 2, 2) # Drag Hole
        
        # 2. Glass UI Elements
        painter.setCompositionMode(Gui.QPainter.CompositionMode.CompositionMode_SourceOver)
        alpha = 140 if self.is_playing else 60
        painter.setBrush(Gui.QColor(255, 255, 255, alpha))
        painter.setPen(Core.Qt.PenStyle.NoPen)
        for i, h in enumerate(self.eq_heights):
            painter.drawRoundedRect(15 + (i * 7), 135 - int(h), 4, int(h), 2, 2)
        painter.drawRoundedRect(55, 140, 40, 4, 2, 2) # Info Bar

        # 3. Transparent Control Feedback (Ghost Icons)
        if self.feedback_opacity > 0:
            painter.setBrush(Gui.QColor(255, 255, 255, int(self.feedback_opacity)))
            if self.feedback_icon == 'play':
                painter.drawPolygon(Gui.QPolygonF([Core.QPointF(64, 61), Core.QPointF(64, 89), Core.QPointF(88, 75)]))
            elif self.feedback_icon == 'pause':
                painter.drawRoundedRect(63, 61, 8, 28, 2, 2); painter.drawRoundedRect(79, 61, 8, 28, 2, 2)
            elif self.feedback_icon == 'next':
                p1 = Gui.QPolygonF([Core.QPointF(92, 65), Core.QPointF(92, 85), Core.QPointF(104, 75)])
                p2 = Gui.QPolygonF([Core.QPointF(104, 65), Core.QPointF(104, 85), Core.QPointF(116, 75)])
                painter.drawPolygon(p1); painter.drawPolygon(p2); painter.drawRoundedRect(117, 65, 3, 20, 1, 1)
            elif self.feedback_icon == 'prev':
                p1 = Gui.QPolygonF([Core.QPointF(58, 65), Core.QPointF(58, 85), Core.QPointF(46, 75)])
                p2 = Gui.QPolygonF([Core.QPointF(46, 65), Core.QPointF(46, 85), Core.QPointF(34, 75)])
                painter.drawPolygon(p1); painter.drawPolygon(p2); painter.drawRoundedRect(30, 65, 3, 20, 1, 1)

        # 4. Info Dropdown
        if self.info_opacity > 0:
            painter.setBrush(Gui.QColor(0, 0, 0, int(self.info_opacity * 0.8)))
            painter.drawRoundedRect(5, 152, 140, 30, 8, 8)
            painter.setPen(Gui.QColor(255, 255, 255, self.info_opacity))
            f = painter.font(); f.setPointSize(8); f.setBold(True); painter.setFont(f)
            painter.drawText(12, 165, painter.fontMetrics().elidedText(self.track_title, Core.Qt.TextElideMode.ElideRight, 125))
            f.setBold(False); f.setPointSize(7); painter.setFont(f)
            painter.drawText(12, 177, painter.fontMetrics().elidedText(self.artist_name, Core.Qt.TextElideMode.ElideRight, 125))

    def mousePressEvent(self, e):
        if e.button() == Core.Qt.MouseButton.LeftButton:
            if e.position().x() > 120 and e.position().y() < 40:
                self.drag_start_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            else: self.drag_start_pos = None

    def mouseMoveEvent(self, e):
        if self.drag_start_pos: self.move(e.globalPosition().toPoint() - self.drag_start_pos)

    def mouseReleaseEvent(self, e):
        if e.button() == Core.Qt.MouseButton.LeftButton and not self.drag_start_pos:
            if not (50 < e.position().x() < 100 and e.position().y() > 130):
                self.click_timer.start(150)
        self.drag_start_pos = None

    def mouseDoubleClickEvent(self, e):
        self.click_timer.stop()
        if e.position().x() < 75: 
            keyboard.press_and_release('previous track'); self.trigger_feedback('prev')
        else: 
            keyboard.press_and_release('next track'); self.trigger_feedback('next')

    def contextMenuEvent(self, event):
        menu = Widgets.QMenu(self)
        menu.setStyleSheet("QMenu { background: #222; color: white; border-radius: 8px; }")
        act = menu.addAction("✕ Close")
        if menu.exec(self.mapToGlobal(Core.QPoint(75, 75))) == act: Widgets.QApplication.instance().quit()

class SingleInstanceApp(Widgets.QApplication):
    def __init__(self, argv, key):
        super().__init__(argv)
        self.key = key
        self.socket = Network.QLocalSocket(self)
        self.socket.connectToServer(self.key)
        if self.socket.waitForConnected(500): sys.exit(0)
        self.server = Network.QLocalServer(self)
        self.server.newConnection.connect(lambda: self.window.reset_to_center())
        self.server.listen(self.key)

if __name__ == "__main__":
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    app = SingleInstanceApp(sys.argv, "GlassWidget_v152")
    window = MusicWidget()
    app.window = window
    sys.exit(app.exec())
