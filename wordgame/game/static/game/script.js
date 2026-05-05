const grid = document.getElementById("grid");

const currentPlayerText = document.getElementById("current-player");
const score1Text = document.getElementById("score1");
const score2Text = document.getElementById("score2");

const socket = new WebSocket(
    `ws://${window.location.host}/ws/game/${roomName}/`
);

let myPlayerNumber = null;
let currentPlayer = 1;
let selectedCell = null;


// ==========================
// SOCKET
// ==========================

socket.onmessage = (event) => {

    const message = JSON.parse(event.data);
    console.log("SERVER:", message);

    // PLAYER ASSIGNMENT
    if (message.type === "player_assignment") {
        myPlayerNumber = message.player;
        showToast(`You are Player ${myPlayerNumber}`);
        return;
    }

    // GAME UPDATE
    if (message.type === "update") {

        const { board, turn, scores, words } = message;

        document.querySelectorAll(".cell").forEach(cell => {

            const r = parseInt(cell.dataset.row);
            const c = parseInt(cell.dataset.col);

            const newValue = board[r][c] || "";

            if (cell.textContent !== newValue) {

                cell.textContent = newValue;

                if (newValue !== "") {
                    cell.classList.add("filled");

                    setTimeout(() => {
                        cell.classList.remove("filled");
                    }, 200);
                }
            }
        });

        // TURN UPDATE + GLOW
        currentPlayer = turn;
        currentPlayerText.textContent = `Player ${turn}`;
        currentPlayerText.classList.add("turn-active");

        setTimeout(() => {
            currentPlayerText.classList.remove("turn-active");
        }, 400);

        // SCORE UPDATE
        score1Text.textContent = scores[1];
        score2Text.textContent = scores[2];

        // WORD HIGHLIGHT
        if (words.length > 0) {
            highlightWords(words);
            showToast("Word found: " + words.join(", "));
        }
    }

    // GAME END
    if (message.type === "game_end") {

        const popup = document.createElement("div");
        popup.classList.add("popup-overlay");

        popup.innerHTML = `
            <div class="popup-box">
                <h2>${message.winner}</h2>
                <p>Final Score: ${message.scores[1]} - ${message.scores[2]}</p>

                <button id="playAgainBtn">Play Again</button>
                <button id="backBtn">Back</button>
            </div>
        `;

        document.body.appendChild(popup);

        document.getElementById("playAgainBtn").onclick = () => {
            socket.send(JSON.stringify({ type: "restart" }));
            popup.remove();
        };

        document.getElementById("backBtn").onclick = () => {
            window.location.replace("/");
        };
    }

    // RESET GAME
    if (message.type === "reset") {

        document.querySelectorAll(".cell").forEach(cell => {
            cell.textContent = "";
            cell.classList.remove("word");
        });

        currentPlayer = 1;
        currentPlayerText.textContent = "Player 1";

        score1Text.textContent = 0;
        score2Text.textContent = 0;
    }

    // PLAYER LEFT
    if (message.type === "player_left") {
        showToast("Opponent left the game");
        setTimeout(() => window.location.replace("/"), 1200);
    }
};


// ==========================
// GRID
// ==========================

for (let row = 0; row < 5; row++) {

    for (let col = 0; col < 5; col++) {

        const cell = document.createElement("div");

        cell.classList.add("cell");
        cell.dataset.row = row;
        cell.dataset.col = col;

        cell.addEventListener("click", () => {

            if (myPlayerNumber !== currentPlayer) {
                showToast("Not your turn");
                return;
            }

            if (cell.textContent !== "") return;

            document.querySelectorAll(".cell")
                .forEach(c => c.classList.remove("selected"));

            selectedCell = { row, col };
            cell.classList.add("selected");
        });

        grid.appendChild(cell);
    }
}


// ==========================
// INPUT
// ==========================

document.addEventListener("keydown", (event) => {

    if (!selectedCell) return;
    if (myPlayerNumber !== currentPlayer) return;

    const letter = event.key.toUpperCase();

    if (!/^[A-Z]$/.test(letter)) return;

    socket.send(JSON.stringify({
        row: selectedCell.row,
        col: selectedCell.col,
        letter: letter,
        player: myPlayerNumber
    }));

    selectedCell = null;
});


// ==========================
// WORD HIGHLIGHT
// ==========================

function highlightWords(words) {

    const cells = document.querySelectorAll(".cell");

    cells.forEach(cell => cell.classList.remove("word"));

    // simple visual highlight
    words.forEach(() => {
        cells.forEach(cell => {
            if (cell.textContent !== "") {
                cell.classList.add("word");
            }
        });
    });

    setTimeout(() => {
        cells.forEach(cell => cell.classList.remove("word"));
    }, 600);
}


// ==========================
// TOAST SYSTEM
// ==========================

function showToast(msg) {

    const container = document.getElementById("toast-container") 
        || createToastContainer();

    const toast = document.createElement("div");
    toast.classList.add("toast");
    toast.innerText = msg;

    container.appendChild(toast);

    setTimeout(() => toast.remove(), 2000);
}

function createToastContainer() {

    const div = document.createElement("div");
    div.id = "toast-container";

    div.style.position = "fixed";
    div.style.bottom = "20px";
    div.style.right = "20px";
    div.style.display = "flex";
    div.style.flexDirection = "column";
    div.style.gap = "10px";

    document.body.appendChild(div);

    return div;
}