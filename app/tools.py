import base64
import datetime
import os
from typing import Any, Dict, List, Optional
import uuid
from google.adk.tools import ToolContext
from google import genai
from google.cloud import firestore
from google.cloud import storage
from google.genai import types as genai_types
import requests

PROJECT_ID = "qwiklabs-gcp-04-c4a8dc8d17a0"
BUCKET_NAME = "physiocoach-media-c4a8dc8d"
COLLECTION_NAME = "exercises"
LOGS_COLLECTION = "workout_logs"

db = firestore.Client(project=PROJECT_ID)
storage_client = storage.Client(project=PROJECT_ID)
genai_client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")


def list_exercises(target_area: Optional[str] = None, difficulty: Optional[str] = None) -> List[Dict[str, Any]]:
    """List and search physical therapy exercises from the database.

    Args:
        target_area: Optional filter for targeted body part or joint (e.g. 'lower back', 'shoulder', 'knees', 'hips', 'core').
        difficulty: Optional filter for exercise difficulty level ('Beginner', 'Intermediate', 'Advanced').

    Returns:
        A list of matching exercises with their IDs, names, target areas, difficulty, and sets/reps.
    """
    collection_ref = db.collection(COLLECTION_NAME)
    docs = collection_ref.stream()

    results = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id

        if target_area and target_area.lower() not in data.get("target_area", "").lower():
            continue
        if difficulty and difficulty.lower() != data.get("difficulty", "").lower():
            continue

        results.append(data)

    return results


def get_exercise_details(exercise_name_or_id: str) -> Dict[str, Any]:
    """Retrieve full details, instructions, and precautions for a specific exercise.

    Args:
        exercise_name_or_id: The ID or name of the exercise (e.g. 'glute-bridge', 'Glute Bridge', 'bird-dog').

    Returns:
        A dictionary containing exercise details, step-by-step instructions, and safety precautions.
    """
    collection_ref = db.collection(COLLECTION_NAME)

    # Try direct ID lookup first
    doc_ref = collection_ref.document(exercise_name_or_id.lower().replace(" ", "-"))
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        data["id"] = doc.id
        return data

    # Fallback to searching by name
    docs = collection_ref.stream()
    for doc in docs:
        data = doc.to_dict()
        if data.get("name", "").lower() == exercise_name_or_id.lower():
            data["id"] = doc.id
            return data

    return {"error": f"Exercise '{exercise_name_or_id}' not found in the database."}


def add_exercise(
    name: str,
    target_area: str,
    difficulty: str,
    equipment: str,
    sets: int,
    reps: str,
    instructions: str,
    precautions: str = "",
) -> Dict[str, Any]:
    """Add a new physical therapy exercise to the database.

    Args:
        name: Name of the exercise (e.g. 'Hamstring Stretch').
        target_area: Body area or joint targeted (e.g. 'Hamstrings / Lower Back').
        difficulty: Difficulty level ('Beginner', 'Intermediate', 'Advanced').
        equipment: Equipment required (e.g. 'Mat', 'Resistance Band', 'None').
        sets: Recommended number of sets (e.g. 3).
        reps: Recommended repetitions or hold duration (e.g. '10 reps', '30s hold').
        instructions: Clear step-by-step instructions on how to perform the exercise.
        precautions: Key safety precautions or cues to avoid pain or injury.

    Returns:
        Confirmation message and the saved exercise details.
    """
    doc_id = name.lower().strip().replace(" ", "-")
    exercise_data = {
        "id": doc_id,
        "name": name.strip(),
        "target_area": target_area.strip(),
        "difficulty": difficulty.capitalize().strip(),
        "equipment": equipment.strip(),
        "sets": sets,
        "reps": reps.strip(),
        "instructions": instructions.strip(),
        "precautions": precautions.strip(),
    }

    collection_ref = db.collection(COLLECTION_NAME)
    collection_ref.document(doc_id).set(exercise_data)

    return {
        "status": "success",
        "message": f"Exercise '{name}' successfully saved to Firestore.",
        "exercise": exercise_data,
    }


def log_workout_session(
    exercise_name: str,
    sets_completed: int,
    reps_completed: str,
    pain_score: int,
    notes: str = "",
) -> Dict[str, Any]:
    """Log a completed physical therapy or exercise session into Firestore.

    Args:
        exercise_name: Name of the exercise performed.
        sets_completed: Number of completed sets.
        reps_completed: Repetitions or duration completed per set (e.g. '10 reps', '30s hold').
        pain_score: Pain rating on a scale from 0 (no pain) to 10 (severe pain).
        notes: Optional comments on form, fatigue, or sensations.

    Returns:
        Confirmation and recorded session details with safety feedback.
    """
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    log_data = {
        "exercise_name": exercise_name.strip(),
        "sets_completed": sets_completed,
        "reps_completed": reps_completed.strip(),
        "pain_score": pain_score,
        "notes": notes.strip(),
        "timestamp": timestamp,
    }

    collection_ref = db.collection(LOGS_COLLECTION)
    doc_ref = collection_ref.document()
    doc_ref.set(log_data)
    log_data["id"] = doc_ref.id

    feedback = "Great job completing your session!"
    if pain_score >= 5:
        feedback = "Caution: Pain score is elevated (>= 5/10). Consider resting, applying ice/heat, and reducing intensity next session."
    elif pain_score >= 3:
        feedback = "Mild discomfort noted (3-4/10). Monitor symptoms and maintain steady load without increasing resistance."

    return {
        "status": "success",
        "message": f"Session for '{exercise_name}' successfully logged.",
        "feedback": feedback,
        "log": log_data,
    }


