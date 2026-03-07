/* Yaw compass draw helpers — pure rendering functions for the compass canvas. */

const STATIONARY_RATE = 0.05;
const SLOW_RATE = 0.20;
const MODERATE_RATE = 0.50;

/**
 * @typedef {{centerX: number, centerY: number, radius: number}} CompassGeometry
 */

/**
 * @param {number} absGyroZ
 * @returns {string}
 */
function _computeArcColor(absGyroZ) {
    if (absGyroZ <= STATIONARY_RATE) return '#6ab0f5';
    if (absGyroZ <= SLOW_RATE) return '#4ec97c';
    if (absGyroZ <= MODERATE_RATE) return '#d4a835';
    return '#e05555';
}

/**
 * Draws the outer ring of the compass.
 * @param {CanvasRenderingContext2D} context
 * @param {CompassGeometry} geometry
 * @returns {void}
 */
export function drawCompassRing(context, geometry) {
    context.beginPath();
    context.arc(geometry.centerX, geometry.centerY, geometry.radius, 0, 2 * Math.PI);
    context.strokeStyle = '#444';
    context.lineWidth = 2;
    context.stroke();
}

/**
 * Draws a colored arc indicating the current yaw rate magnitude and direction.
 * @param {CanvasRenderingContext2D} context
 * @param {CompassGeometry} geometry
 * @param {number} gyroZ - Angular rate around the Z axis in rad/s.
 * @returns {void}
 */
export function drawRateArc(context, geometry, gyroZ) {
    const arcLength = Math.min(Math.abs(gyroZ), Math.PI);
    const startAngle = -Math.PI / 2;
    const endAngle = startAngle - Math.sign(gyroZ) * arcLength;
    context.beginPath();
    context.arc(geometry.centerX, geometry.centerY, geometry.radius, startAngle, endAngle, gyroZ > 0);
    context.strokeStyle = _computeArcColor(Math.abs(gyroZ));
    context.lineWidth = 6;
    context.stroke();
}

/**
 * Updates the yaw rate readout text element.
 * @param {HTMLElement | null} element
 * @param {number} gyroZ - Angular rate around the Z axis in rad/s.
 * @returns {void}
 */
export function updateReadout(element, gyroZ) {
    if (element == null) return;
    const degreesPerSecond = (gyroZ * 180 / Math.PI).toFixed(1);
    const sign = gyroZ >= 0 ? '+' : '';
    element.textContent = `${sign}${degreesPerSecond} °/s`;
}
