const socket = io();
let username;

socket.on('init', (data) => {
    username = data.username;
    document.getElementById('puzzle-text').textContent = data.puzzle || "Waiting for puzzle...";
    document.getElementById('timer').textContent = `${data.time_left}s`;
    updateTimerBar(data.time_left);
    updateScores(data.scores);
    updatePlayers(data.players);
});

socket.on('message', (msg) => {
    const chatBox = document.getElementById('chat-box');
    const p = document.createElement('p');
    p.textContent = msg;
    chatBox.appendChild(p);
    chatBox.scrollTop = chatBox.scrollHeight;
});

socket.on('new_game', (data) => {
    document.getElementById('puzzle-text').textContent = data.puzzle;
    document.getElementById('timer').textContent = `${data.time_left}s`;
    updateTimerBar(data.time_left);
});

socket.on('timer_update', (time) => {
    document.getElementById('timer').textContent = `${time}s`;
    updateTimerBar(time);
});

socket.on('game_over', (msg) => {
    document.getElementById('chat-box').innerHTML += `<p>${msg}</p>`;
});

socket.on('update_scores', (scores) => {
    updateScores(scores);
});

socket.on('update_players', (players) => {
    updatePlayers(players);
});

function updateTimerBar(time) {
    const bar = document.getElementById('timer-bar');
    const percentage = (time / 60) * 100;
    bar.style.width = `${percentage}%`;
}

function updateScores(scores) {
    const scoreList = document.getElementById('score-list');
    scoreList.innerHTML = '';
    for (const [player, score] of Object.entries(scores)) {
        const li = document.createElement('li');
        li.textContent = `${player}: ${score}`;
        scoreList.appendChild(li);
    }
}

function updatePlayers(players) {
    const playerList = document.getElementById('player-list');
    playerList.innerHTML = '';
    players.forEach(player => {
        const li = document.createElement('li');
        li.textContent = player;
        playerList.appendChild(li);
    });
}

function sendMessage() {
    const input = document.getElementById('msg-input');
    const msg = input.value.trim();
    if (msg) {
        socket.emit('message', { sid: socket.id, msg: msg });
        input.value = '';
    }
}

document.getElementById('msg-input').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
});