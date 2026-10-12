# -*- mode: python ; coding: utf-8 -*-
"""Receita do PyInstaller do EditDoc. Quem roda e' o build.bat.

    .venv\\Scripts\\python.exe -m PyInstaller --noconfirm --clean EditDoc.spec

EDITDOC_UM_ARQUIVO=1 gera o executavel unico (build.bat umarquivo); sem a
variavel, gera a pasta one-dir, que e' o que se entrega em ZIP.
"""

import os
import pathlib

import PySide6
from PyInstaller.utils.hooks import collect_data_files

RAIZ = pathlib.Path(SPECPATH)
UM_ARQUIVO = os.environ.get("EDITDOC_UM_ARQUIVO") == "1"
TRADUCOES = pathlib.Path(PySide6.__file__).parent / "translations"
ICONE = RAIZ / "editdoc" / "recursos" / "icone.ico"

# Modulos que o EditDoc nao usa. Cada um tirado daqui precisa passar na
# autoverificacao do .exe, que o build.bat roda logo depois.
EXCLUDES = [
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.Qt3DCore",
]

# DLLs que sobram do PySide6 para um editor de widgets basicos.
DLLS_DESNECESSARIAS = {
    "opengl32sw.dll",
    "qt6pdf.dll",
    "qt6pdfwidgets.dll",
    "qt6quick.dll",
    "qt6qml.dll",
    "qt6qmlmodels.dll",
    "qt6multimedia.dll",
    "qt6sql.dll",
}

for nome in ("qtbase_pt_BR.qm", "qt_pt_BR.qm"):
    if not (TRADUCOES / nome).is_file():
        raise SystemExit(f"ERRO: {nome} nao esta em {TRADUCOES}")
if not ICONE.is_file():
    raise SystemExit(f"ERRO: {ICONE} nao existe. Rode ferramentas/gerar_icone.py.")

datas = [
    (str(RAIZ / "editdoc" / "recursos"), "editdoc/recursos"),
    (str(TRADUCOES / "qtbase_pt_BR.qm"), "traducoes"),
    (str(TRADUCOES / "qt_pt_BR.qm"), "traducoes"),
]
# O python-docx le um template interno; sem ele o .exe nao cria nem le .docx.
datas += collect_data_files("docx")

a = Analysis(
    [str(RAIZ / "app.py")],
    pathex=[str(RAIZ)],
    binaries=[],
    datas=datas,
    hiddenimports=["lxml.etree", "lxml._elementpath", "docx"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=1,
)

_descartar = {nome.lower() for nome in DLLS_DESNECESSARIAS}
a.binaries = [b for b in a.binaries
              if os.path.basename(b[0]).lower() not in _descartar]

pyz = PYZ(a.pure)

if UM_ARQUIVO:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="EditDoc",
        icon=str(ICONE),
        version=str(RAIZ / "versao.txt"),
        manifest=str(RAIZ / "editdoc.manifest"),
        console=False,
        upx=False,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="EditDoc",
        icon=str(ICONE),
        version=str(RAIZ / "versao.txt"),
        manifest=str(RAIZ / "editdoc.manifest"),
        console=False,
        upx=False,
    )
    coleta = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="EditDoc",
    )
