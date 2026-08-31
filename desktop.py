import threading
import time
import base64
import io
import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path

from pydub import AudioSegment
import imageio_ffmpeg
AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()

import uvicorn
import webview
import webbrowser
from urllib.parse import urlparse

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

    def open_external_url(self, url):
        try:
            parsed = urlparse(url)

            if parsed.scheme != "https" or parsed.hostname != "pay.payos.vn":
                return {
                    "ok": False,
                    "message": "Đường dẫn thanh toán không hợp lệ."
                }

            webbrowser.open(url, new=2)

            return {
                "ok": True,
                "message": "Đã mở trang thanh toán."
            }

        except Exception as exc:
            return {
                "ok": False,
                "message": str(exc)
            }
    def install_update(self, download_url, expected_sha256):
        try:
            parsed = urlparse(download_url)
            allowed_prefix = "/mrhien144/vietdoc-local/releases/download/"

            if (
                parsed.scheme != "https"
                or parsed.hostname != "github.com"
                or not parsed.path.startswith(allowed_prefix)
            ):
                return {
                    "ok": False,
                    "message": "Link cập nhật không hợp lệ."
                }

            expected_sha256 = (expected_sha256 or "").strip().lower()

            if (
                len(expected_sha256) != 64
                or any(
                    char not in "0123456789abcdef"
                    for char in expected_sha256
                )
            ):
                return {
                    "ok": False,
                    "message": "Mã SHA256 không hợp lệ."
                }

            request = urllib.request.Request(
                download_url,
                headers={
                    "User-Agent": "VoxVietAI-Updater/1.0"
                }
            )

            sha256 = hashlib.sha256()

            with tempfile.NamedTemporaryFile(
                prefix="VoxVietAI-Update-",
                suffix=".exe",
                delete=False
            ) as temp_file:
                installer_path = Path(temp_file.name)

                with urllib.request.urlopen(
                    request,
                    timeout=120
                ) as response:
                    while True:
                        chunk = response.read(1024 * 1024)

                        if not chunk:
                            break

                        temp_file.write(chunk)
                        sha256.update(chunk)

            actual_sha256 = sha256.hexdigest().lower()

            if actual_sha256 != expected_sha256:
                try:
                    installer_path.unlink()
                except OSError:
                    pass

                return {
                    "ok": False,
                    "message": "SHA256 không khớp. Đã hủy cập nhật."
                }

            os.startfile(str(installer_path), "runas")

            def close_after_launch():
                time.sleep(1.5)
                window = webview.windows[0] if webview.windows else None

                if window:
                    window.destroy()

            threading.Thread(
                target=close_after_launch,
                daemon=True
            ).start()

            return {
                "ok": True,
                "message": "Đã xác minh và mở trình cài đặt."
            }

        except Exception as exc:
            return {
                "ok": False,
                "message": f"Không thể cập nhật: {exc}"
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
