# AIStudio Folder Organisation — Design Spec
**Date:** 2026-05-26

---

## Goal

Consolidate all AI projects and tools from their scattered locations on `D:\` into a single, well-structured root at `D:\AIStudio\`. Prevent the mess from returning with a small set of naming conventions.

---

## Proposed Structure

```
D:\AIStudio\
├── Apps\           ← everything you build and ship (git-tracked, one folder per project)
├── Infrastructure\ ← AI tools you run locally (models, n8n, ComfyUI, scripts)
└── Scratch\        ← temp files, test output, experiments — never committed
```

Non-AI folders on `D:\` (`Business Folder`, `College`, `Music`, `Clio PDF files`, `Paddie`, `eCollege`) are **not touched**.

---

## Migration Map

### Apps\

| From (current location) | To (new location) | Notes |
|---|---|---|
| `D:\AIVideoStudio` | `AIStudio\Apps\AIVideoStudio` | Move as-is |
| `D:\AlBal` | `AIStudio\Apps\AlBal` | Move as-is |
| `D:\My_Apps\Anchor_v1` | `AIStudio\Apps\Anchor` | Drop `_v1` suffix |
| `D:\AudioMasterApp` | `AIStudio\Apps\AudioMasterApp` | Move as-is |
| `D:\ClearPath` + `D:\My_Apps\ClearPath Workplace` + `ClearPath Workplace_v2` + `ClearPathWorkplace_BUILD` + `ClearPathWorkplace_DIST` | `AIStudio\Apps\ClearPath` | Keep most complete copy; delete duplicates after confirming |
| `D:\CryptaVitae` + `D:\AI\Projects\CryptaVitae` + `D:\cryptavitea_files` | `AIStudio\Apps\CryptaVitae` | Keep most complete copy; delete duplicates after confirming |
| `D:\CryptaVitae-Mobile` | `AIStudio\Apps\CryptaVitae-Mobile` | Move as-is |
| `D:\cryptavitae-website` | `AIStudio\Apps\CryptaVitae-Website` | Rename for consistency |
| `D:\My_Apps\crypto-price-tracker` | `AIStudio\Apps\crypto-price-tracker` | Move as-is |
| `D:\My_Apps\form_app` | `AIStudio\Apps\form_app` | Move as-is |
| `D:\meavita` + `D:\My_Apps\meavita` + `D:\My_Apps\MeaVita_v1` | `AIStudio\Apps\MeaVita` | Keep most complete copy; delete duplicates after confirming |
| `D:\Poms MES` | `AIStudio\Apps\PomsMES` | Remove space in name |
| `D:\VoiceProject` | `AIStudio\Apps\VoiceProject` | Move as-is |
| `D:\My_Apps\WinHunt` + `WinHunt_V2` | `AIStudio\Apps\WinHunt` | Keep V2; delete V1 after confirming |

### Infrastructure\

| From | To | Notes |
|---|---|---|
| `D:\Local_AI_Models` | `AIStudio\Infrastructure\LocalModels` | Move as-is |
| `D:\n8n` | `AIStudio\Infrastructure\n8n` | Move as-is |
| `D:\ComfyUI workflow backups` | `AIStudio\Infrastructure\ComfyUI` | Move as-is |
| `D:\AI\Scripts` | `AIStudio\Infrastructure\Scripts` | Move as-is |
| `D:\AI\Workflows` | `AIStudio\Infrastructure\Workflows` | Move as-is |
| `D:\AI\Models` | `AIStudio\Infrastructure\LocalModels` | Merge with Local_AI_Models |
| `D:\AI\Input`, `D:\AI\Outputs`, `D:\AI\Archives` | Review contents before moving | May contain project-specific files |

### Scratch\

| From | Action |
|---|---|
| `D:\pytest_*.txt` (×10 files) | Move to `AIStudio\Scratch\` or delete |
| `D:\pt1.txt` – `D:\pt6.txt` | Move to `AIStudio\Scratch\` or delete |
| `D:\test_output.txt` | Move to `AIStudio\Scratch\` or delete |
| `D:\tmp\` | Move to `AIStudio\Scratch\tmp\` |
| `D:\New folder` | Delete if empty |
| `D:\My_Apps\MeaVita_v1.zip`, `D:\My_Apps\meavita architecture.txt`, `D:\My_Apps\MeaVita_Pro.txt` | Review — move to MeaVita project or delete |

---

## Conventions (to prevent recurrence)

1. **New projects always created inside `AIStudio\Apps\` or `AIStudio\Infrastructure\`** — never at `D:\` root
2. **No version suffixes in folder names** — `Apps\ClearPath\` not `ClearPath_v2\`. Git is the version history
3. **No spaces in folder names** — use `CamelCase` or `kebab-case`
4. **Temp/test output files → `Scratch\`** — never dumped at drive root or inside a project folder
5. **New AI tools/models/workflows → `Infrastructure\`** — never at drive root

---

## Duplicate Consolidation Warning

Before deleting any duplicate, open both copies and confirm:
- Which has the most recent commits / most up-to-date code
- Which has files the other doesn't

Projects requiring manual review before deletion:
- **ClearPath** — 4 versions; keep the most complete
- **MeaVita** — 3 versions; keep the most complete
- **CryptaVitae** — 2 copies (root + AI\Projects); keep root version (it has the full project)

---

## Out of Scope

- Reorganising the contents of individual projects
- Setting up GitHub remotes for projects that don't have one yet
- Migrating non-AI folders (`Business Folder`, `College`, etc.)
