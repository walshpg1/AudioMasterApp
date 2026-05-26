# AIStudio Folder Reorganisation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all AI projects from their scattered locations on `D:\` into a single clean `D:\AIStudio\` root.

**Architecture:** Create the three-folder root (`Apps\`, `Infrastructure\`, `Scratch\`), resolve duplicates by comparing file dates, then move each project to its new home. Non-AI folders on `D:\` are untouched.

**Tech Stack:** PowerShell (Move-Item, Get-ChildItem), Windows file system.

---

## ⚠ Before You Start

- **Python `.venv` folders** will break after a move (they contain hardcoded absolute paths). After moving any Python project, delete its `.venv` and recreate it: `python -m venv .venv && pip install -r requirements.txt`
- **Do not move `D:\AudioMasterApp` until last** — if Claude Code is open there, close it first and reopen at the new path after the move.
- Run all commands in **PowerShell** (not CMD).

---

## Task 1: Create the AIStudio folder structure

- [ ] **Step 1: Create the three root folders**

```powershell
New-Item -ItemType Directory -Path "D:\AIStudio\Apps"
New-Item -ItemType Directory -Path "D:\AIStudio\Infrastructure"
New-Item -ItemType Directory -Path "D:\AIStudio\Scratch"
```

- [ ] **Step 2: Verify they exist**

```powershell
Get-ChildItem D:\AIStudio
```

Expected output:
```
Mode    Name
----    ----
d----   Apps
d----   Infrastructure
d----   Scratch
```

---

## Task 2: Resolve ClearPath duplicates

There are multiple ClearPath-related folders. `D:\ClearPath` appears to be a *different* folder (it contains a Word doc, HTML, JSX, MP3 — not a Python app). Confirm before acting.

- [ ] **Step 1: Inspect each folder to identify what's in it**

```powershell
Get-ChildItem "D:\ClearPath" | Select-Object Name, LastWriteTime | Sort-Object LastWriteTime -Descending | Select-Object -First 10
Get-ChildItem "D:\My_Apps\ClearPath Workplace" | Select-Object Name, LastWriteTime | Sort-Object LastWriteTime -Descending | Select-Object -First 10
Get-ChildItem "D:\My_Apps\ClearPath Workplace_v2" | Select-Object Name, LastWriteTime | Sort-Object LastWriteTime -Descending | Select-Object -First 10
Get-ChildItem "D:\My_Apps\ClearPathWorkplace_BUILD" | Select-Object Name, LastWriteTime | Sort-Object LastWriteTime -Descending | Select-Object -First 10
```

- [ ] **Step 2: Check file counts to find the most complete copy**

```powershell
(Get-ChildItem "D:\My_Apps\ClearPath Workplace" -Recurse).Count
(Get-ChildItem "D:\My_Apps\ClearPath Workplace_v2" -Recurse).Count
(Get-ChildItem "D:\My_Apps\ClearPathWorkplace_BUILD" -Recurse).Count
```

The one with the highest count and most recent dates is your canonical version.

- [ ] **Step 3: Move the most complete ClearPath version to AIStudio**

Replace `<BEST>` with whichever folder won in Step 2 (e.g. `ClearPath Workplace_v2`):

```powershell
Move-Item "D:\My_Apps\<BEST>" "D:\AIStudio\Apps\ClearPath"
```

- [ ] **Step 4: Delete the remaining ClearPath duplicates (after confirming Step 3 succeeded)**

```powershell
# Only run these after confirming D:\AIStudio\Apps\ClearPath exists and looks right
Remove-Item -Recurse -Force "D:\My_Apps\ClearPath Workplace"       # if not already moved
Remove-Item -Recurse -Force "D:\My_Apps\ClearPath Workplace_v2"    # if not already moved
Remove-Item -Recurse -Force "D:\My_Apps\ClearPathWorkplace_BUILD"
Remove-Item -Recurse -Force "D:\My_Apps\ClearPathWorkplace_DIST"
```

- [ ] **Step 5: Handle `D:\ClearPath` separately**

If it contains non-app files (Word doc, MP3 etc.), it is NOT the ClearPath app. Move it somewhere appropriate (e.g. `D:\Business Folder`) or leave it. Do NOT delete without checking.

```powershell
Get-ChildItem "D:\ClearPath"   # confirm contents before acting
```

- [ ] **Step 6: Recreate .venv in the moved ClearPath project**

```powershell
Set-Location "D:\AIStudio\Apps\ClearPath"
Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

---

## Task 3: Resolve MeaVita duplicates

- [ ] **Step 1: Compare the two MeaVita copies**

```powershell
(Get-ChildItem "D:\meavita" -Recurse).Count
(Get-ChildItem "D:\My_Apps\meavita" -Recurse).Count
Get-ChildItem "D:\meavita" | Sort-Object LastWriteTime -Descending | Select-Object -First 5
Get-ChildItem "D:\My_Apps\meavita" | Sort-Object LastWriteTime -Descending | Select-Object -First 5
```

- [ ] **Step 2: Move the most complete copy to AIStudio**

```powershell
# Replace <BEST> with either "D:\meavita" or "D:\My_Apps\meavita"
Move-Item "<BEST>" "D:\AIStudio\Apps\MeaVita"
```

- [ ] **Step 3: Delete the remaining duplicate**

```powershell
# Only after confirming D:\AIStudio\Apps\MeaVita looks right
Remove-Item -Recurse -Force "D:\meavita"        # if not moved
Remove-Item -Recurse -Force "D:\My_Apps\meavita" # if not moved
Remove-Item -Recurse -Force "D:\My_Apps\MeaVita_v1"
```

- [ ] **Step 4: Review loose MeaVita files in My_Apps**

```powershell
# Review these — move to MeaVita project or delete
Get-Item "D:\My_Apps\MeaVita_v1.zip"
Get-Item "D:\My_Apps\meavita architecture.txt"
Get-Item "D:\My_Apps\MeaVita_Pro.txt"
```

Move any useful docs into the project:
```powershell
Move-Item "D:\My_Apps\meavita architecture.txt" "D:\AIStudio\Apps\MeaVita\"
Move-Item "D:\My_Apps\MeaVita_Pro.txt" "D:\AIStudio\Apps\MeaVita\"
Remove-Item "D:\My_Apps\MeaVita_v1.zip"   # delete the zip if the folder exists
```

- [ ] **Step 5: Recreate .venv**

```powershell
Set-Location "D:\AIStudio\Apps\MeaVita"
Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

---

## Task 4: Resolve CryptaVitae duplicates

`D:\CryptaVitae` is the main project (full structure confirmed). `D:\AI\Projects\CryptaVitae` and `D:\cryptavitea_files` are likely older copies.

- [ ] **Step 1: Confirm D:\CryptaVitae is the most complete**

```powershell
(Get-ChildItem "D:\CryptaVitae" -Recurse).Count
(Get-ChildItem "D:\AI\Projects\CryptaVitae" -Recurse).Count
(Get-ChildItem "D:\cryptavitea_files" -Recurse -ErrorAction SilentlyContinue).Count
```

- [ ] **Step 2: Move D:\CryptaVitae to AIStudio**

```powershell
Move-Item "D:\CryptaVitae" "D:\AIStudio\Apps\CryptaVitae"
```

- [ ] **Step 3: Move related CryptaVitae projects**

```powershell
Move-Item "D:\CryptaVitae-Mobile" "D:\AIStudio\Apps\CryptaVitae-Mobile"
Move-Item "D:\cryptavitae-website" "D:\AIStudio\Apps\CryptaVitae-Website"
```

- [ ] **Step 4: Delete the duplicate copies (after confirming Step 2 succeeded)**

```powershell
Remove-Item -Recurse -Force "D:\AI\Projects\CryptaVitae"
Remove-Item -Recurse -Force "D:\cryptavitea_files" -ErrorAction SilentlyContinue
```

- [ ] **Step 5: Recreate .venv for CryptaVitae**

```powershell
Set-Location "D:\AIStudio\Apps\CryptaVitae"
Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

---

## Task 5: Move simple Apps (no duplicates)

These projects have one location and move straight to their new home.

- [ ] **Step 1: Move all simple apps in one block**

```powershell
Move-Item "D:\AIVideoStudio"            "D:\AIStudio\Apps\AIVideoStudio"
Move-Item "D:\AlBal"                    "D:\AIStudio\Apps\AlBal"
Move-Item "D:\My_Apps\Anchor_v1"        "D:\AIStudio\Apps\Anchor"
Move-Item "D:\My_Apps\crypto-price-tracker" "D:\AIStudio\Apps\crypto-price-tracker"
Move-Item "D:\My_Apps\form_app"         "D:\AIStudio\Apps\form_app"
Move-Item "D:\Poms MES"                 "D:\AIStudio\Apps\PomsMES"
Move-Item "D:\VoiceProject"             "D:\AIStudio\Apps\VoiceProject"
Move-Item "D:\My_Apps\WinHunt_V2"       "D:\AIStudio\Apps\WinHunt"
Remove-Item -Recurse -Force "D:\My_Apps\WinHunt"   # delete old V1
```

- [ ] **Step 2: Move AudioMasterApp last (close Claude Code first if open there)**

```powershell
Move-Item "D:\AudioMasterApp" "D:\AIStudio\Apps\AudioMasterApp"
```

After this move, reopen Claude Code pointing to `D:\AIStudio\Apps\AudioMasterApp`.

- [ ] **Step 3: Verify Apps folder**

```powershell
Get-ChildItem "D:\AIStudio\Apps" | Select-Object Name | Sort-Object Name
```

Expected: AIVideoStudio, AlBal, Anchor, AudioMasterApp, ClearPath, crypto-price-tracker, CryptaVitae, CryptaVitae-Mobile, CryptaVitae-Website, form_app, MeaVita, PomsMES, VoiceProject, WinHunt

- [ ] **Step 4: Recreate .venv for any remaining Python projects that had one**

For each Python project you moved that had a `.venv`:
```powershell
Set-Location "D:\AIStudio\Apps\<ProjectName>"
Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

---

## Task 6: Move Infrastructure

- [ ] **Step 1: Move AI tools and models**

```powershell
Move-Item "D:\Local_AI_Models"             "D:\AIStudio\Infrastructure\LocalModels"
Move-Item "D:\n8n"                         "D:\AIStudio\Infrastructure\n8n"
Move-Item "D:\ComfyUI workflow backups"    "D:\AIStudio\Infrastructure\ComfyUI"
```

- [ ] **Step 2: Move content from the existing D:\AI folder**

```powershell
Move-Item "D:\AI\Scripts"    "D:\AIStudio\Infrastructure\Scripts"
Move-Item "D:\AI\Workflows"  "D:\AIStudio\Infrastructure\Workflows"
```

- [ ] **Step 3: Review D:\AI\Models, D:\AI\Input, D:\AI\Outputs, D:\AI\Archives**

```powershell
Get-ChildItem "D:\AI\Models"   | Select-Object Name, Length | Sort-Object Length -Descending | Select-Object -First 10
Get-ChildItem "D:\AI\Input"    | Select-Object Name
Get-ChildItem "D:\AI\Outputs"  | Select-Object Name
Get-ChildItem "D:\AI\Archives" | Select-Object Name
```

Then merge or move as appropriate:
```powershell
# If D:\AI\Models has content separate from Local_AI_Models:
Move-Item "D:\AI\Models\*" "D:\AIStudio\Infrastructure\LocalModels\" -Force

# Input/Outputs/Archives — move if they have useful content, delete if empty
Remove-Item -Recurse -Force "D:\AI\Input"    # only if empty or irrelevant
Remove-Item -Recurse -Force "D:\AI\Outputs"  # only if empty or irrelevant
Remove-Item -Recurse -Force "D:\AI\Archives" # only if empty or irrelevant
```

- [ ] **Step 4: Delete the now-empty D:\AI folder (only after confirming all content moved)**

```powershell
Get-ChildItem "D:\AI"   # confirm empty
Remove-Item -Recurse -Force "D:\AI"
```

- [ ] **Step 5: Verify Infrastructure**

```powershell
Get-ChildItem "D:\AIStudio\Infrastructure" | Select-Object Name
```

---

## Task 7: Clean up loose files at D:\ root

- [ ] **Step 1: Move temp/test files to Scratch**

```powershell
Move-Item "D:\pytest_err.txt"         "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pytest_full.txt"        "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pytest_full_err.txt"    "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pytest_full_out.txt"    "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pytest_full2_err.txt"   "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pytest_full2_out.txt"   "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pytest_out.txt"         "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pytest_p10_err.txt"     "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pytest_p10_out.txt"     "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pytest_pdf_err.txt"     "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pytest_pdf_out.txt"     "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pytest_sync.txt"        "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pytest_sync_all_err.txt" "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pytest_sync_all_out.txt" "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pytest_sync_err.txt"    "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pt1.txt"  "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pt1e.txt" "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pt2.txt"  "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pt2e.txt" "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pt3.txt"  "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\pt3e.txt" "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\test_output.txt" "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\nul"      "D:\AIStudio\Scratch\" -ErrorAction SilentlyContinue
Move-Item "D:\tmp"      "D:\AIStudio\Scratch\tmp" -ErrorAction SilentlyContinue
```

- [ ] **Step 2: Handle remaining loose items at D:\ root**

```powershell
# Review these before acting:
Get-Item "D:\New folder"           # delete if empty
Get-Item "D:\work"                 # check contents — move to AIStudio or leave
Get-Item "D:\Claude"               # check contents — move to AIStudio\Infrastructure or leave
Get-Item "D:\Chat GPT Files"       # check contents — move to AIStudio\Infrastructure or leave
```

```powershell
Remove-Item -Recurse -Force "D:\New folder" -ErrorAction SilentlyContinue
# Move Claude and ChatGPT Files if you want them inside AIStudio:
Move-Item "D:\Claude"          "D:\AIStudio\Infrastructure\Claude" -ErrorAction SilentlyContinue
Move-Item "D:\Chat GPT Files"  "D:\AIStudio\Infrastructure\ChatGPT" -ErrorAction SilentlyContinue
```

- [ ] **Step 3: Delete the now-empty My_Apps folder**

```powershell
Get-ChildItem "D:\My_Apps"   # confirm empty
Remove-Item -Recurse -Force "D:\My_Apps"
```

---

## Task 8: Final verification

- [ ] **Step 1: Check the full AIStudio tree**

```powershell
Get-ChildItem "D:\AIStudio" -Recurse -Depth 2 | Select-Object FullName
```

- [ ] **Step 2: Confirm D:\ root only has non-AI folders**

```powershell
Get-ChildItem "D:\" | Select-Object Name | Sort-Object Name
```

Expected survivors: `AIStudio`, `Business Folder`, `College`, `Clio PDF files`, `eCollege`, `Music`, `Paddie`, `OneDriveTemp`, `System Volume Information`, and similar personal/system folders. No loose project folders or .txt files.

- [ ] **Step 3: Update Claude Code working directory**

If you use Claude Code on any moved project, navigate to its new path:
```
D:\AIStudio\Apps\AudioMasterApp
```

Any GitHub remotes inside `.git/config` inside each project are unaffected by the move — they point to GitHub URLs which don't change.
