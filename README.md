<p align="center">
  <img src="assets/logo-mark.png" alt="RedForge" width="112" height="112" />
</p>

# RedForge


<h3 align="center">
The Local AI Engineering Platform
</h3>

<p align="center">
Build • Fine-tune • Benchmark • Secure • Evaluate • Deploy
</p>

<p align="center">
A desktop-first IDE for Local AI development.
</p>

---

> **Train, benchmark, secure, and manage your local AI models from one unified workspace.**

RedForge is a **Local AI Engineering Platform** designed for developers, researchers, students, and AI enthusiasts who want a professional environment for building AI applications **without relying on the cloud**.

So about why I devoloped something like this, a while ago I watched my favourite youtuber go fromm a beginner to advanced level AI engineer in less than a year. Pewdiepie fine tuned a model into something of a size of GPT. He even made Odysseus, something i ws very fascinated by. I cant really finetune an ai (not much with my comp), then I thought of making something that'll help people Train, Evaluate, Benchmark and Access thier model. So thats how the devolopment of Redforge started.

Think of it as:

> **VS Code + Docker Desktop + MLflow + LM Studio + Postman**
>
> **for Local AI.**

Everything runs **locally by default**.

No accounts.

No subscriptions.

No telemetry.

No vendor lock-in.

No data leaves your computer unless **you explicitly connect a cloud provider**.

---

# 🌐 Website

**www.redforge.site**

---

# 🚀 What is RedForge?

Modern AI development is fragmented.

You download models using one application.

Run them from another.

Fine-tune using command-line tools.

Benchmark somewhere else.

Perform security testing using different scripts.

Manage datasets manually.

Track experiments in spreadsheets.

RedForge brings the **entire Local AI workflow into one application**.

From downloading a model to training, benchmarking, evaluating, securing, and exporting it—everything happens inside one professional workspace.

---

# ✨ Features

# 🧠 AI Studio

Your workspace for Local AI projects.

Organize everything related to an AI project in one place.

- Projects
- Models
- Datasets
- Experiments
- Benchmarks
- Reports
- Evaluations
- Training Runs
- Security Assessments

---

# 🤖 Model Hub

Browse, download and manage AI models directly inside RedForge.

No terminal required.

Supported sources include:

- Hugging Face
- Ollama
- GGUF Models
- Future providers

Browse models by:

- Small Models
- Coding Models
- Chat Models
- Vision Models
- Embedding Models
- Fine-tuning Friendly Models

Each model displays:

- Parameters
- Download Size
- VRAM Requirements
- RAM Requirements
- Training Suitability
- Benchmark Suitability
- Recommended Hardware

---

# ⚙ Runtime Manager

One unified runtime abstraction.

Supported providers include:

### Local

- Ollama
- LM Studio
- llama.cpp
- vLLM

### Cloud

- OpenAI
- Anthropic
- Gemini
- Groq
- OpenRouter

Switch between providers without changing your workflow.

---

# 💬 Playground

Experiment with prompts and models.

Features include:

- Multi-model chat
- Streaming responses
- System prompts
- Temperature
- Top-p
- Max Tokens
- Seed
- Context Management
- Conversation History

Run evaluations directly from the Playground.

---

# 📚 Dataset Lab

Create production-ready datasets.

Supports:

- CSV
- JSON
- JSONL
- TXT
- Markdown
- PDF
- DOCX

Features:

- Dataset Preview
- Quality Analysis
- Duplicate Detection
- Prompt Leakage Detection
- Language Detection
- Cleaning Pipeline
- Versioning
- Train / Validation / Test Splitting

---

# 🏋 Training Lab *(Experimental)*

Fine-tune local language models using LoRA / QLoRA.

Designed for beginner-friendly local fine-tuning.

Features:

- Guided Training Wizard
- Foundation Model Registry
- Hardware Compatibility Checks
- Live Progress Dashboard
- Loss Graphs
- Checkpoints
- Training Logs
- Artifact Tracking
- Training History

