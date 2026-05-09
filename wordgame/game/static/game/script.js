const grid = document.getElementById("grid");

const currentPlayerText = document.getElementById("current-player");
const score1Text = document.getElementById("score1");
const score2Text = document.getElementById("score2");


// =====================================
// WEBSOCKET FIX FOR RENDER
// =====================================

const protocol =
    window.location.protocol === "https:"
        ? "wss"
        : "ws";

const socket = new WebSocket(
    `${protocol}://${window.location.host}/ws/game/${roomName}/`
);


let myPlayerNumber = null;
let currentPlayer = 1;
let selectedCell = null;

let playerNames = {
    1: "Player 1",
    2: "Player 2"
};


// ==========================
// SOCKET
// ==========================

socket.onopen = () => {
    console.log("WebSocket Connected");
};

socket.onerror = (error) => {
    console.log("Socket Error:", error);
};

socket.onclose = () => {
    console.log("WebSocket Closed");
};

socket.onmessage = (event) => {

    const message = JSON.parse(event.data);

    console.log("SERVER:", message);

    // ==========================
    // START GAME
    // ==========================

    if (message.type === "start_game") {

        playerNames = message.usernames;

        updatePlayerLabels();

        return;
    }


    // ==========================
    // PLAYER ASSIGNMENT
    // ==========================

    if (message.type === "player_assignment") {

        myPlayerNumber = message.player;

        if (message.usernames) {

            playerNames = message.usernames;

            updatePlayerLabels();
        }

        showToast(`Connected as ${message.username}`);

        return;
    }


    // ==========================
    // UPDATE
    // ==========================

    if (message.type === "update") {

        const {
            board,
            turn,
            scores,
            words,
            usernames
        } = message;

        // USERNAMES
        if (usernames) {

            playerNames = usernames;

            updatePlayerLabels();
        }

        // BOARD UPDATE
        document.querySelectorAll(".cell").forEach(cell => {

            const r = parseInt(cell.dataset.row);
            const c = parseInt(cell.dataset.col);

            const value = board[r][c] || "";

            if (cell.textContent !== value) {

                cell.textContent = value;

                if (value !== "") {

                    cell.classList.add("filled");

                    setTimeout(() => {
                        cell.classList.remove("filled");
                    }, 250);
                }
            }
        });

        // TURN UPDATE
        currentPlayer = turn;

        updatePlayerLabels();

        // SCORE UPDATE
        score1Text.textContent = scores[1];
        score2Text.textContent = scores[2];

        // WORDS
        if (words.length > 0) {

            highlightWords();

            showToast(
                "Word found: " + words.join(", ")
            );
        }
    }


    // ==========================
    // GAME END
    // ==========================

    if (message.type === "game_end") {

        showEndPopup(
            message.winner,
            message.scores
        );
    }


    // ==========================
    // RESET
    // ==========================

    if (message.type === "reset") {

        document.querySelectorAll(".cell")
            .forEach(cell => {

                cell.textContent = "";

                cell.classList.remove("word");
            });

        currentPlayer = 1;

        updatePlayerLabels();

        score1Text.textContent = 0;
        score2Text.textContent = 0;
    }


    // ==========================
    // PLAYER LEFT
    // ==========================

    if (message.type === "player_left") {

        alert("Opponent left the game");

        window.location.href = "/";
    }
};


// ==========================
// END POPUP
// ==========================

function showEndPopup(title, scores) {

    const existing =
        document.querySelector(".popup-overlay");

    if (existing) existing.remove();

    const popup = document.createElement("div");

    popup.classList.add("popup-overlay");

    popup.innerHTML = `

        <div class="popup-box">

            <h2>${title}</h2>

            <p>
                Final Score:
                ${scores[1]} - ${scores[2]}
            </p>

            <button id="playAgainBtn">
                Play Again
            </button>

            <button id="backBtn">
                Back Home
            </button>

        </div>
    `;

    document.body.appendChild(popup);

    document.getElementById("playAgainBtn")
        .onclick = () => {

            socket.send(JSON.stringify({
                type: "restart"
            }));

            popup.remove();
        };

    document.getElementById("backBtn")
        .onclick = () => {

            window.location.href = "/";
        };
}


