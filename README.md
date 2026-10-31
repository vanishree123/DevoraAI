# Devora AI — Local Multi-Agent MVP

A local-first software delivery assistant powered by Ollama. This is a functional MVP containing six coordinated roles: Business Analyst, Solution Architect, Developer, QA Engineer, DevOps Engineer and Orchestrator.

## What works in this MVP

- Local Ollama connection and model selection in the sidebar.
- Business Analyst chat with adaptive follow-up questions and BRD generation.
- Explicit requirements approval gate.
- Solution Architect generates a project-specific technical design.
- Developer asks the model for a structured file manifest and writes actual files into `workspace/<project>/`.
- QA performs an AI static review and can execute generated pytest tests after an explicit user confirmation.
- DevOps creates a local runbook and packages generated files into a downloadable ZIP.
- Project state and agent activity are saved under `data/`.
- Guided and Autonomous modes are selectable. In this MVP, both retain human approval gates for sensitive actions.

## Requirements

- Windows 10/11, Python 3.10+ (Python 3.14 may work if compatible wheels are available for dependencies).
- Ollama installed and running.
- At least one local chat model. The default is `qwen2.5-coder:1.5b`.

## Install

1. Extract the ZIP to a writable folder, for example `C:\Users\<you>\DevoraAI`.
2. Ensure Ollama is running. In PowerShell, check `ollama list`.
3. Double-click `setup.bat` and wait for `Setup complete`.
4. Double-click `run_devora.bat`.
5. Open `http://localhost:8501` if the browser does not open automatically.

If you want to use another installed Ollama model, set `OLLAMA_MODEL` in `run_devora.bat` or select it in the sidebar.

## Recommended workflow

1. Enter a project name and describe the idea.
2. In Business Analyst, chat and answer questions. Click **Generate / refresh BRD** when ready.
3. Read the BRD and check **I approve these requirements**; click **Save approval**.
4. Generate architecture in the Architect tab.
5. Generate application code in Developer. Review every generated file in the workspace before running it.
6. In QA, run the static review. If you have reviewed and trust the generated files, explicitly authorize and execute pytest tests.
7. In DevOps, create the local deployment plan and package the application ZIP.

## Safety and limitations — read this

- This is a local MVP, not a production-grade autonomous software factory.
- Model output can be wrong, incomplete, insecure or fail to run. Review generated requirements, architecture and code.
- **Generated code is untrusted.** The QA test runner executes generated Python tests on your computer. This MVP does not provide an OS-level sandbox/container isolation. Only authorize test execution after reviewing the generated files. Do not use it with untrusted prompts or sensitive host data.
- DevOps creates a runbook and ZIP only. It does not deploy to public cloud, purchase services, access accounts or spend money.
- The Autonomous mode does not bypass approval gates. External deployment, paid resources, credentials, destructive actions and code execution require human authorization.
- Project data is stored locally in `data/` and generated files in `workspace/`. Keep this folder private if your projects contain confidential information.
- The app binds to `127.0.0.1` only; it is not exposed to your network.
- For complex applications, use a stronger model or a cloud model only if you choose to, and verify licensing and privacy terms.

## Troubleshooting

### Ollama not connected

Open PowerShell and run:

```powershell
ollama list
```

If needed, start Ollama from the Windows Start menu. Confirm the local API responds:

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
```

### Browser says localhost cannot be reached

Wait 5–10 seconds and refresh `http://localhost:8501`. Keep the terminal window open. If it still fails, copy the terminal error.

### Model is slow

Small CPU-only models can take time. Keep the prompt focused, close memory-heavy apps and avoid multiple simultaneous model requests.

### Python/package install fails

Copy the complete setup error. Python 3.14 package wheel availability may vary; if a dependency does not support 3.14, install Python 3.12 and rerun `setup.bat`.

## Folder layout

```text
DevoraAI_Full_MVP/
  app.py
  requirements.txt
  setup.bat
  run_devora.bat
  README.md
  data/       # created at runtime; local project history
  workspace/  # generated application files
```