Current status:

> 🧪 Experimental

Training infrastructure continues to evolve while maintaining a production-quality user experience.

---

# 📊 Benchmark Center

Compare models using repeatable benchmarks.

Features:

- Custom Benchmark Suites
- Performance Comparison
- Side-by-side Results
- Historical Runs
- Leaderboards
- Exportable Reports

---

# 🛡 Security Center

Originally the core of RedForge.

Evaluate language models against adversarial attacks.

Includes:

- Prompt Injection
- Jailbreaks
- Roleplay
- Prompt Extraction
- RAG Attacks
- Encoding Attacks
- Multi-turn Attacks
- Policy Evasion
- Custom Attack Suites

Generate comprehensive security reports.

---

# 📈 Evaluation Engine

Automatically evaluate AI models.

Pipeline:

```
Profile

↓

Plan

↓

Execute

↓

Judge

↓

Analyze

↓

Report
```

Outputs include:

- Accuracy
- Robustness
- Security
- Reliability
- Performance
- Overall Score

---

# 📄 Reports

Generate professional reports.

Format:

- Markdown
- JSON
- PDF

Share benchmark and security results easily.

---

# 📥 Artifact Management

Track every generated artifact.

Including:

- Checkpoints
- Reports
- Benchmarks
- Training Runs
- Logs
- Datasets
- Evaluations

---

# 📌 Global Task Manager

Every long-running operation is managed centrally.

Examples:

- Model Downloads
- Training
- Benchmarks
- Evaluations
- Dataset Imports
- Security Scans

Background execution allows you to continue working while tasks run.

---

# ⌨ Command Palette

Inspired by VS Code.

Quickly access every feature using your keyboard.

Examples:

```
> Download Model

> Train Model

> Run Benchmark

> Import Dataset

> Open Task Manager

> Generate Report

> Run Security Scan

> Restart Runtime
```

---

# 🔒 Local First

RedForge is built around one principle:

**Your AI models belong on your machine.**

By default:

- No telemetry
- No analytics
- No cloud dependency
- No accounts
- No external storage

Your projects stay on your computer.

---

# 🏗 Architecture

RedForge follows a modular architecture.

Core systems include:

- Runtime Platform
- Foundation Model Registry
- Model Hub
- Dataset Platform
- Training Platform
- Benchmark Platform
- Security Platform
- Evaluation Engine
- Experiment Tracking
- Artifact Registry
- Global Task Manager

Every subsystem is designed to be replaceable and extensible.

---

# 🛠 Tech Stack

### Frontend

- React
- TypeScript
- Vite
- Tailwind CSS
- shadcn/ui

### Backend

- Python
- FastAPI
- SQLAlchemy
- SQLite

### AI

- Ollama
- llama.cpp
- LM Studio
- Hugging Face
- Unsloth
- Transformers

---

# 🎯 Who is RedForge for?

- AI Developers
- Machine Learning Engineers
- Students
- Researchers
- Security Engineers
- Prompt Engineers
- Open Source Contributors
- Local AI Enthusiasts

---

# 🚧 Roadmap

## Version 1.0

- AI Studio
- Model Hub
- Runtime Manager
- Playground
- Dataset Lab
- Benchmark Center
- Security Center
- Evaluation Engine
- Reports
- Global Task Manager
- Command Palette

## Version 1.1

- Improved Fine-tuning
- Distributed Training
- Better Export Pipeline
- Experiment Tracking
- Model Versioning

## Version 2.0

- AI Agents
- Workflow Automation
- Visual Pipelines
- Plugin Marketplace
- Enterprise Collaboration

---


# 🤝 Contributing

Contributions, issues, and feature requests are welcome.

Feel free to fork the repository and submit a pull request.

---

# 📄 License

MIT License

---

<p align="center">
Built for the Local AI community ❤️
</p>
