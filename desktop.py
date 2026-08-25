import threading
import time

import uvicorn
import webview

from app import app


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

    webview.create_window(
        "VoxViet AI",
        "http://127.0.0.1:8765",
        width=1200,
        height=800,
        min_size=(900, 650)
    )

    webview.start()
