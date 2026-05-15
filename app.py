from __future__ import annotations

import datetime
import json
from typing import Generator

import anthropic
import gradio as gr
from dotenv import load_dotenv

from clinical_trials_guru import (
    INTAKE_MODEL,
    INTAKE_SYSTEM,
    RESEARCH_MODEL,
    RESEARCH_SYSTEM,
    SEARCH_TRIALS_TOOL,
    SUBMIT_PROFILE_TOOL,
    PatientProfile,
    _flatten_and_rank,
    geocode_zip,
    search_trials_api,
)

load_dotenv()


def _intake_turn(
    user_text: str, messages: list
) -> tuple[str, list, PatientProfile | None]:
    today = datetime.date.today().strftime("%B %d, %Y")
    messages = messages + [{"role": "user", "content": user_text}]
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=INTAKE_MODEL,
        max_tokens=1024,
        system=f"Today's date is {today}.\n\n" + INTAKE_SYSTEM,
        tools=[SUBMIT_PROFILE_TOOL],
        messages=messages,
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    tool_block = next(
        (b for b in response.content if b.type == "tool_use" and b.name == "submit_profile"),
        None,
    )
    messages = messages + [{"role": "assistant", "content": response.content}]

    if tool_block:
        data = tool_block.input
        try:
            lat, lon = geocode_zip(data["zip_code"], data.get("country_code", "US"))
        except Exception:
            lat, lon = 0.0, 0.0
        profile = PatientProfile(
            disease=data["disease"],
            age=data["age"],
            onset_months=data["onset_months"],
            benchmarks=data.get("benchmarks") or {},
            zip_code=data["zip_code"],
            country_code=data.get("country_code", "US"),
            lat=lat,
            lon=lon,
            radius_miles=data.get("radius_miles", 100),
            phases=data.get("phases") or [],
        )
        return text or "Got it — searching for trials now…", messages, profile

    return text, messages, None


def _run_research(profile: PatientProfile) -> str:
    client = anthropic.Anthropic()
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
            try:
                studies = search_trials_api(
                    condition=args["condition"],
                    lat=args["lat"],
                    lon=args["lon"],
                    radius_miles=args.get("radius_miles", profile.radius_miles),
                    phases=args.get("phases") or None,
                    max_results=args.get("max_results", 20),
                )
                ranked = _flatten_and_rank(studies, profile.lat, profile.lon)
                content = json.dumps(ranked)
                is_error = False
            except Exception as exc:
                content = f"API request failed: {exc}"
                is_error = True
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": tool_results})


def initialize():
    text, msgs, _ = _intake_turn("Please begin.", [])
    chat = [{"role": "assistant", "content": text}]
    # Strip the seed "Please begin." turn so subsequent user messages append cleanly.
    # msgs already includes both the seed user turn and the assistant turn; keep it.
    return chat, msgs, None, "intake"


def respond(
    user_msg: str,
    chat_history: list,
    intake_msgs: list,
    profile,
    phase: str,
) -> Generator:
    if not user_msg.strip() or phase == "done":
        yield chat_history, intake_msgs, profile, phase, gr.update(), gr.update()
        return

    chat_history = chat_history + [{"role": "user", "content": user_msg}]
    yield chat_history, intake_msgs, profile, phase, gr.update(value=""), gr.update()

    assistant_text, updated_msgs, new_profile = _intake_turn(user_msg, intake_msgs)

    if new_profile:
        status = (assistant_text + "\n\n" if assistant_text else "") + (
            "*Searching ClinicalTrials.gov — this may take a minute…*"
        )
        chat_history = chat_history + [{"role": "assistant", "content": status}]
        yield (
            chat_history,
            updated_msgs,
            new_profile,
            "researching",
            gr.update(interactive=False, placeholder="Searching…"),
            gr.update(visible=False),
        )

        analysis = _run_research(new_profile)
        chat_history = chat_history + [{"role": "assistant", "content": analysis}]
        yield (
            chat_history,
            updated_msgs,
            new_profile,
            "done",
            gr.update(interactive=False, placeholder="Search complete."),
            gr.update(visible=True),
        )
    else:
        chat_history = chat_history + [{"role": "assistant", "content": assistant_text}]
        yield (
            chat_history,
            updated_msgs,
            profile,
            "intake",
            gr.update(),
            gr.update(),
        )


with gr.Blocks(title="Beacon — Clinical Trial Finder") as demo:
    gr.Markdown("# 🔦 Beacon — Rare Disease Clinical Trial Finder")

    chatbot = gr.Chatbot(height=550, show_label=False)
    with gr.Row():
        msg_box = gr.Textbox(
            placeholder="Type your message and press Enter…",
            show_label=False,
            scale=9,
            autofocus=True,
        )
        send_btn = gr.Button("Send", scale=1, variant="primary")
    new_search_btn = gr.Button("New Search", visible=False, variant="secondary")

    # State
    intake_msgs_state = gr.State([])
    profile_state = gr.State(None)
    phase_state = gr.State("intake")

    outputs = [chatbot, intake_msgs_state, profile_state, phase_state, msg_box, new_search_btn]

    demo.load(
        initialize,
        outputs=[chatbot, intake_msgs_state, profile_state, phase_state],
    )

    msg_box.submit(respond, [msg_box, chatbot, intake_msgs_state, profile_state, phase_state], outputs)
    send_btn.click(respond, [msg_box, chatbot, intake_msgs_state, profile_state, phase_state], outputs)

    new_search_btn.click(
        initialize,
        outputs=[chatbot, intake_msgs_state, profile_state, phase_state],
    ).then(
        lambda: (gr.update(interactive=True, placeholder="Type your message and press Enter…"), gr.update(visible=False)),
        outputs=[msg_box, new_search_btn],
    )


if __name__ == "__main__":
    demo.launch()
