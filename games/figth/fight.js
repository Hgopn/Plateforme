console.log("🔥 Fight Arena loaded");

let teamLeft = [];
let teamRight = [];

function addPlayerToTeam(username, team) {
    const playerEl = document.createElement("div");
    playerEl.className = "player";
    playerEl.textContent = username;

    if (team === "left") {
        document.getElementById("players-left").appendChild(playerEl);
        teamLeft.push(username);
    } else {
        document.getElementById("players-right").appendChild(playerEl);
        teamRight.push(username);
    }
}
