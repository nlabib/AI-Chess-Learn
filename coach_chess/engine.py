from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from math import inf
from os import X_OK, access
from pathlib import Path
from typing import Iterable

import chess
import chess.engine

from .config import AppConfig, DifficultyProfile


PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

CENTER_SQUARES = {chess.D4, chess.E4, chess.D5, chess.E5}
EXTENDED_CENTER = {
    chess.C3,
    chess.D3,
    chess.E3,
    chess.F3,
    chess.C4,
    chess.D4,
    chess.E4,
    chess.F4,
    chess.C5,
    chess.D5,
    chess.E5,
    chess.F5,
    chess.C6,
    chess.D6,
    chess.E6,
    chess.F6,
}


@dataclass(frozen=True)
class EngineSuggestion:
    move: chess.Move
    evaluation_cp: int
    best_line_san: list[str]
    source: str


class EngineClient:
    MAX_FALLBACK_REVIEW_DEPTH = 2

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    @property
    def stockfish_available(self) -> bool:
        return self._stockfish_path_is_usable()

    def _stockfish_path_is_usable(self) -> bool:
        if not self.config.stockfish_path:
            return False
        path = Path(self.config.stockfish_path).expanduser()
        return path.is_file() and access(path, X_OK)

    @contextmanager
    def open_engine(self) -> Iterable[chess.engine.SimpleEngine | None]:
        if not self._stockfish_path_is_usable():
            yield None
            return

        try:
            engine = chess.engine.SimpleEngine.popen_uci(self.config.stockfish_path)
        except (FileNotFoundError, PermissionError, OSError):
            yield None
            return
        try:
            yield engine
        finally:
            engine.quit()

    def choose_move(self, board: chess.Board, difficulty: DifficultyProfile) -> EngineSuggestion:
        if self.stockfish_available:
            suggestion = self._choose_move_with_stockfish(board, difficulty)
            if suggestion:
                return suggestion
        return self._choose_move_with_fallback(board, difficulty)

    def get_hint(self, board: chess.Board, difficulty: DifficultyProfile, player_color: chess.Color) -> dict:
        suggestion = self.choose_move(board, difficulty)
        explanation = explain_move(board, suggestion.move)
        return {
            "source": suggestion.source,
            "move_uci": suggestion.move.uci(),
            "move_san": board.san(suggestion.move),
            "evaluation_cp": suggestion.evaluation_cp,
            "evaluation_text": cp_to_text(suggestion.evaluation_cp),
            "line": suggestion.best_line_san,
            "coach_note": explanation,
            "player_color": "white" if player_color == chess.WHITE else "black",
        }

    def analyse_position(
        self,
        board: chess.Board,
        perspective: chess.Color,
        *,
        depth: int,
        difficulty: DifficultyProfile | None = None,
    ) -> dict:
        if self.stockfish_available:
            result = self._analyse_with_stockfish(board, perspective, depth=depth, difficulty=difficulty)
            if result:
                return result
        return self._analyse_with_fallback(board, perspective, depth=depth)

    def _choose_move_with_stockfish(
        self,
        board: chess.Board,
        difficulty: DifficultyProfile,
    ) -> EngineSuggestion | None:
        with self.open_engine() as engine:
            if engine is None:
                return None

            try:
                engine.configure({"Skill Level": difficulty.stockfish_skill})
            except chess.engine.EngineError:
                pass

            try:
                result = engine.play(
                    board,
                    chess.engine.Limit(time=difficulty.move_time_seconds),
                    info=chess.engine.INFO_SCORE | chess.engine.INFO_PV,
                )
            except chess.engine.EngineError:
                return None

            info = result.info or {}
            score = info.get("score")
            evaluation = score.pov(board.turn).score(mate_score=100000) if score else 0
            pv = info.get("pv", [])
            best_line = san_line(board, pv[:4])

            return EngineSuggestion(
                move=result.move,
                evaluation_cp=evaluation,
                best_line_san=best_line,
                source="stockfish",
            )

    def _analyse_with_stockfish(
        self,
        board: chess.Board,
        perspective: chess.Color,
        *,
        depth: int,
        difficulty: DifficultyProfile | None = None,
    ) -> dict | None:
        with self.open_engine() as engine:
            if engine is None:
                return None

            if difficulty is not None:
                try:
                    engine.configure({"Skill Level": difficulty.stockfish_skill})
                except chess.engine.EngineError:
                    pass

            try:
                info = engine.analyse(
                    board,
                    chess.engine.Limit(depth=depth),
                    info=chess.engine.INFO_SCORE | chess.engine.INFO_PV,
                )
            except chess.engine.EngineError:
                return None

            score = info.get("score")
            pv = info.get("pv", [])
            best_move = pv[0] if pv else None
            evaluation_cp = score.pov(perspective).score(mate_score=100000) if score else 0

            return {
                "evaluation_cp": evaluation_cp,
                "evaluation_text": cp_to_text(evaluation_cp),
                "best_move": best_move,
                "best_move_san": board.san(best_move) if best_move else None,
                "pv_san": san_line(board, pv[:4]),
                "source": "stockfish",
            }

    def _choose_move_with_fallback(
        self,
        board: chess.Board,
        difficulty: DifficultyProfile,
    ) -> EngineSuggestion:
        perspective = board.turn
        best_move = None
        best_score = -inf
        for move in ordered_moves(board):
            board.push(move)
            score = minimax(board, difficulty.fallback_depth, -inf, inf, perspective)
            board.pop()
            if score > best_score or best_move is None:
                best_score = score
                best_move = move

        if best_move is None:
            best_move = next(iter(board.legal_moves))
            best_score = 0

        return EngineSuggestion(
            move=best_move,
            evaluation_cp=int(best_score),
            best_line_san=[board.san(best_move)],
            source="fallback",
        )

    def _analyse_with_fallback(
        self,
        board: chess.Board,
        perspective: chess.Color,
        *,
        depth: int,
    ) -> dict:
        # Stockfish review depth can be high, but the built-in minimax must stay shallow
        # so "Analyze Game" remains responsive when Stockfish is unavailable.
        depth = max(1, min(depth, self.MAX_FALLBACK_REVIEW_DEPTH))

        if board.is_game_over(claim_draw=True):
            score = int(evaluate_position(board, perspective))
            return {
                "evaluation_cp": score,
                "evaluation_text": cp_to_text(score),
                "best_move": None,
                "best_move_san": None,
                "pv_san": [],
                "source": "fallback",
            }

        best_move = None
        best_score = -inf
        for move in ordered_moves(board):
            board.push(move)
            score = minimax(board, depth, -inf, inf, perspective)
            board.pop()
            if score > best_score or best_move is None:
                best_score = score
                best_move = move

        return {
            "evaluation_cp": int(best_score),
            "evaluation_text": cp_to_text(int(best_score)),
            "best_move": best_move,
            "best_move_san": board.san(best_move) if best_move else None,
            "pv_san": [board.san(best_move)] if best_move else [],
            "source": "fallback",
        }


