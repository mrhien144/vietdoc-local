from pathlib import Path
import re

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel


app = FastAPI(
    title="VietDoc Local",
    version="2.0.0",
    description="Vietnamese document and language utility for SoloHost"
)

BASE_DIR = Path(__file__).resolve().parent


class TextRequest(BaseModel):
    text: str


@app.get("/")
def home():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "app": "VietDoc Local",
        "version": "2.0.0"
    }


@app.post("/api/text/clean")
def clean_text(data: TextRequest):
    text = data.text

    # Xóa khoảng trắng thừa
    text = re.sub(r"[ \t]+", " ", text)

    # Xóa khoảng trắng trước dấu câu
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)

    # Thêm một khoảng trắng sau dấu câu nếu bị thiếu
    text = re.sub(r"([,.;:!?])([^\s\n])", r"\1 \2", text)

    # Chuẩn hóa khoảng trắng quanh xuống dòng
    text = re.sub(r" *\n *", "\n", text)

    # Không để quá 2 dòng trống liên tiếp
    text = re.sub(r"\n{3,}", "\n\n", text)

    return {
        "text": text.strip()
    }


@app.post("/api/text/stats")
def text_stats(data: TextRequest):
    text = data.text

    words = re.findall(r"\S+", text)
    lines = text.splitlines()

    return {
        "characters": len(text),
        "characters_without_spaces": len(re.sub(r"\s", "", text)),
        "words": len(words),
        "lines": len(lines)
    }


@app.post("/api/text/uppercase")
def uppercase(data: TextRequest):
    return {
        "text": data.text.upper()
    }


@app.post("/api/text/lowercase")
def lowercase(data: TextRequest):
    return {
        "text": data.text.lower()
    }
