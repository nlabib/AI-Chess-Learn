from __future__ import annotations

import json
from typing import Any
from urllib import error, request

from .config import AppConfig


class LMStudioClient:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def generate_review(self, review_payload: dict[str, Any]) -> dict[str, Any]:
        model = self._resolve_model()
        if not model:
            return {
                "enabled": False,
                "model": None,
                "summary": None,
                "error": "No LM Studio model is available. Start the local server and load an instruct model.",
            }

        prompt = build_review_prompt(review_payload)
        payload = {
            "model": model,
            "temperature": 0.2,
            "max_tokens": 700,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a patient chess coach. Use only the supplied engine findings. "
                        "Do not invent tactical lines that are not in the input. "
                        "Be specific, supportive, and practical."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }

        try:
            response = self._request("POST", "/chat/completions", payload)
        except RuntimeError as exc:
            return {
                "enabled": False,
                "model": model,
                "summary": None,
                "error": str(exc),
            }

        try:
            message = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            return {
                "enabled": False,
                "model": model,
                "summary": None,
                "error": f"LM Studio returned an unexpected response: {exc}",
            }

        return {
            "enabled": True,
            "model": model,
            "summary": message.strip(),
            "error": None,
        }

    def _resolve_model(self) -> str | None:
        if self.config.lm_studio_model:
            return self.config.lm_studio_model

        try:
            models = self._request("GET", "/models")
        except RuntimeError:
            return None

        data = models.get("data", [])
        if not data:
            return None
        return data[0].get("id")

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = request.Request(
            url=f"{self.config.lm_studio_base_url}{path}",
            method=method,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.lm_studio_api_key}",
            },
        )

        try:
            with request.urlopen(req, timeout=self.config.lm_studio_timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.URLError as exc:
            raise RuntimeError(
                "Could not reach LM Studio. Start the local server in LM Studio's Developer tab "
                "or with `lms server start`."
            ) from exc

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"LM Studio returned invalid JSON: {exc}") from exc


def build_review_prompt(review_payload: dict[str, Any]) -> str:
    summary = review_payload["summary"]
    notable_moves = review_payload["notable_moves"]
    pgn = review_payload["pgn"]

    return (
        "Review this chess game for a learner.\n\n"
        f"Player color: {review_payload['player_color']}\n"
        f"Result: {review_payload['result']}\n"
        f"Engine source: {review_payload['engine_source']}\n"
        f"PGN:\n{pgn}\n\n"
        f"Summary metrics:\n{json.dumps(summary, indent=2)}\n\n"
        f"Important moves:\n{json.dumps(notable_moves, indent=2)}\n\n"
        "Respond with four short sections:\n"
        "1. Overall assessment\n"
        "2. What went well\n"
        "3. What to fix next time\n"
        "4. Three training priorities\n"
    )