def minimax(
    board: chess.Board,
    depth: int,
    alpha: float,
    beta: float,
    perspective: chess.Color,
) -> float:
    if depth == 0 or board.is_game_over(claim_draw=True):
        return evaluate_position(board, perspective)

    if board.turn == perspective:
        value = -inf
        for move in ordered_moves(board):
            board.push(move)
            value = max(value, minimax(board, depth - 1, alpha, beta, perspective))
            board.pop()
            alpha = max(alpha, value)
            if alpha >= beta:
                break
        return value

    value = inf
    for move in ordered_moves(board):
        board.push(move)
        value = min(value, minimax(board, depth - 1, alpha, beta, perspective))
        board.pop()
        beta = min(beta, value)
        if alpha >= beta:
            break
    return value


def ordered_moves(board: chess.Board) -> list[chess.Move]:
    def move_score(move: chess.Move) -> int:
        score = 0
        if board.is_capture(move):
            captured_piece = board.piece_at(move.to_square)
            moving_piece = board.piece_at(move.from_square)
            captured_value = PIECE_VALUES.get(captured_piece.piece_type, 0) if captured_piece else 0
            moving_value = PIECE_VALUES.get(moving_piece.piece_type, 0) if moving_piece else 0
            score += 10 * captured_value - moving_value
        if move.promotion:
            score += PIECE_VALUES.get(move.promotion, 0)
        if board.gives_check(move):
            score += 50
        if move.to_square in CENTER_SQUARES:
            score += 15
        elif move.to_square in EXTENDED_CENTER:
            score += 5
        return score

    return sorted(board.legal_moves, key=move_score, reverse=True)


