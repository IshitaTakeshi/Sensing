/* Yaw rate compass — integrated heading needle and instantaneous rate arc. */

import { drawCompassRing, drawRateArc, drawHeadingNeedle, updateReadout } from './yaw-compass-draw.js';

const MAX_DELTA_TIME_SECONDS = 0.2;

/** @type {HTMLCanvasElement | null} */
let _canvas = null;

/** @type {HTMLElement | null} */
let _readoutElement = null;

let _integratedHeading = 0;

/** @type {number | null} */
let _lastTimestampNanoseconds = null;

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
    _integratedHeading = _integrate(_integratedHeading, deltaTime, gyroZ);
    _redraw(gyroZ);
}

/**
 * @returns {void}
 */
function _resetHeading() {
    _integratedHeading = 0;
    _lastTimestampNanoseconds = /** @type {number | null} */ (null);
    _redraw(0);
}

/**
 * @returns {void}
 */
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

/**
 * @param {number} currentHeading - Current integrated heading in radians.
 * @param {number} deltaTime - Elapsed time in seconds.
 * @param {number} gyroZ - Angular rate around the Z axis in rad/s.
 * @returns {number} New integrated heading in radians.
 */
function _integrate(currentHeading, deltaTime, gyroZ) {
    const clampedDelta = Math.min(deltaTime, MAX_DELTA_TIME_SECONDS);
    return (currentHeading + gyroZ * clampedDelta) % (2 * Math.PI);
}

/**
 * @param {HTMLCanvasElement} canvas
 * @returns {{centerX: number, centerY: number, radius: number}}
 */
function _computeCompassGeometry(canvas) {
    const centerX = canvas.clientWidth / 2;
    const centerY = canvas.clientHeight / 2;
    const radius = Math.min(centerX, centerY) - 10;
    return { centerX, centerY, radius };
}

/**
 * @param {number} gyroZ
 * @returns {void}
 */
function _redraw(gyroZ) {
    if (_canvas == null) return;
    if (_canvas.clientWidth === 0 || _canvas.clientHeight === 0) return;
    const context = _canvas.getContext('2d');
    if (context == null) return;
    const geometry = _computeCompassGeometry(_canvas);
    context.clearRect(0, 0, _canvas.clientWidth, _canvas.clientHeight);
    drawCompassRing(context, geometry);
    drawRateArc(context, geometry, gyroZ);
    drawHeadingNeedle(context, geometry, _integratedHeading);
    updateReadout(_readoutElement, gyroZ);
}
