# Beacon — Rare Disease Clinical Trial Finder

Beacon is a conversational AI assistant that helps patients with rare diseases find relevant recruiting clinical trials near them. It conducts a warm intake interview, geocodes the patient's location, queries [ClinicalTrials.gov](https://clinicaltrials.gov) in real time, and produces a ranked report of the closest matching trials.

## How it works

1. **Intake agent** (Claude Sonnet) — interviews the patient conversationally to collect disease, age, symptom onset, location, and optional benchmark scores.
2. **Research agent** (Claude Opus) — searches ClinicalTrials.gov via the official v2 API, retrying with synonyms or wider radii if results are sparse, then outputs a ranked trial report with eligibility notes and next steps.
3. **LangGraph** orchestrates the two-node pipeline (intake → research).

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

## Project structure

```
beacon/
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