def calculate_training_load(
    sets: int,
    reps: int,
    resistance_lbs: float = 0.0,
    pain_score: int = 0,
) -> Dict[str, Any]:
    """Calculate workout volume and provide load progression recommendations.

    Args:
        sets: Number of sets.
        reps: Average repetitions per set.
        resistance_lbs: Added resistance or weight in pounds (use 0 for bodyweight exercises).
        pain_score: User's reported pain rating (0 to 10).

    Returns:
        Calculated total reps, volume load, and progression advice.
    """
    total_reps = sets * reps
    effective_load = resistance_lbs if resistance_lbs > 0 else 1.0
    volume = total_reps * effective_load

    if pain_score >= 5:
        recommendation = "Deload recommended: Reduce volume by 20-30% next session due to high pain level."
    elif pain_score >= 3:
        recommendation = "Maintain current volume: Keep sets and reps steady until pain drops below 2."
    else:
        recommendation = "Safe to progress: You may increase volume or resistance by 5-10% for the next session."

    return {
        "total_reps": total_reps,
        "volume_units": round(volume, 1),
        "pain_score": pain_score,
        "recommendation": recommendation,
    }


def lookup_muscle_anatomy(muscle_name: str) -> Dict[str, Any]:
    """Look up anatomical muscle information, location, and visual diagram URLs from the public Wger API.

    Args:
        muscle_name: The common or anatomical name of the muscle (e.g. 'glutes', 'hamstrings', 'deltoid', 'abs', 'quads', 'calves', 'biceps', 'trapezius').

    Returns:
        A dictionary with anatomical name, common name, anterior/posterior orientation, diagram SVG URL, and sample exercises.
    """
    api_key = os.environ.get("WGER_API_KEY", "")
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Token {api_key}"

    try:
        response = requests.get("https://wger.de/api/v2/muscle/", headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        return {"error": f"Failed to fetch muscle data: {e}"}

    query = muscle_name.lower().strip()
    matched = None
    for m in data.get("results", []):
        name = m.get("name", "").lower()
        name_en = m.get("name_en", "").lower()
        if query in name or (name_en and query in name_en):
            matched = m
            break

    if not matched:
        available = [m.get("name_en") or m.get("name") for m in data.get("results", [])]
        return {
            "error": f"Muscle '{muscle_name}' not found.",
            "available_muscles": available,
        }

    exercises = []
    try:
        ex_res = requests.get(
            f"https://wger.de/api/v2/exerciseinfo/?muscles={matched['id']}&limit=2",
            headers=headers,
            timeout=5,
        )
        if ex_res.status_code == 200:
            for ex in ex_res.json().get("results", []):
                for tr in ex.get("translations", []):
                    if tr.get("language") == 2 and tr.get("name"):
                        exercises.append(tr.get("name"))
    except Exception:
        pass

    return {
        "latin_name": matched.get("name"),
        "common_name": matched.get("name_en") or matched.get("name"),
        "location": "Front / Anterior" if matched.get("is_front") else "Back / Posterior",
        "diagram_url": matched.get("image_url_main"),
        "secondary_diagram_url": matched.get("image_url_secondary"),
        "sample_exercises": exercises,
    }


async def generate_exercise_pose_image(
    exercise_name: str,
    focus_pose_cue: str = "",
    tool_context: Optional[ToolContext] = None,
) -> Dict[str, Any]:
    """Generate a clean anatomical/biomechanical illustration of an exercise or body pose using gemini-3.1-flash-lite-image.

    Args:
        exercise_name: Name of the exercise or pose to illustrate (e.g. 'Glute Bridge', 'Bird Dog', 'Cat-Cow Stretch').
        focus_pose_cue: Optional posture alignment details (e.g. 'neutral spine', 'hips elevated 45 degrees', 'proper pelvic alignment').
        tool_context: ToolContext for saving the image artifact in the playground.

    Returns:
        A dictionary with the public image URL, artifact filename, and exercise details.
    """
    cue_text = f", focusing on {focus_pose_cue}" if focus_pose_cue else ""
    prompt = (
        f"A clear clinical physical therapy reference illustration of the exercise '{exercise_name}'{cue_text}. "
        "Consistent character and visual style: The same recurring character model—a fit, athletic physical therapy patient with dark hair tied back in a neat bun, wearing matching dark slate-gray athletic tank top and fitted black workout leggings with white athletic shoes. "
        "The model is on a light teal exercise mat demonstrating proper posture and biomechanics. "
        "Consistent art theme: Minimalist clean white studio background, bright uniform soft studio lighting, sharp anatomical clarity, vector-clean photorealistic illustration, full-body view showing the entire pose. "
        "Maintain strictly consistent character persona, clothing, and theme across all exercise poses. Do not change persona, hair, or outfit."
    )

    try:
        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=[prompt],
            config=genai_types.GenerateContentConfig(
                response_modalities=[genai_types.Modality.TEXT, genai_types.Modality.IMAGE],
            ),
        )
    except Exception as e:
        return {"error": f"Failed to generate pose image: {e}"}

    image_bytes = None
    mime_type = "image/jpeg"
    if response.candidates and response.candidates[0].content:
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                image_bytes = part.inline_data.data
                mime_type = part.inline_data.mime_type or "image/jpeg"
                break

    if not image_bytes:
        return {"error": "No image data was returned by gemini-3.1-flash-lite-image."}

    slug = exercise_name.lower().strip().replace(" ", "-")
    short_id = uuid.uuid4().hex[:6]
    extension = "jpg" if "jpeg" in mime_type else "png"
    artifact_filename = f"{slug}-{short_id}.{extension}"
    blob_name = f"poses/{artifact_filename}"

    # (1) Save artifact in ToolContext for Playground Artifacts panel
    if tool_context is not None:
        try:
            artifact_part = genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            await tool_context.save_artifact(filename=artifact_filename, artifact=artifact_part)
        except Exception:
            pass

    # (2) Upload to public Cloud Storage bucket without writing to local file
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(image_bytes, content_type=mime_type)
    public_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{blob_name}"

    return {
        "status": "success",
        "exercise_name": exercise_name,
        "artifact_filename": artifact_filename,
        "image_url": public_url,
        "message": f"Pose illustration for '{exercise_name}' generated and uploaded.",
    }


