from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from coach_chess.config import load_config
from coach_chess.game import GameManager


config = load_config()
app = Flask(__name__)
game_manager = GameManager(config)
game_manager.new_game()


@app.after_request
def add_cors_headers(response):
    if config.allow_cors_origin:
        response.headers["Access-Control-Allow-Origin"] = config.allow_cors_origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/api/state", methods=["GET"])
def get_state():
    return jsonify(game_manager.serialize_state())


@app.route("/api/new-game", methods=["POST", "OPTIONS"])
def new_game():
    if request.method == "OPTIONS":
        return ("", 204)

    payload = request.get_json(silent=True) or {}
    color = payload.get("player_color", "white")
    difficulty = payload.get("difficulty", "medium")
    state = game_manager.new_game(player_color=color, difficulty_name=difficulty)
    return jsonify(state)


@app.route("/api/move", methods=["POST", "OPTIONS"])
def move():
    if request.method == "OPTIONS":
        return ("", 204)

    payload = request.get_json(silent=True) or {}
    from_square = payload.get("from_square")
    to_square = payload.get("to_square")
    promotion = payload.get("promotion")

    if not from_square or not to_square:
        return jsonify({"error": "Both from_square and to_square are required."}), 400

    try:
        state = game_manager.make_player_move(from_square, to_square, promotion)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(state)


@app.route("/api/hint", methods=["POST", "OPTIONS"])
def hint():
    if request.method == "OPTIONS":
        return ("", 204)

    try:
        hint_data = game_manager.get_hint()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(hint_data)


@app.route("/api/review", methods=["POST", "OPTIONS"])
def review():
    if request.method == "OPTIONS":
        return ("", 204)

    review_data = game_manager.review_current_game()
    return jsonify(review_data)


if __name__ == "__main__":
    app.run(host=config.host, port=config.port, debug=False)

