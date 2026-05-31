from __future__ import annotations

from collections import Counter
from typing import Any

import chess
import chess.pgn

from .config import AppConfig
from .engine import EngineClient
from .llm import LMStudioClient


def review_game(
    moves: list[chess.Move],
    player_color: chess.Color,
    engine_client: EngineClient,
    llm_client: LMStudioClient,
    config: AppConfig,
) -> dict[str, Any]:
    pgn_text = build_pgn(moves)
    if not moves:
        return {
            "result": "*",
            "player_color": color_name(player_color),
            "engine_source": None,
            "pgn": pgn_text,
            "summary": {
                "player_moves": 0,
                "average_centipawn_loss": 0,
                "best_moves": 0,
                "good_moves": 0,
                "inaccuracies": 0,
                "mistakes": 0,
                "blunders": 0,
            },
            "items": [],
            "notable_moves": [],
            "llm_review": {
                "enabled": False,
                "model": None,
                "summary": None,
                "error": "Play a game first so there is something to review.",
            },
        }

    board = chess.Board()
    items: list[dict[str, Any]] = []

    for index, move in enumerate(moves):
        mover = board.turn
        move_number = board.fullmove_number
        san = board.san(move)

        if mover == player_color:
            before_analysis = engine_client.analyse_position(
                board,
                player_color,
                depth=config.review_depth,
            )
            best_move = before_analysis.get("best_move")
            best_move_san = before_analysis.get("best_move_san")
            best_line = before_analysis.get("pv_san", [])
            evaluation_before = before_analysis.get("evaluation_cp", 0)
            source = before_analysis.get("source")

            board.push(move)
            after_analysis = engine_client.analyse_position(
                board,
                player_color,
                depth=config.review_depth,
            )
            evaluation_after = after_analysis.get("evaluation_cp", 0)
            centipawn_loss = max(0, min(1000, evaluation_before - evaluation_after))
            classification = classify_move(move, best_move, centipawn_loss)

            items.append(
                {
                    "ply": index + 1,
                    "move_number": move_number,
                    "side": color_name(mover),
                    "move_san": san,
                    "move_uci": move.uci(),
                    "best_move_san": best_move_san,
                    "best_move_uci": best_move.uci() if best_move else None,
                    "line": best_line,
                    "evaluation_before_cp": evaluation_before,
                    "evaluation_after_cp": evaluation_after,
                    "classification": classification,
                    "centipawn_loss": centipawn_loss,
                    "note": explain_review_item(classification, best_move_san, before_analysis.get("evaluation_text")),
                    "engine_source": source,
                }
            )
            continue

        board.push(move)

    result = board.result(claim_draw=True)
    summary = build_summary(items)
    notable_moves = sorted(
        items,
        key=lambda item: (severity_rank(item["classification"]), item["centipawn_loss"]),
        reverse=True,
    )[:5]

    review_payload = {
        "result": result,
        "player_color": color_name(player_color),
        "engine_source": items[0]["engine_source"] if items else None,
        "pgn": pgn_text,
        "summary": summary,
        "notable_moves": notable_moves,
    }
    llm_review = llm_client.generate_review(review_payload)

    return {
        "result": result,
        "player_color": color_name(player_color),
        "engine_source": items[0]["engine_source"] if items else None,
        "pgn": pgn_text,
        "summary": summary,
        "items": items,
        "notable_moves": notable_moves,
        "llm_review": llm_review,
    }


def build_pgn(moves: list[chess.Move]) -> str:
    game = chess.pgn.Game()
    node = game
    board = chess.Board()

    for move in moves:
        node = node.add_variation(move)
        board.push(move)

    outcome = board.outcome(claim_draw=True)
    if outcome:
        game.headers["Result"] = board.result(claim_draw=True)

    return str(game).strip()


def build_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter(item["classification"] for item in items)
    total_cpl = sum(item["centipawn_loss"] for item in items)
    move_count = len(items)

    return {
        "player_moves": move_count,
        "average_centipawn_loss": round(total_cpl / move_count, 1) if move_count else 0,
        "best_moves": counter.get("best", 0),
        "good_moves": counter.get("good", 0),
        "inaccuracies": counter.get("inaccuracy", 0),
        "mistakes": counter.get("mistake", 0),
        "blunders": counter.get("blunder", 0),
    }


def classify_move(
    played_move: chess.Move,
    best_move: chess.Move | None,
    centipawn_loss: int,
) -> str:
    if best_move and played_move == best_move:
        return "best"
    if centipawn_loss <= 25:
        return "good"
    if centipawn_loss <= 90:
        return "inaccuracy"
    if centipawn_loss <= 220:
        return "mistake"
    return "blunder"


def severity_rank(classification: str) -> int:
    ranks = {
        "best": 1,
        "good": 2,
        "inaccuracy": 3,
        "mistake": 4,
        "blunder": 5,
    }
    return ranks.get(classification, 0)


def explain_review_item(classification: str, best_move_san: str | None, evaluation_text: str | None) -> str:
    if classification == "best":
        return "You matched the engine's top choice here."
    if classification == "good":
        return "Solid move. You kept most of the position's value."
    if classification == "inaccuracy":
        return f"Playable, but {best_move_san or 'another move'} would have kept more pressure."
    if classification == "mistake":
        return f"This gave away a noticeable amount of evaluation. Engine preference: {best_move_san or 'n/a'}."
    return (
        f"This was the biggest kind of swing. The engine preferred {best_move_san or 'a different move'}"
        f" and evaluated the position around {evaluation_text or 'n/a'} before the move."
    )


def color_name(color: chess.Color) -> str:
    return "white" if color == chess.WHITE else "black"
