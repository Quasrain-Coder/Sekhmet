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
        # Concrete table preview when the scenario carries a frozen state.
        "table": _table_preview(s),
    }


def _table_preview(scenario) -> dict | None:
    """Public preview of the frozen state for the decision UI."""
    gs = scenario.frozen_state
    if gs is None:
        return None
    p = gs.player(scenario.player_seat) if scenario.player_seat is not None else None
    return {
        "phase": gs.phase.name,
        "hole_cards": [str(c) for c in p.hole_cards] if p and p.hole_cards else [],
        "community_cards": [str(c) for c in gs.community_cards],
        "pot": gs.pot.main_pot,
        "current_bet": gs.current_bet,
        "to_call": max(0, gs.current_bet - p.current_bet) if p else 0,
        "stack": p.stack if p else 0,
        "dealer_idx": gs.dealer_idx,
        "sb_seat": gs.sb_seat,
        "bb_seat": gs.bb_seat,
        "player_seat": scenario.player_seat,
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


@router.get("/importable-hands")
async def importable_hands(username: str | None = None, limit: int = 10):
    """Recent recorded hands the account lost, ready to import as scenarios."""
    import json as _json
    from fastapi.responses import JSONResponse
    from sqlalchemy import select

    if not username:
        return JSONResponse(status_code=400, content={"error": "username required"})
    from ..models import db
    from ..models.records import HandRecord

    async with db.SessionLocal() as s:
        rows = (await s.execute(
            select(HandRecord).order_by(HandRecord.id.desc())
            .limit(max(1, min(limit, 100)))
        )).scalars().all()
    hands = [
        {**{k: getattr(r, k) for k in (
            "id", "table_id", "created_at", "small_blind", "big_blind")},
         "players": _json.loads(r.players),
         "board": _json.loads(r.board),
         "actions": _json.loads(r.actions),
         "awards": _json.loads(r.awards)}
        for r in rows
    ]
    from ..trainer.hand_to_scenario import lost_hands_for
    lost = lost_hands_for(hands, username)
    return {"hands": [
        {
            "hand_id": h["id"],
            "table_id": h["table_id"],
            "created_at": h["created_at"].isoformat() if h.get("created_at") else None,
            "board": h["board"],
            "lost": sum(1 for _ in [0]),  # placeholder, replaced below
        }
        for h in lost
    ]}


@router.post("/scenarios/import-hand")
async def import_hand(body: dict):
    """Build a training scenario from a recorded hand the player lost."""
    from fastapi.responses import JSONResponse

    hand_id = body.get("hand_id")
    username = body.get("username")
    if not hand_id or not username:
        return JSONResponse(status_code=400,
                            content={"error": "hand_id and username required"})

    from ..models import db
    from ..models.records import HandRecord
    from sqlalchemy import select
    import json as _json
    from ..trainer.hand_to_scenario import build_scenario_from_hand

    async with db.SessionLocal() as s:
        r = (await s.execute(
            select(HandRecord).where(HandRecord.id == hand_id)
        )).scalar_one_or_none()
    if r is None:
        return JSONResponse(status_code=404, content={"error": "Hand not found"})

    hand = {
        "id": r.id,
        "players": _json.loads(r.players),
        "board": _json.loads(r.board),
        "actions": _json.loads(r.actions),
        "awards": _json.loads(r.awards),
        "small_blind": r.small_blind,
        "big_blind": r.big_blind,
    }
    seat = next((p["seat_idx"] for p in hand["players"]
                 if p.get("name") == username), None)
    if seat is None:
        return JSONResponse(status_code=404,
                            content={"error": f"{username} not in hand"})

    scenario = build_scenario_from_hand(hand, seat, username)
    if scenario is None:
        return JSONResponse(status_code=400,
                            content={"error": "Hand lacks hole cards (recorded before the patch)"})
    _library.add(scenario)
    return {"scenario_id": scenario.id, "title": scenario.title}
