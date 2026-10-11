---
name: hatch-pet
description: Create, repair, validate, visually QA, and package Codex-compatible animated pets and pet spritesheets from character art, generated images, brand cues, or visual references. Deterministic Pillow-only raster pipeline plus a pluggable image-generation layer.
---

# Hatch Pet（本环境复刻版）

## Overview

Create a Codex-compatible animated pet from a concept, brand cue, one or more reference images, or any combination. The deterministic pipeline (atlas geometry, validation, QA, packaging) is identical to the upstream OpenAI skill; the only change is the generation layer: instead of the Codex `$imagegen` system skill, this repo uses a pluggable local CLI (`scripts/imagegen_generate.py`) with swappable backends.

User-facing inputs are optional. Infer a missing pet name from concept/brand/reference filenames; infer a missing description from the concept or references. Without reference images, generate the base pet from text first, then use that base as the canonical reference for every animation row.

## Generation Layer（可插拔，替代 $imagegen）

All visual generation goes through one CLI — never call image APIs ad hoc from the workflow:

```bash
python scripts/imagegen_generate.py \
  --prompt-file <run>/prompts/<job>.md \
  --input-image <abs path> --input-role "<role>" \   # repeatable; rows must attach theirs
  --output <abs output.png> \
  --backend <trae|manual> --width W --height H
```

- List backends: `python scripts/imagegen_generate.py --list-backends`
- `trae`: HTTP text-to-image endpoint. Prompt-only (rejects `--input-image`), fixed aspect presets. Suitable for the **base** job; not for row strips.
- `manual`: promotes an externally generated image from a staging dir (`--staging-dir`, default `./staged/<output filename>`). Use when the model/agent generates rows with an external tool that supports reference images.
- Adding a backend: implement the `ImagegenBackend` protocol in `scripts/imagegen_backends.py` (`generate(prompt, input_images, output_path, *, width, height)`, plus `name`/`supports_references`) and register it in `get_backend`.

Rules carried over from upstream:

- Only the `base` job may be prompt-only. Every row-strip job must attach its listed grounding images (canonical base + layout guide) when the backend supports references; with a prompt-only backend, paste the canonical-base description into the prompt and accept the identity risk — flag it in the QA note.
- Keep the chroma key from `pet_request.json` in every prompt; do not force a fixed green screen.
- If a row generation fails at transport level, retry once with the job's `retry_prompt_file`; if it still fails, stop and report — do not switch backends silently.
- After selecting an output, the parent copies it into the job's `decoded/` path and marks the job complete in `imagegen-jobs.json`. Never write helper scripts that fabricate row outputs.

## Storage Discipline

- One generation call per visual job; do not batch.
- Workers/agent steps return only `selected_source=...` and `qa_note=...`; do not inline image previews into manifests or logs.
- The parent inspects only the final contact sheet and preview GIFs, not every intermediate PNG.
- After copying into `decoded/`, remove staged originals.

## Brand Discovery

If the user provides a brand/company/product name rather than a concrete avatar description or reference image, run a lightweight discovery step (web search subagent) before `prepare_pet_run.py`. Prefer official sources; 2–4 sources; adaptive markdown brief covering identity/category, audience, visual system, personality, product motifs, mascot translation cues, avoidances, evidence/confidence. End the brief with a `Generation handoff` section containing exactly `brand_name`, `brand_brief` (≤45 words), `avatar_seed`, `avoid`, `brand_sources`. Do not copy logos, readable marks, UI screenshots, slogans, or text. Pass the brief to `prepare_pet_run.py` via `--brand-discovery-file`, `--brand-name`, `--brand-brief`, repeated `--brand-source`, and `--pet-notes <avatar_seed>`.

Skip discovery when the user provides a concrete mascot description or reference images.

## Atlas Contract（硬约束）

- Atlas: 1536×1872, 8 columns × 9 rows, cell 192×208, transparent background.
- Rows: 0 idle(6f), 1 running-right(8f), 2 running-left(8f), 3 waving(4f), 4 jumping(5f), 5 failed(8f), 6 waiting(6f), 7 running(6f), 8 review(6f). Unused cells must be fully transparent.
- Full timing and semantics: [references/animation-rows.md](references/animation-rows.md); app contract: [references/codex-pet-contract.md](references/codex-pet-contract.md); QA rubric: [references/qa-rubric.md](references/qa-rubric.md).

## Pet-Safe Styles

