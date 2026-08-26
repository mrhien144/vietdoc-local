import threading
import time
import base64
import io

from pydub import AudioSegment
import imageio_ffmpeg
AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()

import uvicorn
import webview

from app import app
class DesktopApi:
    def save_audio(self, audio_base64, audio_format="wav"):
        window = webview.active_window()

        if not window:
            return {"ok": False, "message": "Không tìm thấy cửa sổ ứng dụng."}
        audio_format = audio_format.lower()

        if audio_format == "mp3":
            save_filename = "voxviet-ai.mp3"
            file_types = ("MP3 Audio (*.mp3)",)
        else:
            audio_format = "wav"
            save_filename = "voxviet-ai.wav"
            file_types = ("WAV Audio (*.wav)",)

        result = window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=save_filename,
            file_types=file_types,
        )

        if not result:
            return {"ok": False, "message": "Đã hủy lưu file."}

        file_path = result[0] if isinstance(result, (list, tuple)) else result

        audio_bytes = base64.b64decode(audio_base64)

        if audio_format == "mp3":
            audio = AudioSegment.from_wav(
                io.BytesIO(audio_bytes)
            )

            output_buffer = io.BytesIO()

            audio.export(
                output_buffer,
                format="mp3",
                bitrate="192k"
            )

            output_bytes = output_buffer.getvalue()

        else:
            output_bytes = audio_bytes

        with open(file_path, "wb") as audio_file:
            audio_file.write(output_bytes)

        return {
            "ok": True,
            "message": "Đã lưu file âm thanh.",
            "path": file_path
        }

def run_server():
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=8765,
        log_level="warning"
    )

    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    server_thread = threading.Thread(
        target=run_server,
        daemon=True
    )
    server_thread.start()

    time.sleep(1)
    api = DesktopApi()
    webview.create_window(
        "VoxViet AI",
        "http://127.0.0.1:8765",
        width=1200,
        height=800,
        min_size=(900, 650),
        js_api=api
    )

    webview.start()