async def generate_exercise_demo_video(
    exercise_name: str,
    focus_cues: Optional[str] = None,
    tool_context: Optional[ToolContext] = None,
) -> Dict[str, Any]:
    """Generate a short physical therapy exercise form demonstration video using Google's Omni model (gemini-omni-flash-preview).

    Args:
        exercise_name: The name of the exercise to demonstrate (e.g. 'Glute Bridge', 'Bird Dog', 'Cat-Cow').
        focus_cues: Optional specific physical therapy movement cues to emphasize in the video demo.
        tool_context: ToolContext passed automatically by the ADK framework to persist artifacts.

    Returns:
        A dictionary containing the generated video's Cloud Storage public URL and artifact details.
    """
    cues_text = f" Emphasize proper form and alignment: {focus_cues}." if focus_cues else ""
    prompt = (
        f"A clear 4-second physical therapy demonstration video of an athletic person performing the '{exercise_name}' exercise on an exercise mat in a clean, brightly lit rehabilitation clinic studio.{cues_text} Smooth, controlled, safe movement with proper spinal alignment and joint mechanics."
    )

    try:
        interaction = genai_client.interactions.create(
            model="gemini-omni-flash-preview",
            input=prompt,
        )
    except Exception as e:
        return {"error": f"Failed to generate video with gemini-omni-flash-preview: {str(e)}"}

    video_bytes = None
    mime_type = "video/mp4"

    if hasattr(interaction, "output_video") and interaction.output_video:
        video_data = interaction.output_video.data
        if isinstance(video_data, str):
            video_bytes = base64.b64decode(video_data)
        elif isinstance(video_data, bytes):
            video_bytes = video_data
        mime_type = getattr(interaction.output_video, "mime_type", "video/mp4") or "video/mp4"

    if not video_bytes and hasattr(interaction, "steps"):
        for step in interaction.steps:
            if getattr(step, "type", "") == "model_output":
                for item in getattr(step, "content", []):
                    if getattr(item, "type", "") == "video":
                        data_val = getattr(item, "data", None)
                        if data_val:
                            video_bytes = base64.b64decode(data_val) if isinstance(data_val, str) else data_val
                            mime_type = getattr(item, "mime_type", "video/mp4") or "video/mp4"
                            break

    if not video_bytes:
        return {"error": "No video data was returned by gemini-omni-flash-preview."}

    slug = exercise_name.lower().strip().replace(" ", "-")
    short_id = uuid.uuid4().hex[:6]
    artifact_filename = f"{slug}-demo-{short_id}.mp4"
    blob_name = f"videos/{artifact_filename}"
    bucket_name = "physiocoach-media-c4a8dc8d"

    # (1) Save artifact in ToolContext for Playground Artifacts panel
    if tool_context is not None:
        try:
            artifact_part = genai_types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
            await tool_context.save_artifact(filename=artifact_filename, artifact=artifact_part)
        except Exception:
            pass

    # (2) Upload to public Cloud Storage bucket without writing to local file
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(video_bytes, content_type=mime_type)
    public_url = f"https://storage.googleapis.com/{bucket_name}/{blob_name}"

    return {
        "status": "success",
        "exercise_name": exercise_name,
        "artifact_filename": artifact_filename,
        "video_url": public_url,
        "mime_type": mime_type,
        "message": f"Demonstration video for '{exercise_name}' generated and uploaded successfully.",
    }
