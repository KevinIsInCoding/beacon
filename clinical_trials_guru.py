from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from typing import Optional, TypedDict

import anthropic
import httpx
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from langgraph.graph import StateGraph, START, END

CTGOV_BASE = "https://clinicaltrials.gov/api/v2/studies"
INTAKE_MODEL = "claude-sonnet-4-6"
RESEARCH_MODEL = "claude-opus-4-7"

console = Console()

# ── Tool schemas ──────────────────────────────────────────────────────────────

SUBMIT_PROFILE_TOOL: anthropic.types.ToolParam = {
    "name": "submit_profile",
    "description": (
        "Call this when you have collected all required information. "
        "Standardize the disease name to its full medical term."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "disease": {
                "type": "string",
                "description": "Full medical name (e.g. 'Amyotrophic Lateral Sclerosis')",
            },
            "age": {"type": "integer"},
            "onset_months": {
                "type": "integer",
                "description": "Months since first symptom onset",
            },
            "diagnosis_months": {
                "type": "integer",
                "description": "Months since formal/official diagnosis",
            },
            "benchmarks": {
                "type": "object",
                "description": "Disease-specific scores, e.g. {\"ALSFRS-R\": \"38\"}",
                "additionalProperties": {"type": "string"},
            },
            "zip_code": {"type": "string", "description": "Patient ZIP / postal code"},
            "country_code": {
                "type": "string",
                "description": "ISO 2-letter country code (default US)",
            },
            "radius_miles": {
                "type": "integer",
                "description": "Search radius in miles from patient location (default 100)",
            },
            "phases": {
                "type": "array",
                "items": {"type": "string", "enum": ["0", "1", "2", "3", "4"]},
                "description": "Desired trial phases. Empty = all phases.",
            },
            "include_eap": {
                "type": "boolean",
                "description": "Whether patient is interested in Expanded Access Programs (compassionate use)",
            },
        },
        "required": ["disease", "age", "onset_months", "diagnosis_months", "zip_code"],
    },
}

SEARCH_TRIALS_TOOL: anthropic.types.ToolParam = {
    "name": "search_clinical_trials",
    "description": (
        "Search ClinicalTrials.gov for studies within a geographic radius. "
        "Results are pre-ranked by distance from the patient's location. "
        "Call multiple times with different parameters (synonyms, broader radius, "
        "different phases) if initial results are sparse. "
        "Use study_type='EXPANDED_ACCESS' to search for Expanded Access Programs (EAP / compassionate use)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "condition": {
                "type": "string",
                "description": "Disease / condition to search (medical name and/or abbreviation)",
            },
            "lat": {"type": "number", "description": "Patient latitude"},
            "lon": {"type": "number", "description": "Patient longitude"},
            "radius_miles": {"type": "integer", "description": "Search radius in miles"},
            "phases": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Phase numbers to filter ['1','2','3']. Empty = all. Ignored for EAP.",
            },
            "study_type": {
                "type": "string",
                "enum": ["INTERVENTIONAL", "EXPANDED_ACCESS"],
                "description": "INTERVENTIONAL (default) for clinical trials; EXPANDED_ACCESS for EAP/compassionate use.",
            },
            "max_results": {"type": "integer", "description": "Max trials to return (default 20)"},
        },
        "required": ["condition", "lat", "lon", "radius_miles"],
    },
}

# ── System prompts ────────────────────────────────────────────────────────────

INTAKE_SYSTEM = """\
You are Beacon's patient intake specialist for rare disease clinical trials.
Collect the following through a warm, conversational interview — do NOT present a form.

REQUIRED:
  • Disease/condition (standardize: "Lou Gehrig's" → "Amyotrophic Lateral Sclerosis")
  • Patient age
  • Months since first symptom onset (convert dates/years as needed)
  • Months since formal/official diagnosis (convert dates/years as needed; may differ from onset)
  • ZIP/postal code and country for geographic search

OPTIONAL (ask based on disease):
  • Disease-specific benchmark scores:
      ALS → ALSFRS-R (0-48); MS → EDSS (0-10); Parkinson's → MDS-UPDRS III;
      Huntington's → TFC (0-13) + CAG repeats; SMA → HFMS + SMA type;
      Duchenne/Pompe → 6-Minute Walk Test; Friedreich's → SARA score
  • Preferred search radius in miles (default 100)
  • Study types of interest — ask whether the patient wants:
      - Clinical trials (phases 1 / 2 / 3 / 4 / early phase 1)
      - Expanded Access Programs (EAP / compassionate use) — for patients who may not
        qualify for a trial but want access to an investigational treatment
      - Or both

Ask naturally. Infer what you can. Once you have the required fields, call submit_profile.\
"""

