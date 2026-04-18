const canvas = document.getElementById('game-canvas');
const ctx = canvas.getContext('2d');

// UI Elements
const startScreen = document.getElementById('start-screen');
const scoreDisplay = document.getElementById('score-display');
const currentScoreElement = document.getElementById('current-score');
const gameOverScreen = document.getElementById('game-over-screen');
const finalScoreElement = document.getElementById('final-score');
const bestScoreElement = document.getElementById('best-score');
const restartBtn = document.getElementById('restart-btn');

// Game State
const GAME_STATE = {
    START: 0,
    PLAYING: 1,
    GAME_OVER: 2
};
let currentState = GAME_STATE.START;

// Game Variables
let frames = 0;
let score = 0;
let bestScore = localStorage.getItem('flappyBestScore') || 0;

// Bird Object
const bird = {
    x: 50,
    y: 150,
    width: 34,
    height: 24,
    velocity: 0,
    gravity: 0.25,
    jump: 4.6,
    rotation: 0,

    draw: function () {
        ctx.save();
        ctx.translate(this.x + this.width / 2, this.y + this.height / 2);

        // Rotate bird based on velocity
        this.rotation = Math.min(Math.PI / 4, Math.max(-Math.PI / 4, (this.velocity * 0.1)));
        ctx.rotate(this.rotation);

        ctx.translate(-this.width / 2, -this.height / 2);

        // Draw Bird Body (Yellow Ellipse)
        ctx.fillStyle = '#f1c40f'; // Yellow
        ctx.beginPath();
        ctx.ellipse(17, 12, 17, 12, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = '#e67e22'; // Orange border
        ctx.lineWidth = 2;
        ctx.stroke();

        // Draw Eye
        ctx.fillStyle = 'white';
        ctx.beginPath();
        ctx.arc(24, 8, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = 'black';
        ctx.beginPath();
        ctx.arc(25.5, 8, 1.5, 0, Math.PI * 2);
        ctx.fill();

        // Draw Wing
        ctx.fillStyle = '#f39c12';
        ctx.beginPath();
        ctx.ellipse(8, 14, 6, 4, -Math.PI / 6, 0, Math.PI * 2);
        ctx.fill();

        // Draw Beak
        ctx.fillStyle = '#e74c3c';
        ctx.beginPath();
        ctx.moveTo(33, 14);
        ctx.lineTo(40, 15);
        ctx.lineTo(33, 18);
        ctx.closePath();
        ctx.fill();

        ctx.restore();
    },

    update: function () {
        // Apply gravity
        this.velocity += this.gravity;
        this.y += this.velocity;

        // Floor Collision
        if (this.y + this.height >= canvas.height - 20) { // Account for ground height
            this.y = canvas.height - 20 - this.height;
            gameOver();
        }

        // Ceiling Collision
        if (this.y < 0) {
            this.y = 0;
            this.velocity = 0;
        }
    },

    flap: function () {
        this.velocity = -this.jump;
    },

    reset: function () {
        this.y = 150;
        this.velocity = 0;
        this.rotation = 0;
    }
};

// Pipes Object
const pipes = {
    position: [],
    width: 60,
    gap: 150, // Space between top and bottom pipe
    dx: 2, // Pipe speed

    draw: function () {
        for (let i = 0; i < this.position.length; i++) {
            let p = this.position[i];

            // Top Pipe
            ctx.fillStyle = '#2ecc71';
            ctx.fillRect(p.x, 0, this.width, p.y);
            // Border Top
            ctx.strokeStyle = '#27ae60';
            ctx.lineWidth = 4;
            ctx.strokeRect(p.x, 0, this.width, p.y);
            // Top Pipe Cap
            ctx.fillRect(p.x - 2, p.y - 20, this.width + 4, 20);
            ctx.strokeRect(p.x - 2, p.y - 20, this.width + 4, 20);

            // Bottom Pipe
            ctx.fillStyle = '#2ecc71';
            let bottomPipeY = p.y + this.gap;
            let bottomPipeHeight = canvas.height - 20 - bottomPipeY; // Account for ground
            ctx.fillRect(p.x, bottomPipeY, this.width, bottomPipeHeight);
            // Border Bottom
            ctx.strokeRect(p.x, bottomPipeY, this.width, bottomPipeHeight);
            // Bottom Pipe Cap
            ctx.fillRect(p.x - 2, bottomPipeY, this.width + 4, 20);
            ctx.strokeRect(p.x - 2, bottomPipeY, this.width + 4, 20);
        }
    },

    update: function () {
        // Add new pipe every 100 frames
        if (frames % 100 === 0) {
            let minPipeHeight = 50;
            let maxPipeHeight = canvas.height - 20 - this.gap - minPipeHeight;
            let pipeY = Math.random() * (maxPipeHeight - minPipeHeight) + minPipeHeight;
            this.position.push({
                x: canvas.width,
                y: pipeY,
                passed: false
            });
        }

        for (let i = 0; i < this.position.length; i++) {
            let p = this.position[i];
            p.x -= this.dx;

            // Collision Detection
            // Right edge of bird hits left edge of pipe, Left edge of bird hits right edge of pipe
            if (bird.x + bird.width > p.x && bird.x < p.x + this.width) {
                // Top Pipe Collision (bird top hits pipe bottom)
                if (bird.y < p.y) {
                    gameOver();
                }
                // Bottom Pipe Collision (bird bottom hits pipe top)
                if (bird.y + bird.height > p.y + this.gap) {
                    gameOver();
                }
            }

            // Score tracking
            if (p.x + this.width < bird.x && !p.passed) {
                score++;
                currentScoreElement.innerText = score;
                p.passed = true;
            }

            // Remove off-screen pipes
            if (p.x + this.width < 0) {
                this.position.shift();
                i--; // Adjust index since we removed an element
            }
        }
    },

    reset: function () {
        this.position = [];
    }
};

// Background
const background = {
    draw: function () {
        // Ground line
        ctx.fillStyle = '#ded895';
        ctx.fillRect(0, canvas.height - 20, canvas.width, 20);
        ctx.strokeStyle = '#d3ca6b';
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.moveTo(0, canvas.height - 20);
        ctx.lineTo(canvas.width, canvas.height - 20);
        ctx.stroke();
    }
};

// Game Functions
function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height); // Clears the canvas (shows CSS background)

    pipes.draw();
    background.draw();
    bird.draw();
}

