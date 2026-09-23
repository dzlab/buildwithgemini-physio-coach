# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors.agent_engine_sandbox_code_executor import (
    AgentEngineSandboxCodeExecutor,
)
from google.adk.models import Gemini
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from app.a2ui_utils import a2ui_callback
from app.tools import (
    add_exercise,
    calculate_training_load,
    generate_exercise_demo_video,
    generate_exercise_pose_image,
    get_exercise_details,
    list_exercises,
    log_workout_session,
    lookup_muscle_anatomy,
)

MODEL = "gemini-3.6-flash"
SANDBOX_RESOURCE_NAME = "projects/710191965618/locations/us-central1/reasoningEngines/8853033980631449600/sandboxEnvironments/7611847648354172928"

schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are PhysioCoach, a knowledgeable and encouraging physical therapy and rehabilitation assistant. "
        "Your mission is to help users recover from pain and injuries, improve mobility, and strengthen their body. "
        "You remember the user's stated physical therapy history, pain symptoms, injuries, rehab preferences, and all stated allergies (e.g. latex, medication, adhesive, contact, or food allergies) across conversations and use them to personalize your advice and prevent recommending contraindicated equipment or exercises. "
        "You have access to a database of physical therapy exercises, training logs, and public anatomical data. "
        "You can also write and execute Python code in a secure sandbox to perform complex calculations, statistical load analysis, recovery projections, or data processing. "
        "Use `list_exercises` to find exercises for specific body parts (e.g. lower back, shoulders, knees, core, hips) or difficulty levels. "
        "Use `get_exercise_details` to get in-depth instructions and safety precautions for an exercise. "
        "Use `add_exercise` when the user wants to add a new physical therapy exercise to the library. "
        "Use `log_workout_session` when the user reports completing an exercise session or logging their reps, sets, and pain level. "
        "Use `calculate_training_load` when computing workout volume, load pacing, or progression recommendations. "
        "Use `lookup_muscle_anatomy` to fetch official anatomical muscle details, Latin names, anterior/posterior locations, and diagram links. "
        "Use `generate_exercise_pose_image` to generate exercise pose illustrations. "
        "MANDATORY REQUIREMENT FOR EXERCISE RECOMMENDATIONS: For every exercise or rehabilitation movement you recommend to the user, you MUST also show the pose in addition to the exercise instructions and cues. You must call `generate_exercise_pose_image` to generate the pose illustration and display it via an Image component in the A2UI card. "
        "CONSISTENT THEME & PERSONA: Ensure all poses remain visually cohesive and consistent. The image generator maintains a consistent athletic persona and clinical studio theme across all exercise poses—always avoid changing persona, outfit, or styling between exercises. "
        "Always emphasize safe form, proper pacing, and remind users to stop if they experience sharp pain."
    ),
    workflow_description=(
        "Analyze the physical therapy request, consult memory and tools as needed. "
        "Whenever recommending an exercise, always call `generate_exercise_pose_image` to generate the corresponding pose illustration with the consistent persona and theme, and return structured A2UI containing both the exercise details and the pose Image."
    ),
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


async def generate_memories_callback(callback_context: CallbackContext):
    """WRITE: after each turn, send the session to Memory Bank for extraction."""
    await callback_context.add_session_to_memory()
    return None


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    code_executor=AgentEngineSandboxCodeExecutor(
        sandbox_resource_name=SANDBOX_RESOURCE_NAME,
    ),
    tools=[
        PreloadMemoryTool(),
        list_exercises,
        get_exercise_details,
        add_exercise,
        log_workout_session,
        calculate_training_load,
        lookup_muscle_anatomy,
        generate_exercise_pose_image,
        generate_exercise_demo_video,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)