Default `auto`; presets: `pixel`, `plush`, `clay`, `sticker`, `flat-vector`, `3d-toy`, `painterly`, `brand-inspired`. Any style is fine when: compact whole-body silhouette readable at 192×208; consistent face/proportions/material/palette/props across all rows; clean removable chroma-key background; no text/labels/UI/logos unless user-approved.

## Transparency And Effects

- Allowed effects: state-relevant, physically attached to the pet, inside the same frame slot, opaque and hard-edged, non-chroma-key colors, readable at cell size.
- Forbidden by default: speed lines/motion arcs/afterimages/blur; detached stars/sparkles/punctuation/tear drops/smoke; any shadows (cast/contact/drop/floor); glow/halo/aura; text/labels/grids/speech bubbles/scenery; chroma-key-adjacent colors anywhere on pet or props; stray pixels, cropped body parts, poses crossing slot boundaries.
- State-specific: `idle` needs visible micro-variation (no 6 identical frames) and no action poses; `waving` = limb pose only, no wave marks; `jumping` = body position only, no dust/shadows; `failed` allows attached opaque tears/smoke/stars only; `waiting` = expectant asking pose, distinct from idle/review; `running` = working/thinking/typing effort, never literal foot-running; `review` = lean/blink/head-tilt, no new props; `running-right`/`running-left` = true directional gait with alternating cadence, correct facing, no speed lines/dust.

## Visible Progress Plan

Keep a visible 4-step checklist for every run (repair runs start at the first relevant step):

1. Getting `<Pet>` ready. — name, description, references, style, run folder; brand discovery first for bare brand requests.
2. Imagining `<Pet>`'s main look. — generate the base reference image (visual source of truth).
3. Picturing `<Pet>`'s poses. — generate rows, starting with `idle` and `running-right`; mirror `running-left` only when clearly safe.
4. Hatching `<Pet>`. — deterministic pipeline, contact-sheet + preview review, package `pet.json` + `spritesheet.webp`, report paths.

Mark a step complete only when the real file/decision exists.

## Default Workflow

```bash
SKILL_DIR="/Users/lyu/Downloads/hatch pet"

# 1. Prepare run folder + job manifest (all args optional except constraints)
python "$SKILL_DIR/scripts/prepare_pet_run.py" \
  --pet-name "<Name>" --description "<one sentence>" \
  --reference /abs/reference.png --output-dir /abs/run \
  --pet-notes "<stable pet description>" \
  --style-preset auto --force

# 2. Inspect ready jobs
jq '.jobs[] | {id, kind, status, depends_on, prompt_file, retry_prompt_file, input_images, output_path}' \
  /abs/run/imagegen-jobs.json

# 3. Generate jobs in order: base -> idle, running-right -> (mirror running-left?) -> rest
python "$SKILL_DIR/scripts/imagegen_generate.py" \
  --prompt-file /abs/run/prompts/base-pet.md --output /abs/generated/base.png --backend trae
python "$SKILL_DIR/scripts/imagegen_generate.py" \
  --prompt-file /abs/run/prompts/rows/idle.md \
  --input-image /abs/run/references/canonical-base.png --input-role "identity reference" \
  --input-image /abs/run/references/layout-guides/idle.png --input-role "layout guide only" \
  --output /abs/generated/idle.png --backend manual --staging-dir /abs/staging

# 4. Copy selected output into decoded/ and mark complete (jq), base also -> references/canonical-base.png

# 5. Optional mirror derivation (only after visual approval of running-right)
python "$SKILL_DIR/scripts/derive_running_left_from_running_right.py" \
  --run-dir /abs/run --confirm-appropriate-mirror \
  --decision-note "<why mirroring preserves identity>"

# 6. Deterministic pipeline
python "$SKILL_DIR/scripts/extract_strip_frames.py" --decoded-dir /abs/run/decoded --output-dir /abs/run/frames --states all --method auto
python "$SKILL_DIR/scripts/inspect_frames.py" --frames-root /abs/run/frames --json-out /abs/run/qa/review.json --require-components
python "$SKILL_DIR/scripts/compose_atlas.py" --frames-root /abs/run/frames --output /abs/run/final/spritesheet.png --webp-output /abs/run/final/spritesheet.webp
python "$SKILL_DIR/scripts/validate_atlas.py" /abs/run/final/spritesheet.webp --json-out /abs/run/final/validation.json
python "$SKILL_DIR/scripts/make_contact_sheet.py" /abs/run/final/spritesheet.webp --output /abs/run/qa/contact-sheet.png
python "$SKILL_DIR/scripts/render_animation_previews.py" --frames-root /abs/run/frames --output-dir /abs/run/qa/previews

# 6b. If preview GIFs show extraction-induced size popping (and the source strip was stable):
#     rerun extract with --method stable-slots, inspect with --allow-stable-slots, redo 6.

# 7. Package
PET_DIR="$HOME/.codex/pets/<pet-id>"   # or any target dir
mkdir -p "$PET_DIR"
cp /abs/run/final/spritesheet.webp "$PET_DIR/spritesheet.webp"
jq -n --arg id "<pet-id>" --arg displayName "<Name>" --arg description "<desc>" \
  '{id: $id, displayName: $displayName, description: $description, spritesheetPath: "spritesheet.webp"}' \
  > "$PET_DIR/pet.json"
```

