/* Acceleration X-Y scatter panel — 100-point fading trail on a Canvas element. */

const MAX_TRAIL_POINTS = 100;
const AXIS_RANGE_MS2 = 2;

/** @type {HTMLCanvasElement | null} */
let _canvas = null;

/** @type {Array<{x: number, y: number}>} */
const _trailPoints = [];

let _centerX = 0;
let _centerY = 0;
let _pixelsPerMs2 = 0;

/**
 * Initialises the accel scatter panel, wiring up the canvas and resize observer.
 * @returns {void}
 */
export function initAccelScatter() {
    _canvas = document.getElementById('accel-canvas');
    if (_canvas == null) return;
    new ResizeObserver(_onResize).observe(_canvas);
    _onResize();
}

/**
 * Adds a new (accelX, accelY) sample and redraws the scatter panel.
 * @param {number} accelX - X-axis acceleration in m/s².
 * @param {number} accelY - Y-axis acceleration in m/s².
 * @returns {void}
 */
export function updateAccelScatter(accelX, accelY) {
    _trailPoints.push({ x: accelX, y: accelY });
    if (_trailPoints.length > MAX_TRAIL_POINTS) {
        _trailPoints.shift();
    }
    _redraw();
}

function _onResize() {
    if (_canvas == null) return;
    const ratio = window.devicePixelRatio || 1;
    _canvas.width = _canvas.clientWidth * ratio;
    _canvas.height = _canvas.clientHeight * ratio;
    const context = _canvas.getContext('2d');
    if (context != null) {
        context.scale(ratio, ratio);
    }
    _redraw();
}

function _computeLayout() {
    _centerX = _canvas.clientWidth / 2;
    _centerY = _canvas.clientHeight / 2;
    _pixelsPerMs2 = Math.min(_centerX, _centerY) / AXIS_RANGE_MS2;
}

function _redraw() {
    if (_canvas == null) return;
    if (_canvas.clientWidth === 0 || _canvas.clientHeight === 0) return;
    const context = _canvas.getContext('2d');
    if (context == null) return;
    _computeLayout();
    context.clearRect(0, 0, _canvas.clientWidth, _canvas.clientHeight);
    _drawAxes(context);
    _drawTrail(context);
}

function _drawAxes(context) {
    context.strokeStyle = '#444';
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(0, _centerY);
    context.lineTo(_canvas.clientWidth, _centerY);
    context.moveTo(_centerX, 0);
    context.lineTo(_centerX, _canvas.clientHeight);
    context.stroke();
    _drawScale(context);
    _drawLabels(context);
}

function _drawScale(context) {
    const ticks = [-2, -1, 1, 2];
    context.strokeStyle = '#333';
    context.lineWidth = 1;
    for (const tick of ticks) {
        const offset = tick * _pixelsPerMs2;
        context.beginPath();
        context.moveTo(_centerX + offset, _centerY - 4);
        context.lineTo(_centerX + offset, _centerY + 4);
        context.moveTo(_centerX - 4, _centerY - offset);
        context.lineTo(_centerX + 4, _centerY - offset);
        context.stroke();
    }
}

function _drawLabels(context) {
    context.fillStyle = '#666';
    context.font = '11px monospace';
    context.textAlign = 'center';
    context.textBaseline = 'alphabetic';
    context.fillText('X (m/s²)', _centerX, _canvas.clientHeight - 6);
    context.textAlign = 'left';
    context.textBaseline = 'top';
    context.fillText('Y (m/s²)', _centerX + 4, 6);
}

function _drawTrail(context) {
    for (let index = 0; index < _trailPoints.length; index++) {
        _drawPoint(context, index);
    }
    context.globalAlpha = 1;
}

function _drawPoint(context, pointIndex) {
    const alpha = (pointIndex + 1) / _trailPoints.length;
    const point = _trailPoints[pointIndex];
    const pixelX = _centerX + point.x * _pixelsPerMs2;
    const pixelY = _centerY - point.y * _pixelsPerMs2;
    const isNewest = pointIndex === _trailPoints.length - 1;
    context.globalAlpha = alpha;
    context.fillStyle = '#4ec97c';
    context.beginPath();
    context.arc(pixelX, pixelY, isNewest ? 4 : 2, 0, 2 * Math.PI);
    context.fill();
}
