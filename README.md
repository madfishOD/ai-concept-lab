# Anima Concept Lab — local prototype

Approved scope: [PLAN.md](PLAN.md). Local image generation and strict masked editing with artist-controlled iterations. Initial models/workflows are experimental; human art review is required before calling a result useful or production-ready.

Implementation and first measured results: [EXPERIMENTS.md](EXPERIMENTS.md).

## Start on this PC

From PowerShell in `D:\Work\Repos\ai-concept-pipeline`:

```powershell
.\scripts\Start.ps1
```

- UI: http://127.0.0.1:8765
- ComfyUI authoring UI: http://127.0.0.1:8188
- Ollama: http://127.0.0.1:11434
- Logs: `data/logs/`. Services run locally in the background; no login auto-start is installed.
- Pull the agent model if missing: `.\scripts\Pull-Agent.ps1` after starting services.

## Artist workflow

1. Enter a brief. For an edit upload a source and **opaque grayscale PNG mask**, white edits / black preserves, with exactly matching dimensions.
2. Select up to four references, or let Qwen select from the small Nocturna library.
3. Choose **Prepare with Qwen**, then inspect/change the operation, references and English diffusion prompt. For a direct workflow test choose **Configure manually**.
4. Generate. Several variants use different seeds; different design directions require different briefs.
5. Review the image, mark usefulness, or continue from it with a new mask and instruction.

Strict editing composites the generated image onto the source at its original resolution. Pixels with a zero mask remain exactly identical. Feathering is clipped inside the mask. The output is normalized PNG; comparisons apply to decoded pixels, not file bytes/metadata. Mask all background pixels needed for a larger silhouette. Transparent/color masks are not supported.

## Architecture and boundaries

- `pipeline/`: FastAPI, SQLite job persistence, Ollama planning, ComfyUI adapter, strict compositing.
- `web/`: dependency-free browser UI; one active generation, no authentication/multi-user deployment.
- `library/`: locally copied reference PNGs and metadata. All initial references are **candidates**, not art-lead approvals.
- `instructions/`: versioned project context for the agent; no model training.
- `workflows/`: API-format graphs and a catalog. App substitutions are deliberately limited to known node inputs.
- `data/jobs/<id>/`: prompt, selected reference snapshots, source/mask, exact submitted graph, Comfy history, raw and final outputs, manifest and reviews. Not committed to Git.
- `config.toml`: defaults; optional ignored `config.local.toml` overrides sections.
- ComfyUI and Ollama are separate installations. Project dependencies use `.venv`, never ComfyUI's embedded Python.

## First baseline

SDXL base 1.0 + IP-Adapter Plus SDXL ViT-H + CLIP ViT-H for reference-conditioned full-body concepts. Masked editing uses SDXL latent inpainting plus enforced final compositing. It is a baseline, not a dedicated instruction-editing model; prompt adherence, faces and large design changes may be weak. Reference selection by Qwen is separately evaluated from image-model quality.

Qwen3.5-9B through Ollama first classifies the requested deliverable from text, then receives short project instructions, the workflow catalog and reference previews to prepare a constrained plan. The application enforces required inputs and repairs non-English SDXL prompts with a separate local call when necessary. Masked editing uses source + mask; references are planning context, not direct image conditioning for that workflow. Qwen unloads after calls; idle ComfyUI models are freed before planning to reduce VRAM contention. External active ComfyUI jobs are never interrupted.

## Recovery

Known ComfyUI prompt IDs are preserved and polled after an app restart. Waiting jobs can be checked again without resubmission. An ambiguous network failure during submission is marked `submission_unknown` and is **not** automatically rerun. Inspect the ComfyUI queue/history and `extra_data.acp_job_id` before deciding whether to submit a new request. Persistent job status is authoritative; the browser can be refreshed freely.

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pipeline.workflows
.\.venv\Scripts\python.exe -m pytest -q
```

Use the saved `.api.json` graphs for API execution. Runtime generations store the exact substituted graph. Model download sources and installed versions are recorded in `runtime-manifest.json`; model hashes in `models.lock.json` when available. Do not run blanket updates during a comparison series.

Use `scripts/Restart-App.ps1` to restart only this app when no jobs are active. `scripts/smoke_live.py` and `scripts/verify_agent.py` create real local GPU jobs and save evidence in `data/experiments`; they are explicit integration experiments, not part of the unit suite. `scripts/bootstrap_runtime.py` preserves the original Windows download/extraction recipe. Installed app dependencies are pinned in `requirements.lock.txt`; use that file to reproduce this environment.

Windows Portable is local infrastructure. A later Linux/RunPod deployment recreates the environment from recorded dependencies and models, rather than copying Windows binaries.

## Git repository policy

Canonical remote: `git@github.com:madfishOD/ai-concept-lab.git`.
The existing local checkout remains `D:\Work\Repos\ai-concept-pipeline`.

This repository contains UTF-8 source, workflow JSON, reference **metadata**, model download
URLs/checksums and documentation only. Images, masks, generated results, model weights,
installers, runtime reports and environments remain local. Git LFS is not used.
On a fresh clone, restore your authorized local references as described in [library/README.md](library/README.md).
Links to `data/` outputs in the experiment notes work only on a workstation that has those outputs.

Enable the versioned pre-commit guard after cloning:

```powershell
git config core.hooksPath .githooks
```

`scripts/check_repository.py` checks the Git index: no image/model assets or LFS pointers,
UTF-8 text only, maximum 256 KiB per file and 2 MiB total. It also rejects forced staging of
ignored assets. To run it manually: `.\.venv\Scripts\python.exe scripts/check_repository.py`.
Hooks are a local safeguard and can be bypassed; review the staged files before publishing.
