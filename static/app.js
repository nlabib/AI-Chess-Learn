const state = {
  game: null,
  selectedSquare: null,
  hint: null,
  review: null,
};

const boardElement = document.getElementById("board");
const statusText = document.getElementById("status-text");
const messageText = document.getElementById("message-text");
const enginePill = document.getElementById("engine-pill");
const turnPill = document.getElementById("turn-pill");
const resultBadge = document.getElementById("result-badge");
const movesList = document.getElementById("moves-list");
const hintBox = document.getElementById("hint-box");
const reviewSummary = document.getElementById("review-summary");
const colorSelect = document.getElementById("color-select");
const difficultySelect = document.getElementById("difficulty-select");

document.getElementById("new-game-button").addEventListener("click", startNewGame);
document.getElementById("hint-button").addEventListener("click", fetchHint);
document.getElementById("review-button").addEventListener("click", fetchReview);

async function api(path, method = "GET", payload = null) {
  const response = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: payload ? JSON.stringify(payload) : null,
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

async function loadState() {
  try {
    const game = await api("/api/state");
    state.game = game;
    render();
  } catch (error) {
    statusText.textContent = error.message;
  }
}

async function startNewGame() {
  setBusy("Starting a new game...");
  try {
    state.review = null;
    state.hint = null;
    state.selectedSquare = null;
    state.game = await api("/api/new-game", "POST", {
      player_color: colorSelect.value,
      difficulty: difficultySelect.value,
    });
    render();
  } catch (error) {
    statusText.textContent = error.message;
  }
}

async function fetchHint() {
  setHintLoading();
  try {
    state.hint = await api("/api/hint", "POST");
    renderHint();
  } catch (error) {
    hintBox.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
  }
}

async function fetchReview() {
  reviewSummary.innerHTML = "<p>Analyzing game...</p>";
  try {
    state.review = await api("/api/review", "POST");
    renderReview();
  } catch (error) {
    reviewSummary.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
  }
}

function render() {
  if (!state.game) return;

  statusText.textContent = state.game.status;
  messageText.textContent = state.game.message || "";
  enginePill.textContent = state.game.engine_label;
  turnPill.textContent = `Turn: ${capitalize(state.game.turn)}`;
  resultBadge.textContent = state.game.result;
  difficultySelect.value = state.game.difficulty;
  colorSelect.value = state.game.player_color;

  renderBoard();
  renderMoves();
  renderHint();
  renderReview();
}

function renderBoard() {
  const game = state.game;
  const files = game.orientation === "white"
    ? ["a", "b", "c", "d", "e", "f", "g", "h"]
    : ["h", "g", "f", "e", "d", "c", "b", "a"];
  const ranks = game.orientation === "white"
    ? [8, 7, 6, 5, 4, 3, 2, 1]
    : [1, 2, 3, 4, 5, 6, 7, 8];

  const legalTargets = getLegalTargets();
  boardElement.innerHTML = "";

  for (const rank of ranks) {
    for (const file of files) {
      const square = `${file}${rank}`;
      const piece = game.board[square];
      const squareElement = document.createElement("button");
      const isLight = (files.indexOf(file) + ranks.indexOf(rank)) % 2 === 0;

      squareElement.className = `square ${isLight ? "light" : "dark"}`;
      squareElement.dataset.square = square;

      if (state.selectedSquare === square) {
        squareElement.classList.add("selected");
      }
      if (game.last_move && (game.last_move.from === square || game.last_move.to === square)) {
        squareElement.classList.add("last-move");
      }
      if (legalTargets.includes(square)) {
        squareElement.classList.add("target");
      }

      squareElement.addEventListener("click", () => handleSquareClick(square));

      if (piece) {
        const pieceSpan = document.createElement("span");
        pieceSpan.className = "piece";
        pieceSpan.textContent = piece.symbol;
        squareElement.appendChild(pieceSpan);
      }

      if ((game.orientation === "white" && rank === 1) || (game.orientation === "black" && rank === 8)) {
        const label = document.createElement("span");
        label.className = "square-label";
        label.textContent = file;
        squareElement.appendChild(label);
      }

      boardElement.appendChild(squareElement);
    }
  }
}

async function handleSquareClick(square) {
  if (!state.game || state.game.game_over) return;
  const piece = state.game.board[square];
  const isPlayerPiece = piece && piece.color === state.game.player_color;

  if (!state.selectedSquare) {
    if (isPlayerPiece) {
      state.selectedSquare = square;
      renderBoard();
    }
    return;
  }

  if (state.selectedSquare === square) {
    state.selectedSquare = null;
    renderBoard();
    return;
  }

  if (isPlayerPiece) {
    state.selectedSquare = square;
    renderBoard();
    return;
  }

  const matchingMoves = state.game.legal_moves.filter(
    (move) => move.from === state.selectedSquare && move.to === square,
  );

  if (matchingMoves.length === 0) {
    state.selectedSquare = null;
    renderBoard();
    return;
  }

  let promotion = null;
  if (matchingMoves.some((move) => move.promotion)) {
    const chosen = window.prompt("Promote to q, r, b, or n", "q");
    promotion = chosen ? chosen.trim().toLowerCase() : "q";
  }

  try {
    setBusy("Submitting move...");
    state.game = await api("/api/move", "POST", {
      from_square: state.selectedSquare,
      to_square: square,
      promotion,
    });
    state.selectedSquare = null;
    state.hint = null;
    render();
  } catch (error) {
    messageText.textContent = error.message;
  }
}

function renderMoves() {
  if (!state.game) return;
  const rows = [];

  for (let i = 0; i < state.game.moves.length; i += 2) {
    const whiteMove = state.game.moves[i];
    const blackMove = state.game.moves[i + 1];
    rows.push(`
      <div class="move-row">
        <span class="move-number">${whiteMove.move_number}.</span>
        <span>${escapeHtml(whiteMove.san)}</span>
        <span>${blackMove ? escapeHtml(blackMove.san) : ""}</span>
      </div>
    `);
  }

  movesList.innerHTML = rows.length ? rows.join("") : "<p class=\"muted\">No moves yet.</p>";
}

function renderHint() {
  if (!state.hint) {
    hintBox.innerHTML = "<p>Ask for a hint when you are not sure what to play.</p>";
    return;
  }

  const line = state.hint.line && state.hint.line.length
    ? state.hint.line.join(" ")
    : "No continuation available.";

  hintBox.innerHTML = `
    <strong>${escapeHtml(state.hint.move_san)}</strong>
    <p>${escapeHtml(state.hint.coach_note)}</p>
    <p><span class="muted">Eval:</span> ${escapeHtml(state.hint.evaluation_text)}</p>
    <p><span class="muted">Line:</span> ${escapeHtml(line)}</p>
    <p><span class="muted">Source:</span> ${escapeHtml(state.hint.source)}</p>
  `;
}

function renderReview() {
  if (!state.review) {
    return;
  }

  const summary = state.review.summary;
  const metrics = [
    ["Moves reviewed", summary.player_moves],
    ["Avg CPL", summary.average_centipawn_loss],
    ["Best moves", summary.best_moves],
    ["Good moves", summary.good_moves],
    ["Inaccuracies", summary.inaccuracies],
    ["Mistakes", summary.mistakes],
    ["Blunders", summary.blunders],
  ];

  const metricHtml = metrics.map(
    ([label, value]) => `
      <div class="metric">
        <strong>${escapeHtml(String(value))}</strong>
        <span class="muted">${escapeHtml(label)}</span>
      </div>
    `,
  ).join("");

  const items = state.review.notable_moves.map((item) => `
    <div class="review-item ${escapeHtml(item.classification)}">
      <strong>${item.move_number}. ${escapeHtml(item.move_san)} • ${capitalize(item.classification)}</strong>
      <p>${escapeHtml(item.note)}</p>
      <p><span class="muted">Best move:</span> ${escapeHtml(item.best_move_san || "n/a")}</p>
      <p><span class="muted">Centipawn loss:</span> ${escapeHtml(String(item.centipawn_loss))}</p>
      <p><span class="muted">Line:</span> ${escapeHtml((item.line || []).join(" "))}</p>
    </div>
  `).join("");

  const llmBlock = state.review.llm_review?.summary
    ? `<div class="hint-box"><strong>LM Studio Coach</strong><div class="review-text">${escapeHtml(state.review.llm_review.summary)}</div></div>`
    : `<div class="hint-box"><strong>LM Studio Coach</strong><p class="muted">${escapeHtml(state.review.llm_review?.error || "No LM Studio review available.")}</p></div>`;

  reviewSummary.innerHTML = `
    <p><span class="muted">Result:</span> ${escapeHtml(state.review.result)} • <span class="muted">Player color:</span> ${escapeHtml(capitalize(state.review.player_color))}</p>
    <p><span class="muted">Engine source:</span> ${escapeHtml(state.review.engine_source || "n/a")}</p>
    <div class="review-grid">${metricHtml}</div>
    <div class="review-items">${items || "<p class=\"muted\">No notable moves yet.</p>"}</div>
    ${llmBlock}
    <div class="hint-box">
      <strong>PGN</strong>
      <div class="review-text">${escapeHtml(state.review.pgn)}</div>
    </div>
  `;
}

function getLegalTargets() {
  if (!state.selectedSquare || !state.game) return [];
  return state.game.legal_moves
    .filter((move) => move.from === state.selectedSquare)
    .map((move) => move.to);
}

function setBusy(message) {
  messageText.textContent = message;
}

function setHintLoading() {
  hintBox.innerHTML = "<p>Analyzing your options...</p>";
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function capitalize(value) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

loadState();

