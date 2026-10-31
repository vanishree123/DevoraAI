import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import requests
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
PROJECTS_DIR = APP_DIR / "workspace"
DATA_DIR.mkdir(exist_ok=True)
PROJECTS_DIR.mkdir(exist_ok=True)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:1.5b")

st.set_page_config(page_title="Devora AI", page_icon="🛠️", layout="wide")

# ---------- Local persistence ----------
def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-_").lower()
    return (value[:48] or "new-project")


def project_file(project_id: str) -> Path:
    return DATA_DIR / f"{slugify(project_id)}.json"


def load_project(project_id: str) -> dict:
    path = project_file(project_id)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "id": project_id,
        "name": project_id,
        "idea": "",
        "mode": "Guided",
        "requirements": "",
        "approved": False,
        "architecture": "",
        "code_files": [],
        "qa_result": "",
        "devops_result": "",
        "history": [],
        "updated": datetime.now().isoformat(timespec="seconds"),
    }


def save_project(project: dict) -> None:
    project["updated"] = datetime.now().isoformat(timespec="seconds")
    project_file(project["id"]).write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")


def add_history(project: dict, agent: str, content: str) -> None:
    project.setdefault("history", []).append({
        "time": datetime.now().isoformat(timespec="seconds"),
        "agent": agent,
        "content": content[:12000],
    })
    project["history"] = project["history"][-100:]

# ---------- Ollama ----------
def ollama_tags():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=4)
        r.raise_for_status()
        return [m.get("name") for m in r.json().get("models", [])]
    except Exception:
        return []


def ask_model(model: str, system: str, prompt: str, json_mode: bool = False, temperature: float = 0.2) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": 4096},
    }
    if json_mode:
        payload["format"] = "json"
    response = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=600)
    response.raise_for_status()
    return response.json().get("message", {}).get("content", "").strip()


def call_agent(project: dict, model: str, agent: str, system: str, prompt: str, json_mode: bool = False) -> str:
    with st.spinner(f"{agent} is working with your local Ollama model…"):
        result = ask_model(model, system, prompt, json_mode=json_mode)
    add_history(project, agent, result)
    save_project(project)
    return result

# ---------- Agent definitions ----------
BA_SYSTEM = """You are Devora AI's senior Business Analyst for non-technical people. Use simple language. First understand the user's actual goal. Ask only the smallest set of essential unanswered questions; do not invent enterprise requirements, user roles, analytics, authentication, storage, integrations, cloud, compliance or scale unless the use case needs them. Clearly separate confirmed facts, assumptions and open questions. Never claim the user approved something. If asked to draft requirements, create concise, project-specific scope, user stories and testable acceptance criteria. Do not write code."""
ARCH_SYSTEM = """You are Devora AI's Solution Architect. Design the simplest maintainable architecture that meets the approved requirements. Avoid unnecessary services and dependencies. State components, data flow, technology choices, file structure, security boundaries, run instructions and trade-offs. Never add features not in scope. Do not write implementation code."""
DEV_SYSTEM = """You are Devora AI's senior software developer. Generate a small, complete, runnable implementation that matches ONLY the approved requirements and architecture. Return valid JSON only, with schema {\"summary\":string,\"files\":[{\"path\":string,\"content\":string}]}. Include all source files and useful tests. No markdown fences. Paths must be relative. Do not include secrets. Prefer simple dependencies and include README.md. The app must run locally. Do not use placeholders, TODOs or ellipses in required functionality."""
QA_SYSTEM = """You are Devora AI's QA engineer. Review the supplied requirements, architecture and generated file list. Identify test scenarios, edge cases, likely defects, security concerns and missing acceptance criteria. Be precise and prioritize. Do not claim tests were executed; distinguish static review from actual execution results."""
DEVOPS_SYSTEM = """You are Devora AI's DevOps engineer. Prepare a safe local deployment plan for the generated project. Prefer simple local run commands. Only add Docker when it is appropriate. Explain environment variables, dependencies, startup, health checks, logs, rollback and deployment risks. Never deploy externally or spend money. Do not claim deployment occurred."""
ORCH_SYSTEM = """You are Devora AI's software delivery orchestrator. Given a user's idea and current project state, propose the next practical agent action and explain dependencies. Keep the project moving in small verifiable steps. Respect approvals and never claim an agent ran if it did not."""

