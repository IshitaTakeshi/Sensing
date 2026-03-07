/* Sensing Dashboard — entry point: WebSocket connection and message dispatch. */

import { handleGnss } from './gnss.js';
import { initAccelScatter, updateAccelScatter } from './accel-scatter.js';
import { initYawCompass, updateYawCompass } from './yaw-compass.js';

function _handleImu(message) {
    updateAccelScatter(message.accel_x, message.accel_y);
    updateYawCompass(message.gyro_z);
}

function _dispatchMessage(message) {
    if (message.type === 'gnss') handleGnss(message);
    if (message.type === 'imu') _handleImu(message);
}

function _parseMessage(data) {
    try {
        return JSON.parse(data);
    } catch {
        return null;
    }
}

function _onMessage(event) {
    const message = _parseMessage(event.data);
    if (message == null) return;
    _dispatchMessage(message);
}

function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const webSocket = new WebSocket(`${protocol}//${location.host}/ws`);
    webSocket.addEventListener('message', _onMessage);
    webSocket.addEventListener('close', () => setTimeout(connect, 2000));
}

initAccelScatter();
initYawCompass();
connect();
