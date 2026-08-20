from pathlib import Path
import re
from functools import lru_cache
from threading import Lock

from argostranslate import package as argos_package
from argostranslate import translate as argos_translate
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel


app = FastAPI(
    title="VietDoc Local",
    version="2.1.0",
    description="Vietnamese document and language utility for SoloHost"
)

BASE_DIR = Path(__file__).resolve().parent

DIACRITIC_MODEL_ID = "nrl-ai/vn-diacritic-small"
ARGOS_INSTALL_LOCK = Lock()

class TextRequest(BaseModel):
    text: str

class TranslationRequest(BaseModel):
    text: str
    direction: str
def argos_pair_installed(from_code: str, to_code: str) -> bool:
    installed_packages = argos_package.get_installed_packages()

    return any(
        pkg.from_code == from_code
        and pkg.to_code == to_code
        for pkg in installed_packages
    )


def ensure_argos_pair(from_code: str, to_code: str):
    if argos_pair_installed(from_code, to_code):
        return

    with ARGOS_INSTALL_LOCK:

        if argos_pair_installed(from_code, to_code):
            return

        argos_package.update_package_index()

        available_packages = (
            argos_package.get_available_packages()
        )

        package_to_install = next(
            (
                pkg
                for pkg in available_packages
                if pkg.from_code == from_code
                and pkg.to_code == to_code
            ),
            None
        )

        if package_to_install is None:
            raise RuntimeError(
                f"Không tìm thấy model dịch "
                f"{from_code} -> {to_code}."
            )

        package_to_install.install()
        @app.get("/")
def home():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "app": "VietDoc Local",
        "version": "2.1.0",
        "diacritic_model": DIACRITIC_MODEL_ID
    }

@app.post("/api/translate")
def translate_text(data: TranslationRequest):

    text = data.text.strip()

    if not text:
        raise HTTPException(
            status_code=400,
            detail="Chưa có văn bản để dịch."
        )

    directions = {
        "vi-en": ("vi", "en"),
        "en-vi": ("en", "vi")
    }

    language_pair = directions.get(
        data.direction
    )

    if language_pair is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Chỉ hỗ trợ dịch Việt → Anh "
                "và Anh → Việt."
            )
        )

    from_code, to_code = language_pair

    try:

        ensure_argos_pair(
            from_code,
            to_code
        )

        translated = argos_translate.translate(
            data.text,
            from_code,
            to_code
        )

        return {
            "text": translated,
            "direction": data.direction
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Không thể dịch văn bản. "
                "Vui lòng kiểm tra model dịch."
            )
        ) from exc
@app.post("/api/text/clean")
def clean_text(data: TextRequest):
    text = data.text

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])([^\s\n])", r"\1 \2", text)
    text = re.sub(r" *\n *", "\n", text)
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


@lru_cache(maxsize=1)
def get_diacritic_model():
    """
    Tải model khi người dùng sử dụng chức năng thêm dấu lần đầu.
    Model chỉ được giữ một bản trong bộ nhớ của container.
    """

    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

    tokenizer = AutoTokenizer.from_pretrained(
        DIACRITIC_MODEL_ID
    )

    model = AutoModelForSeq2SeqLM.from_pretrained(
        DIACRITIC_MODEL_ID
    )

    model.eval()

    return tokenizer, model


def split_long_sentence(text, max_words=70):
    """
    Chia câu quá dài thành các đoạn nhỏ để tránh vượt giới hạn model.
    """

    words = text.split()

    if len(words) <= max_words:
        return [text]

    chunks = []

    for i in range(0, len(words), max_words):
        chunks.append(
            " ".join(words[i:i + max_words])
        )

    return chunks


def restore_diacritics_piece(text, tokenizer, model):
    import torch

    clean = text.strip()

    if not clean:
        return text

    inputs = tokenizer(
        clean,
        return_tensors="pt",
        truncation=True,
        max_length=256
    )

    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_length=256,
            num_beams=1,
            do_sample=False
        )

    restored = tokenizer.decode(
        output[0],
        skip_special_tokens=True
    )

    return restored.strip()


def restore_diacritics_text(text):
    tokenizer, model = get_diacritic_model()

    output_lines = []

    for line in text.split("\n"):

        if not line.strip():
            output_lines.append("")
            continue

        sentence_parts = re.split(
            r"(?<=[.!?])\s+",
            line.strip()
        )

        restored_sentences = []

        for sentence in sentence_parts:

            chunks = split_long_sentence(sentence)

            restored_chunks = []

            for chunk in chunks:
                restored_chunks.append(
                    restore_diacritics_piece(
                        chunk,
                        tokenizer,
                        model
                    )
                )

            restored_sentences.append(
                " ".join(restored_chunks)
            )

        output_lines.append(
            " ".join(restored_sentences)
        )

    return "\n".join(output_lines)


@app.post("/api/text/diacritics")
def add_diacritics(data: TextRequest):

    text = data.text.strip()

    if not text:
        raise HTTPException(
            status_code=400,
            detail="Chưa có văn bản để thêm dấu."
        )

    try:
        restored = restore_diacritics_text(
            data.text
        )

        return {
            "text": restored,
            "model": DIACRITIC_MODEL_ID
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Không thể chạy chức năng thêm dấu. "
                "Vui lòng kiểm tra model hoặc kết nối mạng."
            )
        ) from exc