# ---------- File safety and code workspace ----------
def safe_relative_path(raw: str) -> Path:
    raw = str(raw).replace("\\", "/").strip()
    p = Path(raw)
    if not raw or p.is_absolute() or ".." in p.parts or re.match(r"^[A-Za-z]:", raw):
        raise ValueError(f"Unsafe generated path rejected: {raw!r}")
    if len(raw) > 180:
        raise ValueError("Generated path is too long")
    return p


def write_generated_files(project: dict, payload: dict) -> list[str]:
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("Developer response did not contain a non-empty files array")
    root = PROJECTS_DIR / slugify(project["id"])
    root.mkdir(parents=True, exist_ok=True)
    written = []
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("content"), str):
            continue
        rel = safe_relative_path(item["path"])
        if rel.parts[0].lower() in {".git", ".venv", "venv", "node_modules"}:
            raise ValueError("Generated project attempted to write into a protected directory")
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item["content"], encoding="utf-8")
        written.append(rel.as_posix())
    if not written:
        raise ValueError("No valid source files were generated")
    project["code_files"] = written
    add_history(project, "Developer", "Generated files: " + ", ".join(written))
    save_project(project)
    return written


def project_root(project: dict) -> Path:
    return PROJECTS_DIR / slugify(project["id"])


def run_project_tests(project: dict) -> tuple[int, str]:
    root = project_root(project)
    if not root.exists():
        return 2, "No generated project folder found. Run the Developer agent first."
    test_files = list(root.rglob("test_*.py")) + list(root.rglob("*_test.py"))
    if not test_files:
        return 2, "No Python pytest files found. QA can still perform a static review, but there are no automated Python tests to execute."
    # Generated code is untrusted. This MVP warns and requires an explicit user click.
    cmd = [sys.executable, "-m", "pytest", "-q", "--disable-warnings", "--maxfail=5"]
    try:
        completed = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=90, shell=False)
        output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
        return completed.returncode, output[-14000:]
    except subprocess.TimeoutExpired as exc:
        return 124, "Tests exceeded the 90-second limit.\n" + (exc.stdout or "")
    except Exception as exc:
        return 1, f"Could not execute tests: {exc}"


def make_delivery_zip(project: dict) -> Path:
    root = project_root(project)
    if not root.exists():
        raise FileNotFoundError("Generate the application first")
    zip_path = PROJECTS_DIR / f"{slugify(project['id'])}-delivery.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in root.rglob("*"):
            if path.is_file() and not any(part in {".venv", "venv", "__pycache__", ".git"} for part in path.parts):
                archive.write(path, path.relative_to(root))
    return zip_path

# ---------- UI ----------
st.markdown("# 🛠️ Devora AI")
st.caption("From human ideas to production software · Local-first multi-agent MVP")
with st.sidebar:
    st.subheader("Workspace")
    model_names = ollama_tags()
    if model_names:
        preferred = DEFAULT_MODEL if DEFAULT_MODEL in model_names else model_names[0]
        model = st.selectbox("Ollama model", model_names, index=model_names.index(preferred))
        st.success("Ollama connected")
    else:
        model = st.text_input("Ollama model", value=DEFAULT_MODEL)
        st.error("Ollama is not reachable. Start Ollama and refresh this page.")
    st.caption(f"API: {OLLAMA_URL}")
    st.divider()
    project_name = st.text_input("Project name", value=st.session_state.get("project_name", "My First Project"))
    st.session_state["project_name"] = project_name
    if st.button("Open / create project", use_container_width=True):
        st.session_state["project"] = load_project(project_name)
        st.rerun()

if "project" not in st.session_state:
    st.session_state["project"] = load_project(st.session_state.get("project_name", "My First Project"))
project = st.session_state["project"]
project["name"] = project_name
project["id"] = slugify(project_name)

status_cols = st.columns(4)
status_cols[0].metric("Project", project["name"][:18])
status_cols[1].metric("Mode", project.get("mode", "Guided"))
status_cols[2].metric("Generated files", len(project.get("code_files", [])))
status_cols[3].metric("Requirements approved", "Yes" if project.get("approved") else "No")

mode_col, idea_col = st.columns([1, 3])
with mode_col:
    project["mode"] = st.radio("Working mode", ["Guided", "Autonomous"], index=0 if project.get("mode", "Guided") == "Guided" else 1, help="Both modes require approval for external deployment, paid resources, secrets or destructive actions.")
with idea_col:
    project["idea"] = st.text_area("What would you like to build?", value=project.get("idea", ""), height=90, placeholder="Describe your app in everyday language…")

ba_tab, arch_tab, dev_tab, qa_tab, ops_tab, flow_tab = st.tabs([
    "💬 Business Analyst", "🏗️ Architect", "💻 Developer", "🧪 QA Engineer", "🚀 DevOps", "🔄 Orchestrator"
])

