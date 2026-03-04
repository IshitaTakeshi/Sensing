/* Yaw rate compass — integrated heading needle and instantaneous rate arc. */

const STATIONARY_RATE = 0.05;
const SLOW_RATE = 0.20;
const MODERATE_RATE = 0.50;
const MAX_DELTA_TIME_SECONDS = 0.2;

/** @type {HTMLCanvasElement | null} */
let _canvas = null;

/** @type {HTMLElement | null} */
let _readoutElement = null;

let _integratedHeading = 0;

/** @type {number | null} */
let _lastTimestampNanoseconds = null;

let _centerX = 0;
let _centerY = 0;
let _radius = 0;

/**
 * Initialises the yaw compass panel, wiring up the canvas and reset button.
 * @returns {void}
 */
export function initYawCompass() {
    _canvas = /** @type {HTMLCanvasElement | null} */ (document.getElementById('compass-canvas'));
    if (_canvas == null) return;
    _readoutElement = document.getElementById('compass-readout');
    const resetButton = document.getElementById('reset-heading-button');
    if (resetButton != null) {
        resetButton.addEventListener('click', _resetHeading);
    }
    new ResizeObserver(_onResize).observe(_canvas);
    _onResize();
}

/**
 * Integrates gyroZ over the elapsed time and redraws the compass.
 * @param {number} gyroZ - Angular rate around the Z axis in rad/s.
 * @param {number} timestampNanoseconds - Sample timestamp in nanoseconds.
 * @returns {void}
 */
export function updateYawCompass(gyroZ, timestampNanoseconds) {
    if (_lastTimestampNanoseconds == null) {
        _lastTimestampNanoseconds = timestampNanoseconds;
        _redraw(gyroZ);
        return;
    }
    const deltaTime = (timestampNanoseconds - _lastTimestampNanoseconds) / 1e9;
    _lastTimestampNanoseconds = timestampNanoseconds;
    if (deltaTime <= 0) {
        _redraw(gyroZ);
        return;
    }
    const clampedDelta = Math.min(deltaTime, MAX_DELTA_TIME_SECONDS);
    _integratedHeading = (_integratedHeading + gyroZ * clampedDelta) % (2 * Math.PI);
    _redraw(gyroZ);
}

function _resetHeading() {
    _integratedHeading = 0;
    _lastTimestampNanoseconds = /** @type {number | null} */ (null);
    _redraw(0);
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
    _redraw(0);
}

function _computeCompassLayout() {
    _centerX = _canvas.clientWidth / 2;
    _centerY = _canvas.clientHeight / 2;
    _radius = Math.min(_centerX, _centerY) - 10;
}

function _redraw(gyroZ) {
    if (_canvas == null) return;
    if (_canvas.clientWidth === 0 || _canvas.clientHeight === 0) return;
    const context = _canvas.getContext('2d');
    if (context == null) return;
    _computeCompassLayout();
    context.clearRect(0, 0, _canvas.clientWidth, _canvas.clientHeight);
    _drawCompassRing(context);
    _drawRateArc(context, gyroZ);
    _drawHeadingNeedle(context);
    _updateReadout(gyroZ);
}

function _computeArcColor(absGyroZ) {
    if (absGyroZ <= STATIONARY_RATE) return '#6ab0f5';
    if (absGyroZ <= SLOW_RATE) return '#4ec97c';
    if (absGyroZ <= MODERATE_RATE) return '#d4a835';
    return '#e05555';
}

function _drawCompassRing(context) {
    context.beginPath();
    context.arc(_centerX, _centerY, _radius, 0, 2 * Math.PI);
    context.strokeStyle = '#444';
    context.lineWidth = 2;
    context.stroke();
}

function _drawHeadingNeedle(context) {
    const needleAngle = _integratedHeading - Math.PI / 2;
    const tipX = _centerX + _radius * 0.8 * Math.cos(needleAngle);
    const tipY = _centerY + _radius * 0.8 * Math.sin(needleAngle);
    context.beginPath();
    context.moveTo(_centerX, _centerY);
    context.lineTo(tipX, tipY);
    context.strokeStyle = '#d0d0d0';
    context.lineWidth = 2;
    context.stroke();
}

function _drawRateArc(context, gyroZ) {
    const arcLength = Math.min(Math.abs(gyroZ), Math.PI);
    const startAngle = -Math.PI / 2;
    const endAngle = startAngle + Math.sign(gyroZ) * arcLength;
    context.beginPath();
    context.arc(_centerX, _centerY, _radius, startAngle, endAngle, gyroZ < 0);
    context.strokeStyle = _computeArcColor(Math.abs(gyroZ));
    context.lineWidth = 6;
    context.stroke();
}

function _updateReadout(gyroZ) {
    if (_readoutElement == null) return;
    const degreesPerSecond = (gyroZ * 180 / Math.PI).toFixed(1);
    const sign = gyroZ >= 0 ? '+' : '';
    _readoutElement.textContent = `${sign}${degreesPerSecond} °/s`;
}
