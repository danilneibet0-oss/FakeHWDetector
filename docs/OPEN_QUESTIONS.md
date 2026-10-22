# Open questions

## Decisions taken (iteration 1)
- Python package is `fakehw` (spec mentioned both `hwcheck/` and `fakehw`; the latter matches the CLI and PyPI name). Not explicitly confirmed — revert if unwanted.
- Interface languages: English (default) and Russian, selectable via `fakehw config --language ru` / `--lang`; GUI selector comes in iteration 7.
- Rule `condition` is a safe mini-DSL (`and`/`or`/`not`, `== != < <= > >= in`, literals, lists, signal names), parsed with `ast` against a whitelist, never `eval`.

## Knowledge base (iteration 2)
- Bundled snapshots: `fakehw/kb/data/pci.ids` (v2026.10.20) and `usb.ids` (v2026.06.26), downloaded 2026-10-21 with the user's approval; source URL, version and SHA-256 in `snapshot.json`. Licensing: pci.ids is BSD-3 / GPL-2+ dual, usb.ids is GPL-2+ / BSD-3 (stated in the file headers) - confirm compatibility before publishing the package.
- `linux-usb.org` serves `usb.ids` over plain HTTP only (HTTPS certificate does not match the host). The updater therefore validates by parsing (version header + vendors) and records the SHA-256, but cannot authenticate the source. Consider a pinned HTTPS mirror - needs a decision.
- Upstream `usb.ids` has one non-UTF-8 byte (HID table, unused) and lines with 3 spaces after an ID; parser decodes with replacement and tolerates extra spaces. Reported as `parse_errors == 0` on the full snapshots.
- `usb.ids` itself lists an entry "Counterfeit flash drive [Kingston]" (vendor 0001, product 7778). Candidate source for the iteration 4 USB rule - needs a decision whether upstream-marked entries count as a signal.
- `jedec.py` and `cpu_tables.py` are deferred: they need a sourced data file (JEDEC JEP106 list, CPU family/model tables) - not invented.

## Collectors (iteration 3)
- PCI/USB data comes from `Win32_PnPEntity` via PowerShell `Get-CimInstance` (no `wmi`/`pywin32` dependency). Needs `powershell.exe`; if missing, collectors return a record with `errors` instead of raising. Linux/macOS are not supported.
- CPU: raw CPUID through a 24-byte x64 stub in executable memory (`VirtualAlloc`/`VirtualProtect`, no driver, no admin). Some antivirus products may dislike runtime-executable memory - unverified. ARM64 Windows falls back to the registry (family/model/stepping only, hypervisor = "unknown"); untested on real ARM hardware.
- The CPUID hypervisor bit is **set on this physical machine** (vendor "Microsoft Hv"): Windows with VBS/Hyper-V runs the host as the root partition. A naive "hypervisor present => virtual machine" rule would wrongly lower confidence on such hosts. Need a reliable way to tell the root partition from a guest (e.g. Hyper-V CPUID leaf 0x40000003 privileges, Win32_ComputerSystem model/manufacturer) before iteration 4 uses it. Not guessed here.
- Serial numbers are hashed as `sha256:<first 16 hex>` (unsalted). Short serials are brute-forceable; consider a per-report salt if reports are shared publicly.
- Windows-generated child nodes (`&MI_xx`, `&LAMPARRAY`, ...) are skipped; only the parent USB device is reported. USB devices with a failed descriptor request (VID_0000) are reported with an error and no usable IDs.
- Fixtures: `tests/fixtures/collectors/local_*.json` are real dumps of the developer machine (USB serials replaced); `edited_*` are hand-edited copies and say so in their `note`. Regenerate with `python tools/capture_fixtures.py`.

## Rule engine (iteration 4)
- **Hyper-V ambiguity resolved conservatively:** vendor "Microsoft Hv" is `ambiguous` (confidence x0.8) rather than "virtual machine", because the developer's physical host shows it too. A real way to tell root partition from guest is still unknown (candidates: Hyper-V CPUID leaf 0x40000003 privilege bits, `Win32_ComputerSystem` model) - not guessed.
- **`cpu_arch.yaml` has a single entry** (family 6 / model 167), backed by evidence observed on the developer machine. The microarchitecture name and the Xeon E-2300 pattern are from public naming, unverified. `cpu.brand_arch_mismatch` returns "could not verify" for every other CPU. To grow coverage, add entries *with sources* (e.g. Linux `intel-family.h`, AMD PPR documents) - downloading them needs a decision/approval.
- Score thresholds (0.25 / 0.6), rule weights and virtualization factors are initial design values, not calibrated on real counterfeit samples.
- `kb.entry_marked_counterfeit` relies on upstream entry text; usb.ids has 4 such USB entries and pci.ids 1 (`10DE:1404 GeForce GTX 960 FAKE`). Matching is by the words "counterfeit"/"fake".
- Live scan on the developer machine: 0 LIKELY_FAKE; 3 Intel chipset functions (8086:4C53, 4C01, 4C11) are absent from pci.ids -> `pci.device_not_in_db` INFO (score 0.2).
- Iteration 3's USB spoof checks (VID/PID of known counterfeit beyond what upstream marks) have no curated list; add `kb/data` entries with sources if a trustworthy list is found.