with ba_tab:
    st.subheader("Business Analyst")
    st.caption("Clarifies the idea, asks focused questions and prepares requirements for approval.")
    for entry in project.get("history", []):
        if entry.get("agent") == "Business Analyst":
            with st.chat_message("assistant"):
                st.caption(entry.get("time", ""))
                st.markdown(entry.get("content", ""))
    user_msg = st.chat_input("Describe your idea or answer the BA's questions…", key="ba_chat")
    if user_msg:
        project["idea"] = project.get("idea") or user_msg
        context = f"Project: {project['name']}\nOriginal idea: {project.get('idea','')}\nExisting requirements draft: {project.get('requirements','')}\nUser message: {user_msg}\n\nIf information is missing, ask only essential follow-up questions. If the user asks to prepare/finalize requirements, produce a concise BRD with scope, out-of-scope, user stories, acceptance criteria, assumptions and open questions."
        try:
            answer = call_agent(project, model, "Business Analyst", BA_SYSTEM, context)
            st.rerun()
        except Exception as exc:
            st.error(f"Business Analyst error: {exc}")
    if st.button("Generate / refresh BRD", key="brd_btn"):
        if not project.get("idea", "").strip():
            st.warning("Describe your idea first.")
        else:
            try:
                prompt = f"Create a concise, specific BRD for this project. Do not invent requirements. Clearly mark assumptions and open questions.\nProject idea: {project['idea']}\nConversation history: {json.dumps(project.get('history', [])[-20:], ensure_ascii=False)}"
                project["requirements"] = call_agent(project, model, "Business Analyst", BA_SYSTEM, prompt)
                project["approved"] = False
                save_project(project)
                st.rerun()
            except Exception as exc:
                st.error(f"BRD generation failed: {exc}")
    if project.get("requirements"):
        st.markdown("#### Requirements draft")
        st.markdown(project["requirements"])
        project["approved"] = st.checkbox("I approve these requirements for architecture and implementation", value=bool(project.get("approved")))
        if st.button("Save approval", key="approve_btn"):
            save_project(project)
            st.success("Approval saved. You can now use Architect and Developer.")

with arch_tab:
    st.subheader("Solution Architect")
    st.caption("Creates a practical technical design from approved requirements.")
    if not project.get("approved"):
        st.warning("Approve the BRD in the Business Analyst tab before architecture design.")
    if st.button("Generate architecture", disabled=not bool(project.get("approved"))):
        try:
            prompt = f"Project: {project['name']}\nApproved requirements:\n{project['requirements']}\n\nProduce a practical architecture: recommended stack, components, data flow, project structure, API/data model if needed, security considerations, local run approach, trade-offs. Keep it proportional to the project."
            project["architecture"] = call_agent(project, model, "Solution Architect", ARCH_SYSTEM, prompt)
            save_project(project)
            st.rerun()
        except Exception as exc:
            st.error(f"Architect error: {exc}")
    if project.get("architecture"):
        st.markdown(project["architecture"])

with dev_tab:
    st.subheader("Developer")
    st.caption("Generates real project files in the local workspace. Review generated code before running it.")
    if not project.get("approved") or not project.get("architecture"):
        st.warning("Approve requirements and generate architecture first.")
    if st.button("Generate application code", disabled=not (bool(project.get("approved")) and bool(project.get("architecture")))):
        try:
            prompt = f"Project name: {project['name']}\nApproved requirements:\n{project['requirements']}\nArchitecture:\n{project['architecture']}\n\nGenerate a minimal complete runnable implementation and tests. Include only necessary features. Return the required JSON schema."
            raw = call_agent(project, model, "Developer", DEV_SYSTEM, prompt, json_mode=True)
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", raw, re.S)
                if not match:
                    raise ValueError("Model did not return valid JSON. Try again or use a stronger model.")
                payload = json.loads(match.group(0))
            written = write_generated_files(project, payload)
            project["developer_summary"] = payload.get("summary", "Application files generated.")
            save_project(project)
            st.success("Generated: " + ", ".join(written))
            st.rerun()
        except Exception as exc:
            st.error(f"Code generation failed: {exc}")
    root = project_root(project)
    if project.get("code_files") and root.exists():
        st.markdown("#### Generated workspace")
        st.write(project.get("developer_summary", ""))
        for rel in project["code_files"]:
            path = root / safe_relative_path(rel)
            if path.exists() and path.is_file():
                with st.expander(rel):
                    try:
                        st.code(path.read_text(encoding="utf-8")[:20000], language=path.suffix.lstrip(".") or "text")
                    except Exception:
                        st.caption("Unable to preview this file.")
        st.caption(f"Local folder: {root}")