Expected run structure before cleanup: `pet_request.json`, `imagegen-jobs.json`, `prompts/`, `decoded/`, `frames/frames-manifest.json`, `final/spritesheet.webp`, `final/validation.json`, `qa/contact-sheet.png`, `qa/previews/*.gif`, `qa/review.json`.

## Visual QA

Deterministic validation is necessary but not sufficient. After step 6, visually inspect `qa/contact-sheet.png` and `qa/previews/*.gif` (a subagent/vision pass is fine). Block acceptance on: identity/style/palette/silhouette drift across rows; missing/blank frames; copied guide marks; white/nontransparent cell backgrounds; cropped bodies; slot overlap; detached effects, shadows, glows, smears, dust; chroma artifacts; wrong facing direction; reversed or non-alternating gait; size popping; inert idle loops. Return `visual_qa=pass|fail` plus row-specific repair notes.

## Repair Workflow

- Repair the smallest failing scope: regenerate only the failed row, copy into the same `decoded/` path, keep the job complete with updated `source_path`/`completed_at`.
- Identity repairs: ground the row worker with canonical base + original references + contact sheet + exact failure note; preserve identity and style.
- Extraction-induced motion popping: rerun with `--method stable-slots` first; regenerate imagery only when the source strip itself is clipped/unstable/semantically wrong.

## Rules

- All generation through `scripts/imagegen_generate.py`; never fabricate rows locally (no drawing/tiling/transforms as substitutes for generated rows).
- `running-right` before any `running-left` mirror decision; mirror only via the deterministic script (framewise, order-preserving).
- Never derive `waiting`, `running`, `failed`, `review`, `jumping`, or `waving` from another state.
- Only mark a visual job complete after its output is copied into `decoded/`.
- Never rely on generated images for exact atlas geometry; the deterministic scripts own geometry.
- Treat `qa/review.json` errors as blockers; warnings require visual review. Identity drift blocks even when JSONs are clean.
- Cleanup after QA passes: keep `pet_request.json`, `final/spritesheet.webp`, `final/validation.json`, `qa/contact-sheet.png`, `qa/previews/`, `qa/review.json`; remove prompts, layout guides, decoded strips, extracted frames, `final/spritesheet.png`, job manifest. Skip cleanup when debugging or repairing.

## Acceptance Criteria

- Final atlas is PNG or WebP, 1536×1872, transparent-capable, 192×208 cells.
- Used cells non-empty; unused cells fully transparent; zero transparent-RGB residue.
- Row/frame counts match [references/animation-rows.md](references/animation-rows.md).
- Contact sheet and per-row GIF previews produced and visually inspected; `qa/review.json` has no errors.
- No unintended size popping, reversed directional cadence, or wrong row semantics in previews.
- Package staged as `<target>/pets/<pet-name>/pet.json` + `spritesheet.webp`.

## 复刻说明（与上游差异）

- 生成层：上游的 `$imagegen` 系统技能 → 本 repo 的 `scripts/imagegen_generate.py` + `imagegen_backends.py`（协议可插拔）。`trae` 后端为 HTTP 文生图端点（实测为异步占位返回，不可直接用于生产；建议用 `manual` 后端或新增带参考图支持的 API 后端）。
- 子代理编排、rollout 存储约束等 Codex 特有概念已简化为对本环境有意义的纪律条款。
- 8 个确定性脚本与 3 份 references 与上游逐字节一致（MIT，见 LICENSE.txt）。
