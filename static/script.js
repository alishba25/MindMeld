let socket = io();
let gameState = null;

// When the game connects to the server
socket.on('connect', () => {
    console.log('Connected to the game server!');
    document.getElementById('test-message').innerText = 'Connected to server!';
});

// Update the board when the server sends new information
socket.on('update_game', (data) => {
    console.log('Board updated:', data);
    gameState = data.state;
    drawBoard();
});

// Show if you win or lose
socket.on('game_result', (data) => {
    console.log('Game result:', data);
    document.getElementById('result').innerText = data.result === 'win' ? 'You Win!' : 'Game Over!';
});

// Set up the level and board
socket.on('level_data', (data) => {
    console.log('Starting level:', data);
    gameState = data.state;
    document.getElementById('level').innerText = 'Level ' + data.level;
    drawBoard();
});

// Add to your existing socket handlers
socket.on('update_sequence', (data) => {
    const cells = document.querySelectorAll('.game-cell');
    // Remove all click handlers first
    cells.forEach(cell => {
        cell.onclick = null;
    });
    
    // Add selected class to newly selected cell
    cells[data.index].classList.add('selected');
    
    // Re-enable click handlers only for unselected cells
    cells.forEach((cell, idx) => {
        if (!data.selected.includes(idx)) {
            cell.onclick = () => socket.emit('tile_click', { index: idx });
        }
    });
});

socket.on('sequence_reset', () => {
    const cells = document.querySelectorAll('.game-cell');
    cells.forEach((cell, idx) => {
        cell.classList.remove('selected');
        cell.onclick = () => socket.emit('tile_click', { index: idx });
    });
});

socket.on('init_game', (data) => {
    gameState = data.state;
    if (gameState.type === "sequence") {
        const board = document.getElementById('game-board');
        board.innerHTML = '';
        board.className = 'sequence-level';
        
        const sequenceDisplay = document.createElement('div');
        sequenceDisplay.className = 'sequence-display';
        sequenceDisplay.textContent = `Find this sequence: ${gameState.sequence.join(' → ')}`;
        board.appendChild(sequenceDisplay);
        
        const grid = document.createElement('div');
        grid.className = 'sequence-grid';
        grid.style.gridTemplateColumns = `repeat(${gameState.size}, 1fr)`;
        
        gameState.grid.forEach((item, idx) => {
            const cell = document.createElement('div');
            cell.className = 'game-cell';
            cell.textContent = item;
            if (!gameState.selected.includes(idx)) {
                cell.onclick = () => socket.emit('tile_click', { index: idx });
            } else {
                cell.classList.add('selected');
            }
            grid.appendChild(cell);
        });
        
        board.appendChild(grid);
    }
});

// Draw the tiles on the board
function drawBoard() {
    const board = document.getElementById('game-board');
    board.innerHTML = ''; // Clear the old tiles
    if (!gameState) {
        console.log('No game state to show!');
        return;
    }
    if (gameState.type === "number_alphabet") {
        board.innerHTML = ''; // Clear the old tiles
        const current_round = gameState.rounds[gameState.current_round];
        const sequenceDiv = document.createElement('div');
        sequenceDiv.textContent = `Round ${gameState.current_round + 1}/3: ${current_round.sequence.join(', ')}, ?`;
        sequenceDiv.className = 'sequence-text';
        const optionsDiv = document.createElement('div');
        current_round.options.forEach((opt, index) => {
            const btn = document.createElement('button');
            btn.textContent = opt;
            btn.className = 'option-btn';
            btn.addEventListener('click', () => {
                console.log('Selected option:', opt);
                clickTile(opt);
            });
            optionsDiv.appendChild(btn);
        });
        board.appendChild(sequenceDiv);
        board.appendChild(optionsDiv);
    } else {
        // Existing logic for other game types
        const flatGrid = Array.isArray(gameState.grid[0]) ? [].concat(...gameState.grid) : gameState.grid;
        const gridSize = Math.sqrt(flatGrid.length);
        console.log('Grid size calculated as:', gridSize, 'Total tiles:', flatGrid.length);
        flatGrid.forEach((cell, index) => {
            const tile = document.createElement('div');
            tile.classList.add('tile');
            tile.dataset.index = index;
            tile.textContent = gameState.revealed.includes(index) ? cell : '?';
            tile.addEventListener('click', () => {
                console.log('Clicked tile at index:', index);
                clickTile(index);
            });
            board.appendChild(tile);
        });
    }
}

// Handle clicks for options or other actions
function clickTile(choice) {
    if (gameState) {
        socket.emit('tile_click', { choice: choice });
    } else {
        console.log('Game not ready to click!');
    }
}
