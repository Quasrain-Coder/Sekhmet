"""REST and WebSocket endpoints for the training module."""

from fastapi import APIRouter

from ..trainer.scenario_library import ScenarioCategory, ScenarioLibrary, BUILTIN_SCENARIOS
from ..trainer.scenario_runner import ScenarioRunner

router = APIRouter(prefix="/api/trainer", tags=["trainer"])

# Global trainer state (will be DB-backed later)
_library = ScenarioLibrary()
_runner = ScenarioRunner(_library)

# Load built-in scenarios
for data in BUILTIN_SCENARIOS:
    from ..trainer.scenario_library import Scenario
    _library.add(Scenario.from_yaml(data))


@router.get("/scenarios")
async def list_scenarios(category: str | None = None):
    """List all training scenarios, optionally by category."""
    if category:
        try:
            cat = ScenarioCategory(category)
        except ValueError:
            return {"error": f"Unknown category: {category}. Options: {[c.value for c in ScenarioCategory]}"}, 400
        scenarios = _library.list_by_category(cat)
    else:
        scenarios = _library.list_all()

    return {
        "scenarios": [
            {
                "id": s.id,
                "title": s.title,
                "description": s.description,
                "category": s.category.value,
                "difficulty": s.difficulty,
            }
            for s in scenarios
        ]
    }


@router.get("/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str):
    """Get a single scenario by ID."""
    from fastapi.responses import JSONResponse

    s = _library.get(scenario_id)
    if s is None:
        return JSONResponse(status_code=404, content={"error": "Scenario not found"})
    # Fetching a scenario's detail marks the decision timer's start — the
    # submit endpoint scores against this.  (next_scenario was never wired
    # into the API, so timing used to read 0 and always score full marks.)
    _runner.start(scenario_id)
    return {
        "id": s.id,
        "title": s.title,
        "description": s.description,
        "category": s.category.value,
        "difficulty": s.difficulty,
        "hints": s.hints,
    }


@router.post("/scenarios/{scenario_id}/submit")
async def submit_decision(scenario_id: str, action: dict):
    """Submit a training decision and get scored feedback."""
    from fastapi.responses import JSONResponse

    result = _runner.submit(scenario_id, action)
    if result is None:
        return JSONResponse(status_code=404, content={"error": "Scenario not found"})
    return result


@router.get("/scenarios/{scenario_id}/hint")
async def get_hint(scenario_id: str, level: int = 0):
    """Get a hint for a scenario."""
    from fastapi.responses import JSONResponse

    hint = _runner.get_hint(scenario_id, level)
    if hint is None:
        return JSONResponse(status_code=404, content={"error": "No hints available"})
    return {"hint": hint, "level": level}


@router.get("/categories")
async def list_categories():
    """List all scenario categories."""
    return {"categories": [c.value for c in ScenarioCategory]}
