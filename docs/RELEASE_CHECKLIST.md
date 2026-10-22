# Release checklist

Nothing here is published automatically. **Do not upload to PyPI/GitHub or register names without an explicit decision.**

## 1. Build

```bash
pip install pyinstaller ".[ui]"
winget install --id JRSoftware.InnoSetup -e --scope user   # once; or set ISCC=<path to ISCC.exe>
python tools/render_readme.py       # READMEs are generated from docs/readme/*.tmpl and fakehw/branding.py
python tools/build_exe.py           # add --no-installer to skip Inno Setup
```

Result in `dist/`:

| File | What it is |
|---|---|
| `fakehw/` | program folder: `fakehw.exe` (console), `FakeHWDetector.exe` (window), `_internal/`, READMEs |
| `FakeHWDetector-<version>-portable.zip` | the same folder plus `portable.txt`: settings and kb cache go to `data/` next to the exe |
| `FakeHWDetector-<version>-setup.exe` | Inno Setup installer (`packaging/installer.iss`): per-user by default, no admin rights, Start menu shortcut, uninstaller; English/Russian wizard |

The installer never contains `portable.txt`, so installed copies keep using `%APPDATA%` / `%LOCALAPPDATA%`.
The `AppId` in `installer.iss` identifies the installation for upgrades: never change it.

Status on the developer machine (Windows 11 25H2, Python 3.15, PySide6-Essentials 6.12, PyInstaller 6.22.3,
Inno Setup 6.7.3): the build succeeds (folder about 113 MB, portable zip 49 MB, installer 33 MB); `fakehw.exe selftest`
works from another directory with a minimal `PATH`; the portable copy writes `data\settings.json` next to the exe and
nothing to `%APPDATA%`; a silent per-user install (`/VERYSILENT /CURRENTUSER`) creates the Start menu shortcut and the
"Installed apps" entry, the installed window starts, and the silent uninstall removes all of it.

On Python 3.15 PyYAML has no wheel yet: install it with `PYYAML_FORCE_LIBYAML=0` (pure Python). `PySide6-Essentials`
is enough for the app (QtCore/QtGui/QtWidgets) and avoids the large WebEngine download of the full `PySide6`.

## 2. Clean Windows 11 VM (NOT done yet - needs a VM)

Copy the whole `dist/fakehw` folder to a fresh Windows 11 VM with no Python installed, then:

- [ ] `fakehw.exe --version` prints the product name and version.
- [ ] `fakehw.exe selftest` prints OK for all five checks.
- [ ] `fakehw.exe scan --format md -o report.md` finishes without errors and the file opens.
  - Expected in a VM: virtualization shown as "likely", CPU/GPU findings with reduced confidence, GPU rows with "could not verify" entries.
- [ ] `FakeHWDetector.exe` opens the window; run the manual UI list in [UI_CHECKLIST.md](UI_CHECKLIST.md).
- [ ] No "missing DLL" or VC++ runtime error dialogs (if one appears, note which DLL).
- [ ] Windows SmartScreen / antivirus behaviour noted (the build is unsigned; raw CPUID uses a small executable stub).
- [ ] `fakehw.exe kb update` on a machine with internet updates the caches (optional; the only network use).
- [ ] Installer: runs without an admin prompt, installs to `%LOCALAPPDATA%\Programs\FakeHWDetector`, the Start menu
  shortcut opens the window; installing a second time upgrades in place; "Apps > Installed apps" uninstalls it.
- [ ] Portable: unpack the zip to a USB stick, run `FakeHWDetector.exe`, switch the language: `data\settings.json`
  appears next to the exe and nothing is written to `%APPDATA%\FakeHWDetector`.

## 3. Before the first publication

- [ ] Choose the project license (not chosen yet) and add a `LICENSE` file; bundled pci.ids/usb.ids are GPL-2+ or 3-clause BSD.
- [ ] Name checklist in [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md): PyPI, GitHub, domains (.com, .app, .dev), trademark - nothing has been checked.
- [ ] Re-read the README limitations and the comparison paragraph about GPU-Z / HWiNFO (written from the author's brief, not verified against their current features).
- [ ] Code signing certificate for the executables (optional).