with qa_tab:
    st.subheader("QA Engineer")
    st.caption("Performs an AI review and can execute generated Python pytest files after your confirmation.")
    if not project.get("code_files"):
        st.info("Generate application code first.")
    if st.button("Run QA review", disabled=not bool(project.get("code_files"))):
        try:
            prompt = f"Requirements:\n{project.get('requirements','')}\nArchitecture:\n{project.get('architecture','')}\nGenerated files:\n{json.dumps(project.get('code_files', []))}\n\nPerform a detailed static QA review. Provide test scenarios, edge cases, likely bugs and priorities. Clearly say this is static review only."
            project["qa_review"] = call_agent(project, model, "QA Engineer", QA_SYSTEM, prompt)
            save_project(project)
            st.rerun()
        except Exception as exc:
            st.error(f"QA review error: {exc}")
    if project.get("qa_review"):
        st.markdown("#### QA review")
        st.markdown(project["qa_review"])
    st.warning("Safety notice: generated code is untrusted. Running tests executes code from the generated project on your computer. Only proceed if you have reviewed and trust the files. This MVP does not provide an OS-level sandbox.")
    confirm_tests = st.checkbox("I reviewed the generated files and authorize running the project's pytest tests", key="confirm_tests")
    if st.button("Execute automated tests", disabled=not (confirm_tests and bool(project.get("code_files")))):
        code, output = run_project_tests(project)
        project["qa_result"] = f"Exit code: {code}\n{output}"
        add_history(project, "QA Test Runner", project["qa_result"])
        save_project(project)
        st.rerun()
    if project.get("qa_result"):
        st.markdown("#### Actual test execution result")
        st.code(project["qa_result"])

with ops_tab:
    st.subheader("DevOps Engineer")
    st.caption("Prepares a local delivery package and deployment instructions. No external deployment or paid resource is launched.")
    if not project.get("code_files"):
        st.info("Generate application code first.")
    if st.button("Create deployment plan", disabled=not bool(project.get("code_files"))):
        try:
            prompt = f"Requirements:\n{project.get('requirements','')}\nArchitecture:\n{project.get('architecture','')}\nFiles:\n{json.dumps(project.get('code_files', []))}\nQA results:\n{project.get('qa_result','Not executed')}\n\nCreate a practical local deployment/runbook with exact commands based on the files. Identify missing prerequisites. Explain rollback and security. Do not claim deployment occurred."
            project["devops_result"] = call_agent(project, model, "DevOps Engineer", DEVOPS_SYSTEM, prompt)
            save_project(project)
            st.rerun()
        except Exception as exc:
            st.error(f"DevOps error: {exc}")
    if project.get("devops_result"):
        st.markdown(project["devops_result"])
    if st.button("Package application as ZIP", disabled=not bool(project.get("code_files"))):
        try:
            path = make_delivery_zip(project)
            st.success(f"Package created: {path.name}")
            st.download_button("Download application ZIP", data=path.read_bytes(), file_name=path.name, mime="application/zip")
        except Exception as exc:
            st.error(f"Packaging failed: {exc}")

with flow_tab:
    st.subheader("AI Orchestrator")
    st.caption("Coordinates the next step based on project progress. You trigger each action explicitly.")
    if st.button("Recommend next action"):
        try:
            state = {
                "idea": project.get("idea"), "requirements_approved": project.get("approved"),
                "has_architecture": bool(project.get("architecture")), "generated_files": project.get("code_files", []),
                "qa_reviewed": bool(project.get("qa_review")), "qa_executed": bool(project.get("qa_result")),
                "devops_plan": bool(project.get("devops_result")),
            }
            result = call_agent(project, model, "Orchestrator", ORCH_SYSTEM, f"Project state:\n{json.dumps(state, indent=2)}\nRecommend the single best next action, explain why, and state which tab/action to use.")
            st.markdown(result)
        except Exception as exc:
            st.error(f"Orchestrator error: {exc}")
    st.markdown("#### Project activity")
    for item in reversed(project.get("history", [])[-20:]):
        with st.expander(f"{item.get('time','')} · {item.get('agent','Agent')}"):
            st.write(item.get("content", ""))

save_project(project)
st.divider()
st.caption("Devora AI Local MVP · Human approval required for requirements, generated-code execution and external deployment. Local model responses can be imperfect; review outputs before use.")
