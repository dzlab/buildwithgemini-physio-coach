#!/usr/bin/env python3
"""Seed script to populate Firestore with initial Physical Therapy exercises."""

from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-04-c4a8dc8d17a0"

SEED_EXERCISES = [
    {
        "id": "glute-bridge",
        "name": "Glute Bridge",
        "target_area": "Lower Back / Hips",
        "difficulty": "Beginner",
        "equipment": "Mat",
        "sets": 3,
        "reps": "10-12 reps",
        "instructions": "Lie on back with knees bent and feet flat on floor, hip-width apart. Squeeze glutes and raise hips until body forms a straight line from shoulders to knees. Hold 2 seconds, then slowly lower.",
        "precautions": "Avoid arching lower back excessively. Drive through heels."
    },
    {
        "id": "bird-dog",
        "name": "Bird Dog",
        "target_area": "Core / Lower Back",
        "difficulty": "Beginner",
        "equipment": "Mat",
        "sets": 3,
        "reps": "8-10 reps per side",
        "instructions": "Begin on hands and knees with hands under shoulders and knees under hips. Simultaneously extend right arm forward and left leg back until parallel with floor. Hold briefly, return, and alternate.",
        "precautions": "Keep spine neutral and hips level. Do not let lower back sag."
    },
    {
        "id": "band-pull-apart",
        "name": "Band Pull-Apart",
        "target_area": "Shoulders / Upper Back",
        "difficulty": "Beginner",
        "equipment": "Resistance Band",
        "sets": 3,
        "reps": "12-15 reps",
        "instructions": "Stand tall holding a resistance band at shoulder height with arms extended. Pull band apart horizontally by squeezing shoulder blades together until band touches chest. Slowly return to start.",
        "precautions": "Keep shoulders relaxed down away from ears. Do not arch lower back."
    },
    {
        "id": "wall-slide",
        "name": "Wall Slide with Foam Roller",
        "target_area": "Shoulders / Scapular Stability",
        "difficulty": "Intermediate",
        "equipment": "Foam Roller, Wall",
        "sets": 3,
        "reps": "8-10 reps",
        "instructions": "Place foam roller against wall at forearm height. Stand in a staggered stance, gently press forearms into roller, and slide upward while maintaining core engagement and ribs down.",
        "precautions": "Stop if you feel pinching in the shoulders. Maintain continuous gentle pressure."
    },
    {
        "id": "straight-leg-raise",
        "name": "Straight Leg Raise",
        "target_area": "Knees / Quadriceps",
        "difficulty": "Beginner",
        "equipment": "Mat",
        "sets": 3,
        "reps": "10-12 reps per leg",
        "instructions": "Lie flat on back with one leg bent and one leg straight. Flex the foot of the straight leg and lift it to the height of the opposite knee. Pause 2 seconds, then lower slowly.",
        "precautions": "Keep lower back gently pressed to the floor. Do not let knee bend during lift."
    },
    {
        "id": "clamshell",
        "name": "Clamshell",
        "target_area": "Hips / Gluteus Medius",
        "difficulty": "Beginner",
        "equipment": "Mat (optional loop band)",
        "sets": 3,
        "reps": "12-15 reps per side",
        "instructions": "Lie on side with hips and knees stacked at 90 degrees. Keeping feet glued together, rotate top knee upward towards the ceiling as high as possible without rolling pelvis back.",
        "precautions": "Do not roll hips backward; place top hand on hip bone to stabilize pelvis."
    }
]


def seed_database():
    db = firestore.Client(project=PROJECT_ID)
    collection_ref = db.collection("exercises")

    print(f"Seeding {len(SEED_EXERCISES)} exercises into project '{PROJECT_ID}'...")
    for item in SEED_EXERCISES:
        doc_id = item["id"]
        collection_ref.document(doc_id).set(item)
        print(f"  ✓ Added: {item['name']} ({doc_id})")

    print("\n✅ Seeding complete!")


if __name__ == "__main__":
    seed_database()
