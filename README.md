<<<<<<< HEAD
---
title: Beacon Trial Finder
emoji: 📚
colorFrom: gray
colorTo: yellow
sdk: gradio
sdk_version: 6.14.0
python_version: '3.13'
app_file: app.py
pinned: false
license: mit
short_description: help patients with rare disease to find clinical trials
---

=======
>>>>>>> 6977736 (Initial release: Beacon rare disease clinical trial finder)
# Beacon — Rare Disease Clinical Trial Finder

Beacon is a conversational AI assistant that helps patients with rare diseases find relevant recruiting clinical trials near them. It conducts a warm intake interview, geocodes the patient's location, queries [ClinicalTrials.gov](https://clinicaltrials.gov) in real time, and produces a ranked report of the closest matching trials.

## How it works

<<<<<<< HEAD
1. **Intake agent** (Claude Sonnet) — interviews the patient conversationally to collect disease, age, symptom onset date, formal diagnosis date, location, preferred trial phases, and whether they are interested in Expanded Access Programs (EAP / compassionate use).
2. **Research agent** (Claude Opus) — searches ClinicalTrials.gov via the official v2 API for clinical trials and/or EAP listings, retrying with synonyms or wider radii if results are sparse, then outputs a ranked report with eligibility notes and next steps.
3. **LangGraph** orchestrates the two-node pipeline (intake → research).

### Clinical trial phases explained

| Phase | Focus | Typical size |
|---|---|---|
| **Early Phase 1** | First-in-human safety; tiny doses | ~10–15 people |
| **Phase 1** | Safe dosage range and side effects | 20–80 people |
| **Phase 2** | Does it work? Continued safety | 100–300 people |
| **Phase 3** | vs. standard of care; required for FDA approval | 1,000–3,000 people |
| **Phase 4** | Post-approval long-term surveillance | Varies |

### Expanded Access Programs (EAP)

EAP (also called compassionate use) allows patients who do not qualify for or cannot access a clinical trial to receive an investigational drug or device outside of a formal trial. The treatment is not yet FDA-approved; a physician must submit the EAP request to the drug sponsor and obtain FDA authorization. Beacon can search for available EAP listings alongside clinical trials.

=======
1. **Intake agent** (Claude Sonnet) — interviews the patient conversationally to collect disease, age, symptom onset, location, and optional benchmark scores.
2. **Research agent** (Claude Opus) — searches ClinicalTrials.gov via the official v2 API, retrying with synonyms or wider radii if results are sparse, then outputs a ranked trial report with eligibility notes and next steps.
3. **LangGraph** orchestrates the two-node pipeline (intake → research).

>>>>>>> 6977736 (Initial release: Beacon rare disease clinical trial finder)
## Project setup

### Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `pip`

### 1. Clone the repo

```bash
git clone <repo-url>
cd beacon
```

### 2. Install dependencies

```bash
uv sync
```

Or with pip:

```bash
pip install -e .
```

### 3. Configure API keys

Copy the example env file and fill in your keys:

```bash
cp .env.example .env
```

Open `.env` and replace the placeholder values:

```env
<<<<<<< HEAD
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

### 4. Run

```bash
uv run python app.py
```

#### Hot-reload during development

Use the `gradio` CLI to automatically reload the app whenever you save a file — no manual restart needed:

```bash
uv run gradio app.py
```

> **Note:** Active user sessions are reset on each reload.

## Configuration

| Environment variable | Default     | Description       |
|----------------------|-------------|-------------------|
| `ANTHROPIC_API_KEY`  | *(required)*| Anthropic API key |
=======
# ⚠️  Replace with your actual API keys — never commit real keys to version control
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

- Get your Anthropic key at <https://console.anthropic.com>
- Get your OpenAI key at <https://platform.openai.com/api-keys>

### 4. Run

```bash
uv run python main.py
```

Or if using a plain virtualenv:

```bash
python main.py
```

## Configuration

| Environment variable | Default     | Description                                      |
|----------------------|-------------|--------------------------------------------------|
| `ANTHROPIC_API_KEY`  | *(required)*| Anthropic API key                                |
| `OPENAI_API_KEY`     | *(optional)*| OpenAI API key (only needed for OpenAI provider) |
| `LLM_PROVIDER`       | `anthropic` | LLM backend: `anthropic` or `openai`             |

To switch to the OpenAI backend, set `LLM_PROVIDER=openai` in `.env`.
>>>>>>> 6977736 (Initial release: Beacon rare disease clinical trial finder)

## Project structure

```
beacon/
<<<<<<< HEAD
├── app.py                   # Gradio web UI entry point
├── main.py                  # Terminal entry point
├── clinical_trials_guru.py  # Intake + research agents, LangGraph pipeline
├── llm.py                   # LLM provider abstraction
├── requirements.txt         # HuggingFace Spaces dependencies
├── pyproject.toml
└── .env                     # Local secrets — not committed
```
=======
├── main.py                  # Entry point
├── clinical_trials_guru.py  # Intake + research agents, LangGraph pipeline
├── llm.py                   # LLM provider abstraction (Anthropic / OpenAI)
├── pyproject.toml
├── .env                     # Local secrets — not committed
└── .gitignore
```

## Dependencies

| Package          | Purpose                              |
|------------------|--------------------------------------|
| `anthropic`      | Claude API client                    |
| `openai`         | OpenAI API client                    |
| `langgraph`      | Agent pipeline orchestration         |
| `rich`           | Terminal UI (panels, markdown, etc.) |
| `python-dotenv`  | `.env` file loading                  |
| `httpx`          | HTTP client for ClinicalTrials.gov   |
>>>>>>> 6977736 (Initial release: Beacon rare disease clinical trial finder)