function update() {
    if (currentState === GAME_STATE.START) {
        // Bird hovers during start screen
        bird.y = 150 + Math.cos(frames / 10) * 5;
    } else if (currentState === GAME_STATE.PLAYING) {
        bird.update();
        pipes.update();
    }
}

function loop() {
    update();
    draw();
    frames++;
    requestAnimationFrame(loop);
}

function startGame() {
    if (currentState === GAME_STATE.PLAYING) return;

    currentState = GAME_STATE.PLAYING;
    startScreen.classList.remove('active');
    setTimeout(() => { startScreen.classList.add('hidden'); }, 300);
    scoreDisplay.classList.remove('hidden');
    bird.reset();
    pipes.reset();
    score = 0;
    currentScoreElement.innerText = score;
    frames = 0;
}

function gameOver() {
    currentState = GAME_STATE.GAME_OVER;

    // Update Best Score
    if (score > bestScore) {
        bestScore = score;
        localStorage.setItem('flappyBestScore', bestScore);
    }

    // Update Game Over UI
    scoreDisplay.classList.add('hidden');
    finalScoreElement.innerText = score;
    bestScoreElement.innerText = bestScore;

    gameOverScreen.classList.remove('hidden');
    // Tiny delay to allow display block to apply before animating opacity
    setTimeout(() => {
        gameOverScreen.classList.add('active');
    }, 10);
}

function resetGame() {
    gameOverScreen.classList.remove('active');
    setTimeout(() => {
        gameOverScreen.classList.add('hidden');
        startGame();
    }, 300);
}

// Input Handling
function flapInput(e) {
    if (currentState === GAME_STATE.START) {
        startGame();
        bird.flap();
    } else if (currentState === GAME_STATE.PLAYING) {
        bird.flap();
    }
}

window.addEventListener('keydown', (e) => {
    if (e.code === 'Space') {
        flapInput();
    }
});

canvas.addEventListener('click', flapInput);
canvas.addEventListener('touchstart', (e) => {
    e.preventDefault(); // Prevent default scrolling/zooming on touch
    flapInput();
}, { passive: false });

restartBtn.addEventListener('click', resetGame);

// Start loop statically
scoreDisplay.classList.add('hidden');
loop();
