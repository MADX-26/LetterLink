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
let playerNames = { 1: "Player 1", 2: "Player 2" };


// ==========================
// SOCKET
// ==========================

socket.onmessage = (event) => {

    const message = JSON.parse(event.data);
    console.log("SERVER:", message);

    // START GAME (RECEIVE USERNAMES)
    if (message.type === "start_game") {
        playerNames = message.usernames;
        updatePlayerLabels();
        return;
    }

    // PLAYER ASSIGNMENT
    if (message.type === "player_assignment") {
        myPlayerNumber = message.player;
        if (message.usernames) {
            playerNames = message.usernames;
            updatePlayerLabels();
        }
        showToast(`Connected as ${message.username}`);
        return;
    }

    // GAME UPDATE
    if (message.type === "update") {

        const { board, turn, scores, words, usernames } = message;

        // Sync usernames
        if (usernames) {
            playerNames = usernames;
            updatePlayerLabels();
        }

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
        updatePlayerLabels(); // This will update the turn text correctly using the sync'd names
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
        showEndPopup(message.winner, message.scores);
    }

    // RESET GAME
    if (message.type === "reset") {

        document.querySelectorAll(".cell").forEach(cell => {
            cell.textContent = "";
            cell.classList.remove("word");
        });

        currentPlayer = 1;
        updatePlayerLabels();

        score1Text.textContent = 0;
        score2Text.textContent = 0;
    }

    // PLAYER LEFT
    if (message.type === "player_left") {
        const winnerMsg = message.winner ? `🏆 ${message.winner} Wins!` : "Opponent left the game";
        const subMsg = message.winner ? "(Your opponent has exited the match)" : "The other player has disconnected.";
        
        showEndPopup(winnerMsg, null, true); // true = hide play again
        
        const popupBox = document.querySelector(".popup-box");
        if (popupBox) {
            const p = document.createElement("p");
            p.innerHTML = `${subMsg}<br><small style="color: #9ca3af; margin-top: 0.5rem; display: block;">Redirecting to home in <span id="countdown">10</span>s...</small>`;
            p.style.color = "#6b7280";
            p.style.marginBottom = "2rem";
            popupBox.insertBefore(p, popupBox.querySelector("div"));

            let seconds = 10;
            const timer = setInterval(() => {
                seconds--;
                const count = document.getElementById("countdown");
                if (count) count.textContent = seconds;
                if (seconds <= 0) {
                    clearInterval(timer);
                    window.location.href = "/";
                }
            }, 1000);
        }
    }
};

function showEndPopup(title, scores, hidePlayAgain = false) {
    // Remove existing if any
    const existing = document.querySelector(".popup-overlay");
    if (existing) existing.remove();

    const popup = document.createElement("div");
    popup.classList.add("popup-overlay");

    let scoreHtml = "";
    if (scores) {
        scoreHtml = `<p style="font-size: 1.25rem; color: #6b7280; margin-bottom: 2rem;">
            Final Score: <b style="color: #1f2937;">${scores[1]} - ${scores[2]}</b>
        </p>`;
    }

    popup.innerHTML = `
        <div class="popup-box">
            <h2 class="modern-title" style="font-size: 2rem; margin-bottom: 1rem;">${title}</h2>
            ${scoreHtml}

            <div style="display: flex; flex-direction: column; gap: 0.75rem;">
                ${!hidePlayAgain ? '<button id="playAgainBtn" class="modern-btn">Play Again</button>' : ''}
                <button id="backBtn" class="modern-btn" style="background-color: #f3f4f6; color: #4b5563;">Back to Home</button>
            </div>
        </div>
    `;

    document.body.appendChild(popup);

    if (!hidePlayAgain) {
        document.getElementById("playAgainBtn").onclick = () => {
            socket.send(JSON.stringify({ type: "restart" }));
            popup.remove();
        };
    }

    document.getElementById("backBtn").onclick = () => {
        window.location.href = "/";
    };
}


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

function updatePlayerLabels() {
    if (!playerNames) return;

    // Get names safely whether playerNames is a dict or array
    const p1 = getPlayerName(1);
    const p2 = getPlayerName(2);
    
    const p1Elem = document.getElementById("p1-name");
    const p2Elem = document.getElementById("p2-name");
    
    if (p1Elem) p1Elem.textContent = p1;
    if (p2Elem) p2Elem.textContent = p2;
    
    // Update turn text to show the name of the current player
    if (currentPlayerText) {
        currentPlayerText.textContent = (currentPlayer === 1) ? p1 : p2;
    }
}

function getPlayerName(num) {
    if (!playerNames) return `Player ${num}`;

    if (Array.isArray(playerNames)) {
        // Handle 0-based array index for 1-based player number
        return playerNames[num - 1] || `Player ${num}`;
    } else {
        // Handle object with string or number keys
        return playerNames[num.toString()] || playerNames[num] || `Player ${num}`;
    }
}