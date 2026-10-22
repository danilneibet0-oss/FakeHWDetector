# Rules

Each rule is a YAML file in `fakehw/rules/rules/` (or a directory passed via `--dir`).

| Field | Meaning |
|---|---|
| `id` | unique, e.g. `pci.dev_not_in_db` |
| `applies_to` | device classes: cpu, gpu, ram, usb, storage, pci |
| `signals` | signal names the condition may use |
| `condition` | safe expression over signals |
| `weight` | 0..1 contribution to the weighted device score |
| `false_positive_risk` | low / medium / high |
| `explanation`, `recommendation` | text; plain string = English, or `{en: ..., ru: ...}` |

Every rule must be documented below with a "norm / suspicious" table and have positive, negative and borderline fixtures.

<!-- Rule sections are added together with the rules (iteration 4+). -->

## Scoring (iteration 4 decisions)
- Fired rule contribution = `weight x confidence`. Device score = sum of contributions, capped at 1.0 (weighted sum, **not** the worst rule).
- Levels: score < 0.25 `INFO`, 0.25-0.59 `SUSPICIOUS`, >= 0.6 `LIKELY_FAKE`. No fired rule: `INFO` if at least one rule could be evaluated, else `UNVERIFIED`.
- A rule whose signals are unknown yields an `UNVERIFIED` finding - never a guess.
- Virtualization (from the CPU record) lowers confidence of **all CPU and GPU rules**: `likely` (hypervisor bit set, vendor is not Hyper-V) x0.5; `ambiguous` (vendor "Microsoft Hv": a VM guest *or* a Windows host with VBS/Hyper-V, as on the developer machine) x0.8; `none`/`unknown` x1.0.
- Every finding text states the signals it rests on and the false-alarm disclaimer.

## Rules

### pci.vendor_not_in_db (weight 0.4, false-positive risk: medium)
| Norm | Suspicious |
|---|---|
| vendor ID listed in pci.ids | vendor ID not listed |

### pci.device_not_in_db (0.2, medium)
| Norm | Suspicious |
|---|---|
| vendor and device ID both listed | known vendor, device ID not listed under it. Weak alone: new/rare devices and chipset blocks are often missing (3 Intel chipset functions on the developer machine) |

### pci.subsys_vendor_unknown (0.2, medium)
| Norm | Suspicious |
|---|---|
| no subsystem (0000:0000) or subsystem vendor listed | subsystem vendor ID set but not listed. Unknown if DeviceID has no SUBSYS part |

### cpu.brand_vendor_mismatch (0.7, low)
| Norm | Suspicious |
|---|---|
| brand names the CPUID vendor (Intel <-> GenuineIntel, AMD <-> AuthenticAMD) | brand names the other vendor. Unknown if the brand names neither (e.g. Hygon) |

### cpu.brand_arch_mismatch (0.45, high)
| Norm | Suspicious |
|---|---|
| brand matches a pattern allowed for the signature in `kb/data/cpu_arch.yaml` | signature is in the table, brand fits none of its patterns. Unknown if the signature is not in the table (currently only one entry) |

### kb.entry_marked_counterfeit (0.65, medium)
| Norm | Suspicious |
|---|---|
| usb.ids/pci.ids entry for the exact ID is not described as counterfeit | entry name contains the word "counterfeit" or "fake" (word match; "clone" is deliberately not matched). The same ID can also be used by genuine devices |

Cases: `tests/fixtures/cases/<rule id>.yaml` (positive / negative / borderline / unverified); `tests/test_rule_cases.py` enforces that each rule has the first three.

### ram.jedec_parity_invalid (0.3, medium)
| Norm | Suspicious |
|---|---|
| manufacturer code printed as 4 hex digits (JEDEC JEP106 bank byte + ID byte) has odd parity in both bytes, e.g. `802C` | a byte with even parity, e.g. `802D`, `0000`, `FFFF`. Unknown if the BIOS reports a name (like "Kingston") instead of a code |

### ram.part_number_placeholder (0.2, high)
| Norm | Suspicious |
|---|---|
| any non-placeholder part number (padding spaces are trimmed) | empty or a firmware placeholder word (Unknown, N/A, Not Specified, To Be Filled By O.E.M., ...). Common on OEM laptops |

### ram.serial_placeholder / storage.serial_placeholder (0.15 / 0.2, high)
| Norm | Suspicious |
|---|---|
| serial_shape `normal` (a real serial may contain zeros, e.g. `0CD214F8`) | empty, all zeros, all F, 4+ repeated characters, or a placeholder word |

### storage.nvme_vid_unregistered (0.4, medium)
| Norm | Suspicious |
|---|---|
| NVMe Identify VID registered in pci.ids | VID absent from pci.ids. Unknown for non-NVMe drives and when Identify cannot be read |

### storage.identify_model_mismatch (0.35, medium)
| Norm | Suspicious |
|---|---|
| Windows model equals the Identify model after removing punctuation, or one contains the other (truncation) | models differ. Needs Identify data: NVMe works without admin rights, SATA needs them |

### storage.size_exceeds_nvme_capacity (0.5, low)
| Norm | Suspicious |
|---|---|
| Windows size <= TNVMCAP (total NVM capacity from Identify) | Windows size > TNVMCAP. Unknown when the drive reports TNVMCAP = 0 |

Serial numbers are never compared with Identify serials: Windows reports the namespace EUI-64 as an NVMe disk serial (verified on the developer machine), so the comparison would give false alarms.

### gpu.vram_dxgi_nvml_mismatch (0.5, low)
| Norm | Suspicious |
|---|---|
| DXGI dedicated VRAM and NVML total memory within 10% (driver reserves 2-6%; 8024 vs 8192 MiB on the developer machine) | the two APIs differ by more than 10%. Unknown when only one API answers (non-NVIDIA GPU) |

### gpu.mem_bus_width_invalid (0.35, medium)
| Norm | Suspicious |
|---|---|
| bus width is a positive multiple of 32 bits | any other width. Unknown without NVML |

### gpu.pcie_link_inconsistent (0.4, low)
| Norm | Suspicious |
|---|---|
| current generation/width <= maximum; idle down-training (e.g. gen 1 x4) is normal | current above the maximum the device itself reports |

### gpu.vram_reference_mismatch (0.5, medium)
| Norm | Suspicious |
|---|---|
| VRAM (NVML total, else DXGI) is within -6%/+2% of a size listed for the PCI device ID in `kb/data/gpu_refs.yaml` | a size that is not listed. Unknown when the device ID has no reference entry (currently one entry) |

### gpu.bus_width_reference_mismatch (0.5, medium)
| Norm | Suspicious |
|---|---|
| bus width listed for the device ID | a different width (cut-down chip under another model ID). Unknown without a reference entry |

### gpu.pcie_link_exceeds_reference (0.35, medium)
| Norm | Suspicious |
|---|---|
| maximum link gen/width <= chip capability; lower is normal (NVML reports the limit of card AND slot) | maximum above the chip capability. Unknown without a reference entry |

### gpu.name_pci_ids_mismatch (0.45, medium)
| Norm | Suspicious |
|---|---|
| DXGI/NVML adapter name contains (or is contained in) the bracketed marketing name pci.ids lists for the device ID, e.g. `GA104 [GeForce RTX 3060 Ti]` | the names are different products. Unknown if the device ID is not in pci.ids or no name is reported |
