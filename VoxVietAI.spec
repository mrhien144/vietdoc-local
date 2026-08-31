# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, copy_metadata


datas = [
    ("index.html", "."),
    ("logo-voxviet.png", "."),
    ("voxviet-ai.ico", "."),
    ("voxviet-icon.png", "."),
]

binaries = []
hiddenimports = []


def add_package(package_name):
    package_datas, package_binaries, package_hiddenimports = collect_all(
        package_name
    )

    datas.extend(package_datas)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_hiddenimports)


# Cac goi can thu thap day du cho TTS va ung dung desktop.
add_package("vieneu")
add_package("sea_g2p")
add_package("kokoro")
add_package("imageio_ffmpeg")
add_package("webview")
add_package("language_tags")
add_package("espeakng_loader")
add_package("en_core_web_sm")
datas += copy_metadata("en_core_web_sm")
add_package("misaki")


a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "gradio",
        "gradio_client",
        "hf_gradio",
        "pandas",

    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)


exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VoxVietAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon="voxviet-ai.ico",
)


coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VoxVietAI",
)