// ==========================
// GRID
// ==========================

for (let row = 0; row < 5; row++) {

    for (let col = 0; col < 5; col++) {

        const cell =
            document.createElement("div");

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
                .forEach(c =>
                    c.classList.remove("selected")
                );

            selectedCell = { row, col };

            cell.classList.add("selected");
        });

        grid.appendChild(cell);
    }
}


// ==========================
// DESKTOP KEYBOARD INPUT
// ==========================

document.addEventListener("keydown", (event) => {

    if (!selectedCell) return;

    if (myPlayerNumber !== currentPlayer)
        return;

    const letter =
        event.key.toUpperCase();

    if (!/^[A-Z]$/.test(letter)) return;

    sendLetter(letter);
});


// ==========================
// MOBILE INPUT SUPPORT
// ==========================

const hiddenInput =
    document.createElement("input");

hiddenInput.type = "text";

hiddenInput.maxLength = 1;

hiddenInput.style.position = "absolute";
hiddenInput.style.opacity = 0;

document.body.appendChild(hiddenInput);

document.querySelectorAll(".cell")
    .forEach(cell => {

        cell.addEventListener("click", () => {

            hiddenInput.focus();
        });
    });

hiddenInput.addEventListener("input", () => {

    const letter =
        hiddenInput.value.toUpperCase();

    if (/^[A-Z]$/.test(letter)) {

        sendLetter(letter);
    }

    hiddenInput.value = "";
});


// ==========================
// SEND LETTER
// ==========================

function sendLetter(letter) {

    socket.send(JSON.stringify({

        row: selectedCell.row,

        col: selectedCell.col,

        letter: letter,

        player: myPlayerNumber
    }));

    selectedCell = null;

    document.querySelectorAll(".cell")
        .forEach(c =>
            c.classList.remove("selected")
        );
}


// ==========================
// HIGHLIGHT WORDS
// ==========================

function highlightWords() {

    const cells =
        document.querySelectorAll(".cell");

    cells.forEach(cell => {

        if (cell.textContent !== "") {

            cell.classList.add("word");
        }
    });

    setTimeout(() => {

        cells.forEach(cell =>
            cell.classList.remove("word")
        );

    }, 600);
}


// ==========================
// TOAST
// ==========================

function showToast(msg) {

    let container =
        document.getElementById(
            "toast-container"
        );

    if (!container) {

        container =
            document.createElement("div");

        container.id = "toast-container";

        container.style.position = "fixed";
        container.style.bottom = "20px";
        container.style.right = "20px";
        container.style.zIndex = "9999";

        document.body.appendChild(container);
    }

    const toast =
        document.createElement("div");

    toast.classList.add("toast");

    toast.innerText = msg;

    toast.style.background = "#111827";
    toast.style.color = "white";
    toast.style.padding = "12px 18px";
    toast.style.marginTop = "10px";
    toast.style.borderRadius = "8px";

    container.appendChild(toast);

    setTimeout(() => {

        toast.remove();

    }, 2000);
}


// ==========================
// PLAYER LABELS
// ==========================

function updatePlayerLabels() {

    const p1 = getPlayerName(1);
    const p2 = getPlayerName(2);

    const p1Elem =
        document.getElementById("p1-name");

    const p2Elem =
        document.getElementById("p2-name");

    if (p1Elem) p1Elem.textContent = p1;
    if (p2Elem) p2Elem.textContent = p2;

    currentPlayerText.textContent =
        currentPlayer === 1
            ? p1
            : p2;
}


function getPlayerName(num) {

    if (!playerNames)
        return `Player ${num}`;

    if (Array.isArray(playerNames)) {

        return playerNames[num - 1]
            || `Player ${num}`;
    }

    return playerNames[num]
        || playerNames[num.toString()]
        || `Player ${num}`;
}