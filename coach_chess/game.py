from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import chess

from .config import DEFAULT_DIFFICULTY, AppConfig, get_difficulty
from .engine import EngineClient
from .llm import LMStudioClient
from .review import review_game


@dataclass
class GameManager:
    config: AppConfig
    engine_client: EngineClient = field(init=False)
    llm_client: LMStudioClient = field(init=False)
    board: chess.Board = field(default_factory=chess.Board)
    player_color: chess.Color = chess.WHITE
    difficulty_name: str = DEFAULT_DIFFICULTY
    last_message: str = "Start a new game when you're ready."

    def __post_init__(self) -> None:
        self.engine_client = EngineClient(self.config)
        self.llm_client = LMStudioClient(self.config)

    @property
    def difficulty(self):
        return get_difficulty(self.difficulty_name)

    def new_game(self, player_color: str = "white", difficulty_name: str = DEFAULT_DIFFICULTY) -> dict[str, Any]:
        self.board = chess.Board()
        self.player_color = chess.WHITE if player_color.lower() != "black" else chess.BLACK
        self.difficulty_name = difficulty_name if difficulty_name in {"easy", "medium", "hard"} else DEFAULT_DIFFICULTY
        self.last_message = "New game started."

        if self.player_color == chess.BLACK:
            computer_move = self.engine_client.choose_move(self.board, self.difficulty)
            san = self.board.san(computer_move.move)
            self.board.push(computer_move.move)
            self.last_message = f"Computer opened with {san}."

        return self.serialize_state()

    def make_player_move(self, from_square: str, to_square: str, promotion: str | None = None) -> dict[str, Any]:
        if self.board.is_game_over(claim_draw=True):
            raise ValueError("The game is already over. Start a new one to keep playing.")
        if self.board.turn != self.player_color:
            raise ValueError("It is not your turn yet.")

        move = self._parse_move(from_square, to_square, promotion)
        if move not in self.board.legal_moves:
            raise ValueError("That move is not legal in this position.")

        player_san = self.board.san(move)
        self.board.push(move)
        self.last_message = f"You played {player_san}."

        if not self.board.is_game_over(claim_draw=True):
            computer_move = self.engine_client.choose_move(self.board, self.difficulty)
            computer_san = self.board.san(computer_move.move)
            self.board.push(computer_move.move)
            self.last_message = f"You played {player_san}. Computer answered with {computer_san}."

        return self.serialize_state()

    def get_hint(self) -> dict[str, Any]:
        if self.board.is_game_over(claim_draw=True):
            raise ValueError("The game is over, so there is no next-move hint.")
        if self.board.turn != self.player_color:
            raise ValueError("Wait for the computer to move before asking for a hint.")

        return self.engine_client.get_hint(self.board, self.difficulty, self.player_color)

    def review_current_game(self) -> dict[str, Any]:
        return review_game(
            list(self.board.move_stack),
            self.player_color,
            self.engine_client,
            self.llm_client,
            self.config,
        )

    def serialize_state(self) -> dict[str, Any]:
        legal_moves = [
            {
                "from": chess.square_name(move.from_square),
                "to": chess.square_name(move.to_square),
                "uci": move.uci(),
                "san": self.board.san(move),
                "promotion": promotion_name(move.promotion),
            }
            for move in self.board.legal_moves
        ]

        last_move = None
        if self.board.move_stack:
            peek = self.board.peek()
            last_move = {
                "from": chess.square_name(peek.from_square),
                "to": chess.square_name(peek.to_square),
                "uci": peek.uci(),
            }

        return {
            "fen": self.board.fen(),
            "board": serialize_board(self.board),
            "turn": "white" if self.board.turn == chess.WHITE else "black",
            "player_color": "white" if self.player_color == chess.WHITE else "black",
            "orientation": "white" if self.player_color == chess.WHITE else "black",
            "game_over": self.board.is_game_over(claim_draw=True),
            "result": self.board.result(claim_draw=True) if self.board.is_game_over(claim_draw=True) else "*",
            "status": self._status_text(),
            "message": self.last_message,
            "moves": build_move_history(self.board.move_stack),
            "legal_moves": legal_moves,
            "last_move": last_move,
            "difficulty": self.difficulty_name,
            "engine_available": self.engine_client.stockfish_available,
            "engine_label": "Stockfish" if self.engine_client.stockfish_available else "Built-in engine",
        }

    def _status_text(self) -> str:
        if self.board.is_checkmate():
            winner = "White" if self.board.turn == chess.BLACK else "Black"
            return f"Checkmate. {winner} wins."
        if self.board.is_stalemate():
            return "Draw by stalemate."
        if self.board.is_insufficient_material():
            return "Draw by insufficient material."
        if self.board.can_claim_threefold_repetition():
            return "Threefold repetition is available."
        if self.board.can_claim_fifty_moves():
            return "A fifty-move draw is available."

        if self.board.turn == self.player_color:
            return "Your move." + (" You are in check." if self.board.is_check() else "")
        return "Computer to move."

    def _parse_move(self, from_square: str, to_square: str, promotion: str | None = None) -> chess.Move:
        base_move = f"{from_square}{to_square}"
        if promotion:
            promotion_piece = promotion_piece_type(promotion)
            if promotion_piece is None:
                raise ValueError("Promotion must be one of q, r, b, or n.")
            return chess.Move.from_uci(f"{base_move}{promotion.lower()}")

        for legal_move in self.board.legal_moves:
            if (
                chess.square_name(legal_move.from_square) == from_square
                and chess.square_name(legal_move.to_square) == to_square
            ):
                if legal_move.promotion:
                    return chess.Move.from_uci(f"{base_move}q")
                return legal_move

        return chess.Move.from_uci(base_move)


def serialize_board(board: chess.Board) -> dict[str, dict[str, str]]:
    pieces: dict[str, dict[str, str]] = {}
    for square, piece in board.piece_map().items():
        pieces[chess.square_name(square)] = {
            "symbol": piece.unicode_symbol(),
            "color": "white" if piece.color == chess.WHITE else "black",
            "code": piece.symbol(),
        }
    return pieces


def build_move_history(move_stack: list[chess.Move]) -> list[dict[str, Any]]:
    board = chess.Board()
    history: list[dict[str, Any]] = []

    for index, move in enumerate(move_stack):
        history.append(
            {
                "ply": index + 1,
                "move_number": board.fullmove_number,
                "side": "white" if board.turn == chess.WHITE else "black",
                "san": board.san(move),
                "uci": move.uci(),
            }
        )
        board.push(move)

    return history


def promotion_name(piece_type: int | None) -> str | None:
    names = {
        chess.QUEEN: "queen",
        chess.ROOK: "rook",
        chess.BISHOP: "bishop",
        chess.KNIGHT: "knight",
    }
    return names.get(piece_type)


def promotion_piece_type(symbol: str) -> int | None:
    mapping = {
        "q": chess.QUEEN,
        "r": chess.ROOK,
        "b": chess.BISHOP,
        "n": chess.KNIGHT,
    }
    return mapping.get(symbol.lower())
