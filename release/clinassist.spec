# PyInstaller recipe: builds the application folder that the installer copies (ADR-012).
#
#   pyinstaller --noconfirm --clean release/clinassist.spec --distpath build/dist --workpath build/work
#
# One folder, not one file: a single .exe would unpack about 600 MB to a temporary folder at every
# start. Two programs share the folder:
#   ClinAssist.exe        the desktop application (no console window)
#   ClinAssist-check.exe  prints the start-up checks or verifies a bundle, for the installer and
#                         support staff (console window)
# The models are not inside; they come from the offline bundle (clinassist.bundle).

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH is set by PyInstaller

datas = (
    collect_data_files("spellchecker")  # the English dictionary for the merged-word check
    + collect_data_files("faster_whisper")  # the voice-activity model used to skip silence
    + collect_data_files("_sounddevice_data")  # PortAudio, the microphone library
    + [(str(ROOT / "scripts" / "airgap_firewall.ps1"), "scripts")]
)
binaries = collect_dynamic_libs("sqlcipher3") + collect_dynamic_libs("ctranslate2")

analysis = Analysis(  # noqa: F821
    [str(ROOT / "src" / "clinassist" / "ui" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    binaries=binaries,
    hiddenimports=[
        "clinassist.adapters.recorder",
        "clinassist.adapters.transcriber",
        "clinassist.startup",
        "clinassist.bundle",
        "sqlcipher3.dbapi2",
    ],
    excludes=["tkinter", "pytest", "matplotlib", "IPython"],
)
pyz = PYZ(analysis.pure)  # noqa: F821

app = EXE(  # noqa: F821
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="ClinAssist",
    console=False,
)
check = EXE(  # noqa: F821
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="ClinAssist-check",
    console=True,
)
COLLECT(  # noqa: F821
    app,
    check,
    analysis.binaries,
    analysis.datas,
    name="ClinAssist",
)
