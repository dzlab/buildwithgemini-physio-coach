# My agent: PhysioCoach (Physical Therapy & Rehab Assistant)

One-liner: A conversational agent that helps individuals recover from injuries and build strength with a catalog of targeted physical therapy exercises, personalized routines, and pose/form illustrations.

Tool coverage:
- Memory: User injury history, pain levels, target muscle groups/joints, available equipment, and completed session history.
- Tools: Look up exercises by body area/condition, log workout sessions and pain ratings, retrieve detailed exercise instructions.
- Catalog/UI: Exercise library rendered as A2UI cards (exercise name, target area, difficulty, sets/reps) and multi-day rehab routine tables.
- Image gen: Generates posture alignment illustrations and reference body pose diagrams for exercises.
- Sandbox: Computes training volume (sets × reps × load), progress pacing, and recovery intensity adjustments.

Recommended for every project: memory, storage, tools, image generation, A2UI
Agent-specific / stretch (pick what fits): Code sandbox for training volume and progression calculations; multimodal camera/image input to inspect user form.
