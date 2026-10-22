# Manual UI check list (iteration 7)

Run on a real Windows 11 machine, without administrator rights unless stated. Start with `fakehw gui`
(needs `pip install fakehwdetector[ui]`).

## 1. Start-up
- [ ] The window title shows the product name and the tagline "Hardware Authenticity Checker".
- [ ] The status bar says "Ready. Press Scan." (or the Russian equivalent if Russian was chosen last time).
- [ ] The details panel asks to select a device; **Export...** is disabled.

## 2. Scan
- [ ] Press **Scan**: the button becomes disabled and reads "Scanning..."; the window stays responsive (move/resize it).
- [ ] After a few seconds the table fills; the status bar shows the device count and how many have findings.
- [ ] The permanent status text shows the pci.ids / usb.ids versions and the virtualization state.
  - On a Windows host with Hyper-V/VBS the state is "possible (Hyper-V ...)" - expected, not an error.
- [ ] Every class you own appears: CPU, GPU, Memory, USB, Storage, PCI device.
- [ ] Rows are coloured **and** carry a symbol: ● Information (green), ▲ Suspicious (amber), ✖ Likely counterfeit (red), ? Could not verify (grey).
- [ ] Most serious devices are listed first; click a column header to re-sort.
- [ ] **No row is red (✖) on a genuine machine.** If one is, open its details and read which rule fired - then report it as a false positive.
- [ ] SATA drives show "needs administrator rights" in Notes (without admin rights); the NVMe drive does not.

## 3. Details panel
- [ ] Select a row: the panel shows name, class, source, verdict with score, "Triggered rules", identifiers, strings.
- [ ] A triggered rule shows its id, level, explanation (which names the signals used and the false-alarm reminder), evidence and recommendation.
- [ ] "Could not verify" lists the rules that lacked data.
- [ ] Problems (errors, missing rights) are listed at the bottom.
- [ ] Device strings that contain `<` or `&` are shown literally (no broken layout).

## 4. Filters, serials
- [ ] **Only devices with findings** keeps rows that triggered a rule or are not plain Information; unticking restores all rows.
- [ ] Serial numbers appear as `sha256:...` by default. Tick **Show serial numbers**, scan again: real serials appear (do this only for your own use; do not share such a report).

## 5. Language
- [ ] Switch the language combo to Русский: buttons, headers, class names, level names, status text and the open details panel change at once; no new scan happens.
- [ ] Finding texts (rule explanations) are in Russian after the switch.
- [ ] Close and reopen the application: the chosen language is remembered.

## 6. Export
- [ ] **Export...** opens a save dialog; choose a file name: the status bar says "Saved: ...".
- [ ] Cancel the dialog: nothing is written.
- [ ] The saved JSON contains `devices`, `findings`, `assessments`, `kb_versions`; serial numbers are hashed unless the box was ticked.

## 7. About this computer
- [ ] The window has two tabs, **Device check** and **About this computer**; the language selector sits at the right of the tab bar.
- [ ] Open **About this computer**: "Collecting information..." appears briefly, then sections for the operating system,
  computer, motherboard and BIOS, processor, memory (with every slot), video adapter, drives and volumes.
- [ ] Values match Windows' own "System information" (`msinfo32`): OS version and build, CPU, installed memory, drive models.
- [ ] Video memory is shown only when DXGI reports it (never the 4 GB-capped WMI value).
- [ ] No serial numbers, UUIDs or MAC addresses appear anywhere on the tab.
- [ ] **Copy** puts a plain-text version on the clipboard and the status bar says "Copied to the clipboard".
- [ ] **Refresh** collects again; switching tabs back and forth does not.
- [ ] Switch the language: the tab is re-labelled at once (sizes use "ГБ" and a decimal comma in Russian).

## 8. Failure handling
- [ ] Run the app in an environment without an NVIDIA driver (for example a VM): the scan still completes and the GPU row lists "could not verify" rules instead of failing.
- [ ] A scan error never crashes the window; the status bar shows "Scan failed: ...".