def evaluate_position(board: chess.Board, perspective: chess.Color) -> float:
    if board.is_checkmate():
        return -100000 if board.turn == perspective else 100000
    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    total = 0
    for square, piece in board.piece_map().items():
        value = PIECE_VALUES[piece.piece_type]
        bonus = positional_bonus(square, piece)
        signed_value = value + bonus
        total += signed_value if piece.color == chess.WHITE else -signed_value

    white_attacks = count_attacks(board, chess.WHITE)
    black_attacks = count_attacks(board, chess.BLACK)
    total += (white_attacks - black_attacks) * 0.75

    white_mobility = mobility(board, chess.WHITE)
    black_mobility = mobility(board, chess.BLACK)
    total += (white_mobility - black_mobility) * 2

    return total if perspective == chess.WHITE else -total


def positional_bonus(square: chess.Square, piece: chess.Piece) -> int:
    rank = chess.square_rank(square) if piece.color == chess.WHITE else 7 - chess.square_rank(square)
    bonus = 0

    if piece.piece_type == chess.PAWN:
        bonus += rank * 7
        if square in CENTER_SQUARES:
            bonus += 14
    elif piece.piece_type in {chess.KNIGHT, chess.BISHOP}:
        if square in CENTER_SQUARES:
            bonus += 18
        elif square in EXTENDED_CENTER:
            bonus += 10
    elif piece.piece_type == chess.ROOK:
        bonus += rank * 2
    elif piece.piece_type == chess.QUEEN:
        if square in EXTENDED_CENTER:
            bonus += 8
    elif piece.piece_type == chess.KING:
        bonus -= rank * 4

    return bonus


def count_attacks(board: chess.Board, color: chess.Color) -> int:
    return sum(len(board.attacks(square)) for square, piece in board.piece_map().items() if piece.color == color)


def mobility(board: chess.Board, color: chess.Color) -> int:
    if board.turn == color:
        return board.legal_moves.count()

    mirrored = board.copy(stack=False)
    mirrored.turn = color
    return mirrored.legal_moves.count()


def cp_to_text(score_cp: int) -> str:
    if score_cp >= 100000:
        return "Winning by force"
    if score_cp <= -100000:
        return "Losing by force"
    return f"{score_cp / 100:+.2f}"


def san_line(board: chess.Board, pv: list[chess.Move]) -> list[str]:
    line_board = board.copy()
    san_moves: list[str] = []
    for move in pv:
        if move not in line_board.legal_moves:
            break
        san_moves.append(line_board.san(move))
        line_board.push(move)
    return san_moves


def explain_move(board: chess.Board, move: chess.Move) -> str:
    if board.is_castling(move):
        return "Castling improves king safety and helps your rooks connect."
    if board.gives_check(move):
        return "This move gives check and forces your opponent to respond."
    if board.is_capture(move):
        return "This move wins or contests material and changes the balance immediately."

    moving_piece = board.piece_at(move.from_square)
    if moving_piece and moving_piece.piece_type in {chess.KNIGHT, chess.BISHOP}:
        return "This develops a minor piece and improves your activity."
    if move.to_square in CENTER_SQUARES:
        return "This fights for the center, which usually gives you more space and options."
    return "This move keeps your position coordinated and preserves your best engine line."
