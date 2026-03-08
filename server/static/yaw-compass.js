/* Yaw rate compass — instantaneous rate sector. */

import { drawCompassRing, drawRateArc, updateReadout } from './yaw-compass-draw.js';

/** @type {HTMLCanvasElement | null} */
let _canvas = null;

/** @type {HTMLElement | null} */
let _readoutElement = null;

/**
 * Initialises the yaw compass panel, wiring up the canvas.
 * @returns {void}
 */
export function initYawCompass() {
    _canvas = /** @type {HTMLCanvasElement | null} */ (document.getElementById('compass-canvas'));
    if (_canvas == null) return;
    _readoutElement = document.getElementById('compass-readout');
    new ResizeObserver(_onResize).observe(_canvas);
    _onResize();
}

/**
 * Redraws the compass with the current gyroZ value.
 * @param {number} gyroZ - Angular rate around the Z axis in rad/s.
 * @returns {void}
 */
export function updateYawCompass(gyroZ) {
    _redraw(gyroZ);
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
    drawRateArc(context, geometry, gyroZ);
    drawCompassRing(context, geometry);
    updateReadout(_readoutElement, gyroZ);
}