RESEARCH_SYSTEM = """\
You are Beacon, an expert rare-disease clinical trial navigator.
You have a search_clinical_trials tool that queries ClinicalTrials.gov in real time.
Results are already ranked by geographic distance from the patient.

Workflow:
1. Search for the patient's disease. Use both the full medical name and common abbreviation.
   - If the patient wants clinical trials, search with study_type="INTERVENTIONAL".
   - If the patient wants Expanded Access Programs (EAP), also search with study_type="EXPANDED_ACCESS".
   - If the patient wants both, run separate searches for each study_type.
2. If fewer than 3 results are found, retry with: a wider radius, a disease synonym,
   or fewer phase filters.
3. Produce a final report. Use separate sections for Clinical Trials and Expanded Access if both apply.
   List the top 5 results per section ranked by site proximity.
   For EACH entry use exactly this format (repeat the block per entry):

   📍 **[Closest hospital name]** — [City, State] ([X] mi)
   **Trial:** [Full title] ([Phase] — or "Expanded Access" for EAP)
   **Sponsor:** [Lead sponsor]
   **Summary:** [2–3 sentence plain-language description of what the trial/program is testing
               and why it may matter for this patient]
   **Eligibility notes:** [Key inclusion/exclusion criteria relevant to this patient,
                         including any red flags]
   **Link:** https://clinicaltrials.gov/study/[NCT_ID]

   ---

4. After the results add a short "Next steps" section (bullet points).
   For EAP results, note that patients typically need a physician to submit the EAP request.

Be accurate. Do not fabricate details. If data is missing, say so.\
"""

# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class PatientProfile:
    disease: str
    age: int
    onset_months: int
    diagnosis_months: int = 0
    benchmarks: dict[str, str] = field(default_factory=dict)
    zip_code: str = ""
    country_code: str = "US"
    lat: float = 0.0
    lon: float = 0.0
    radius_miles: int = 100
    phases: list[str] = field(default_factory=list)
    include_eap: bool = False

    def summary(self) -> str:
        lines = [
            f"Disease: {self.disease}",
            f"Age: {self.age}",
            f"Symptom onset: {self.onset_months} months ago",
            f"Formal diagnosis: {self.diagnosis_months} months ago",
        ]
        if self.benchmarks:
            lines.append("Benchmarks: " + ", ".join(f"{k}={v}" for k, v in self.benchmarks.items()))
        lines.append(
            f"Location: ZIP {self.zip_code}, {self.country_code} "
            f"(lat={self.lat:.4f}, lon={self.lon:.4f})"
        )
        lines.append(f"Search radius: {self.radius_miles} miles")
        if self.phases:
            labels = ["Early Phase 1" if p == "0" else f"Phase {p}" for p in self.phases]
            lines.append(f"Phases: {', '.join(labels)}")
        interests = ["Clinical trials"]
        if self.include_eap:
            interests.append("Expanded Access Programs (EAP)")
        lines.append(f"Study type interest: {', '.join(interests)}")
        return "\n".join(lines)


# ── Geocoding ─────────────────────────────────────────────────────────────────