## Memory and storage (iteration 5)
- **No JEP106 table:** the manufacturer-name vs JEDEC-code consistency check and "unknown manufacturer code" need a sourced JEDEC list. JEDEC publishes JEP106 as a (licensed) standard; no table is shipped. Only the table-free parity check is implemented. Needs a decision on a redistributable source.
- Win32_PhysicalMemory often gives the manufacturer as a name (as on the developer machine), so `ram.jedec_parity_invalid` is "could not verify" there. The raw SPD would give the code but needs a kernel driver (not used) - the SPD plugin exists only as an interface (`--enable-spd` with an injected reader); no reader is bundled and the DDR4 offsets (320-321, 325-328, 329-348) are from memory of the JEDEC annex and tested only on a constructed image.
- NVMe Identify (IOCTL_STORAGE_QUERY_PROPERTY, StorageAdapterProtocolSpecificProperty) works without admin rights on the developer machine (Windows 11). Struct layout was verified there only; other Windows builds are untested.
- SATA IDENTIFY (IOCTL_ATA_PASS_THROUGH, struct layout written from the Windows SDK as remembered) and SMART/StorageReliabilityCounter need administrator rights. The non-elevated path (drive flagged `privilege_needed`) is verified on real SATA disks; the elevated path is **untested**. SMART values are not collected at all yet.
- Win32_DiskDrive does not expose the identity of USB-bridge drives (bridges can lie): they are not probed. Fake-capacity flash drives cannot be detected without a full write test (f3/H2testw), which this read-only tool does not do.
- Discovered on real hardware: Windows reports an NVMe disk "serial" as the namespace EUI-64, not the controller serial from Identify - serial comparison rule dropped.
- Rule count is now 13 (target: at least 12). GPU physical checks (iteration 6) will add more.

## GPU physical checks (iteration 6)
- **DXGI is read through raw COM vtable calls** (`CreateDXGIFactory1`, `IDXGIFactory1::EnumAdapters1` = slot 12, `IDXGIAdapter1::GetDesc1` = slot 10); verified on the developer machine (Windows 11) only. NVML structure offsets (`nvmlPciInfo_t`: device id at +28) were verified there too - the first guess was wrong, found by the live probe.
- **`gpu_refs.yaml` has one entry** (10DE:2486, observed on the developer machine). Every other GPU gets "could not verify" from the three reference rules. Specs must come from a sourced list (vendor spec pages, TechPowerUp-like databases); needs a decision on source/licence.
- **NVML max PCIe values are limited by the slot as well as the card**, so only "above the chip capability" is treated as suspicious. A card in an older slot is normal.
- AMD/Intel GPUs get DXGI data only (no bus width / PCIe link): the NVML-based rules are "could not verify" for them. ADL/Intel APIs not implemented.
- The DXGI-vs-NVML VRAM tolerance (10%) and reference tolerance (-6%/+2%) are initial values, based on 2% observed on one card.
- Rule count is now 20.

## UI (iteration 7)
- PySide6 6.12 installs and runs on Python 3.14 here (Windows 11); PyInstaller on 3.14 is still unchecked (iteration 8).
- The window is covered by automated tests on the Qt `offscreen` platform and was inspected through `QWidget.grab()` screenshots on the real `windows` platform with a full scan (29 devices, no red rows). The manual checklist `docs/UI_CHECKLIST.md` has **not** been executed by a person yet.
- Windows-provided device names (e.g. "Standard SATA AHCI Controller") are shown in the Windows display language, not translated by the app.
- Dark/light: level colours are light pastels with dark text so rows stay readable in a dark system theme; no theme switcher.
- The language switch re-evaluates the rules for the existing scan (no rescan). The re-evaluation runs on the UI thread (about a second the first time because the pci.ids database is parsed once).
- Export in the GUI is JSON only; the Markdown report arrives with iteration 8.

## Export and packaging (iteration 8)
- **Clean Windows 11 VM run not done** (no VM available here). Done instead: PyInstaller build on the developer machine, then `selftest`, `rules`, `kb status`, a full `scan --format md` and the windowed GUI executable started from another directory with `PATH` reduced to the Windows folders (no Python, no virtualenv). Steps for the VM are in `docs/RELEASE_CHECKLIST.md`.
- The build is about 140 MB (PySide6) and unsigned; antivirus/SmartScreen behaviour (raw CPUID stub, unsigned exe) is unknown. PyInstaller 6.22 worked with Python 3.14 here.
- Markdown/JSON reports: same input gives byte-identical output (timestamps come from the scan); finding texts are generated in the language used for the assessment, so export in another language by re-assessing first (the GUI does this on language change).
- README (EN/RU) is generated from templates with the branding values; a test fails when the files are stale. The paragraph on GPU-Z / HWiNFO follows the author's brief (they mainly flag GPU counterfeits) and was not checked against their current features.
- The project license is not chosen; bundled pci.ids/usb.ids are GPL-2+ or 3-clause BSD.
- MVP acceptance on the developer machine: 6 device classes collected, 20 rules with fixtures, 351 tests green, 29 devices all Information, 0 LIKELY_FAKE, two consecutive scans identical apart from timestamps.

## Open
- Python 3.14 is installed locally (py launcher); the spec targets 3.11+. PySide6 / PyInstaller wheel availability for 3.14 is unverified — check before iterations 7-8.

## Name checklist (do NOT publish anything before explicit approval)
Not yet checked by the assistant:
- [ ] PyPI: `fakehwdetector`
- [ ] GitHub: org/user and repository name
- [ ] Domains: `.com`, `.app`, `.dev`
- [ ] Trademark search (relevant jurisdictions)