def geocode_zip(zip_code: str, country_code: str = "US") -> tuple[float, float]:
    resp = httpx.get(
        "https://nominatim.openstreetmap.org/search",
        params={"postalcode": zip_code, "country": country_code, "format": "json", "limit": 1},
        headers={"User-Agent": "Beacon-ClinicalTrialFinder/1.0"},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise ValueError(f"Cannot geocode ZIP {zip_code!r} in {country_code!r}")
    return float(results[0]["lat"]), float(results[0]["lon"])


# ── Distance ──────────────────────────────────────────────────────────────────

def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ, dλ = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── ClinicalTrials.gov ────────────────────────────────────────────────────────

def search_trials_api(
    condition: str,
    lat: float,
    lon: float,
    radius_miles: int = 100,
    phases: list[str] | None = None,
    study_type: str = "INTERVENTIONAL",
    max_results: int = 20,
) -> list[dict]:
    is_eap = study_type == "EXPANDED_ACCESS"
    params: dict[str, str | int] = {
        "query.cond": condition,
        "filter.overallStatus": "AVAILABLE" if is_eap else "RECRUITING",
        "filter.studyType": study_type,
        "filter.geo": f"distance({lat},{lon},{radius_miles}mi)",
        "pageSize": max_results,
        "format": "json",
    }
    if phases and not is_eap:
        params["aggFilters"] = "phase:" + " ".join(phases)
    for attempt in range(3):
        try:
            resp = httpx.get(CTGOV_BASE, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json().get("studies", [])
        except httpx.HTTPError as exc:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            console.print(f"[yellow]API warning:[/yellow] {exc} — retrying in {wait}s (attempt {attempt + 1}/3)…")
            time.sleep(wait)


def _flatten_and_rank(studies: list[dict], patient_lat: float, patient_lon: float) -> list[dict]:
    result = []
    for study in studies:
        proto = study.get("protocolSection", {})
        id_mod = proto.get("identificationModule", {})
        desc_mod = proto.get("descriptionModule", {})
        elig_mod = proto.get("eligibilityModule", {})
        contacts_mod = proto.get("contactsLocationsModule", {})
        sponsor_mod = proto.get("sponsorCollaboratorsModule", {})
        design_mod = proto.get("designModule", {})

        sites_with_dist: list[tuple[float, str]] = []
        for loc in contacts_mod.get("locations", []):
            geo = loc.get("geoPoint", {})
            if geo.get("lat") and geo.get("lon"):
                d = haversine_miles(patient_lat, patient_lon, geo["lat"], geo["lon"])
                label = (
                    f"{loc.get('facility', '').strip()} — "
                    f"{loc.get('city', '')}, "
                    f"{loc.get('state', loc.get('country', ''))} "
                    f"({d:.0f} mi)"
                )
                sites_with_dist.append((d, label))
        sites_with_dist.sort(key=lambda x: x[0])

        closest_dist = sites_with_dist[0][0] if sites_with_dist else None
        result.append({
            "nct_id": id_mod.get("nctId", ""),
            "title": id_mod.get("briefTitle", ""),
            "phase": ", ".join(design_mod.get("phases", [])) or "N/A",
            "sponsor": sponsor_mod.get("leadSponsor", {}).get("name", ""),
            "summary": desc_mod.get("briefSummary", "")[:500],
            "eligibility": elig_mod.get("eligibilityCriteria", "")[:1000],
            "min_age": elig_mod.get("minimumAge", ""),
            "max_age": elig_mod.get("maximumAge", ""),
            "closest_site_miles": round(closest_dist, 1) if closest_dist is not None else None,
            "nearest_sites": [label for _, label in sites_with_dist[:5]],
        })

    result.sort(key=lambda x: x["closest_site_miles"] if x["closest_site_miles"] is not None else float("inf"))
    return result


# ── Intake agent ──────────────────────────────────────────────────────────────

def run_intake_agent(client: anthropic.Anthropic) -> PatientProfile:
    import datetime
    today = datetime.date.today().strftime("%B %d, %Y")

    console.print()
    console.print(Panel(
        Text("Beacon — Rare Disease Clinical Trial Finder", justify="center", style="bold cyan"),
        border_style="cyan",
        padding=(1, 4),
    ))

    messages: list[anthropic.types.MessageParam] = [
        {"role": "user", "content": "Please begin."}
    ]

    while True:
        response = client.messages.create(
            model=INTAKE_MODEL,
            max_tokens=1024,
            system=f"Today's date is {today}.\n\n" + INTAKE_SYSTEM,
            tools=[SUBMIT_PROFILE_TOOL],
            messages=messages,
        )

        text = next((b.text for b in response.content if b.type == "text"), "")
        if text:
            console.print(f"\n[bold cyan]Beacon:[/bold cyan] {text}")

        tool_block = next(
            (b for b in response.content if b.type == "tool_use" and b.name == "submit_profile"),
            None,
        )
        if tool_block:
            data = tool_block.input
            try:
                with console.status("[cyan]Geocoding location…[/cyan]", spinner="dots"):
                    lat, lon = geocode_zip(data["zip_code"], data.get("country_code", "US"))
            except Exception as exc:
                console.print(f"[yellow]Warning:[/yellow] Geocoding failed ({exc}) — coordinates set to 0,0.")
                lat, lon = 0.0, 0.0
            return PatientProfile(
                disease=data["disease"],
                age=data["age"],
                onset_months=data["onset_months"],
                diagnosis_months=data.get("diagnosis_months", 0),
                benchmarks=data.get("benchmarks") or {},
                zip_code=data["zip_code"],
                country_code=data.get("country_code", "US"),
                lat=lat,
                lon=lon,
                radius_miles=data.get("radius_miles", 100),
                phases=data.get("phases") or [],
                include_eap=data.get("include_eap", False),
            )

        messages.append({"role": "assistant", "content": response.content})
        user_input = input("\nYou: ").strip() or "(no response)"
        messages.append({"role": "user", "content": user_input})


# ── Research agent ────────────────────────────────────────────────────────────

def run_research_agent(client: anthropic.Anthropic, profile: PatientProfile) -> str:
    messages: list[anthropic.types.MessageParam] = [
        {
            "role": "user",
            "content": (
                f"Find clinical trials for this patient:\n\n{profile.summary()}\n\n"
                "Search within the specified radius and rank results by distance."
            ),
        }
    ]

    while True:
        response = client.messages.create(
            model=RESEARCH_MODEL,
            max_tokens=8096,
            system=RESEARCH_SYSTEM,
            tools=[SEARCH_TRIALS_TOOL],
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            return next(
                (b.text for b in response.content if b.type == "text"),
                "No analysis produced.",
            )

        tool_results: list[anthropic.types.ToolResultBlockParam] = []
        for block in response.content:
            if block.type != "tool_use" or block.name != "search_clinical_trials":
                continue
            args = block.input
            radius = args.get("radius_miles", profile.radius_miles)
            phases = args.get("phases") or None
            study_type = args.get("study_type", "INTERVENTIONAL")
            status_msg = (
                f"[cyan]Searching:[/cyan] '[bold]{args['condition']}[/bold]' | "
                f"radius=[bold]{radius}[/bold] mi | "
                f"type=[bold]{study_type}[/bold] | "
                f"phases=[bold]{phases or 'all'}[/bold]"
            )
            try:
                with console.status(status_msg, spinner="dots"):
                    studies = search_trials_api(
                        condition=args["condition"],
                        lat=args["lat"],
                        lon=args["lon"],
                        radius_miles=radius,
                        phases=phases,
                        study_type=study_type,
                        max_results=args.get("max_results", 20),
                    )
                    ranked = _flatten_and_rank(studies, profile.lat, profile.lon)
                console.print(f"  [green]✓[/green] {len(ranked)} trial(s) found.")
                content = json.dumps(ranked)
                is_error = False
            except Exception as exc:
                console.print(f"[red bold]API error:[/red bold] {exc}")
                content = f"API request failed: {exc}. The ClinicalTrials.gov endpoint may be temporarily unavailable."
                is_error = True
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": content,
                "is_error": is_error,
            })

        messages.append({"role": "user", "content": tool_results})


# ── LangGraph ─────────────────────────────────────────────────────────────────

class BeaconState(TypedDict):
    profile: Optional[PatientProfile]
    analysis: str


def _build_graph(client: anthropic.Anthropic):
    def intake_node(_state: BeaconState) -> BeaconState:
        return {"profile": run_intake_agent(client), "analysis": ""}

    def research_node(state: BeaconState) -> BeaconState:
        analysis = run_research_agent(client, state["profile"])
        console.print()
        console.print(Panel(
            Markdown(analysis),
            title="[bold cyan]BEACON ANALYSIS[/bold cyan]",
            border_style="cyan",
            box=box.DOUBLE_EDGE,
            padding=(1, 2),
        ))
        console.print()
        return {"analysis": analysis}

    graph = StateGraph(BeaconState)
    graph.add_node("intake", intake_node)
    graph.add_node("research", research_node)
    graph.add_edge(START, "intake")
    graph.add_edge("intake", "research")
    graph.add_edge("research", END)
    return graph.compile()


def guru_main(_provider=None):  # _provider kept for backward-compat, unused
    client = anthropic.Anthropic()
    graph = _build_graph(client)
    try:
        graph.invoke({"profile": None, "analysis": ""})
    except (KeyboardInterrupt, EOFError):
        console.print("\n[dim]Goodbye.[/dim]")
        return
    console.print("\n[bold]Goodbye.[/bold] Beacon wishes the patient the best on their journey.")
