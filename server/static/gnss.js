/* GNSS message handler: Leaflet map marker and status bar updates. */

const FIX_LABEL = { 0: 'Invalid', 1: 'GPS', 2: 'DGPS', 4: 'RTK Fixed', 5: 'RTK Float', 6: 'Dead Reckoning' };
const FIX_CLASS = { 0: 'fix-invalid', 1: 'fix-gps', 2: 'fix-dgps', 4: 'fix-rtk-fixed', 5: 'fix-rtk-float', 6: 'fix-dr' };

const mapEl = document.getElementById('map');
const tileUrl = mapEl.dataset.tileUrl || 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const tileAttribution = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

const map = L.map(mapEl).setView([0, 0], 2);
L.tileLayer(tileUrl, { attribution: tileAttribution, maxZoom: 19 }).addTo(map);

let marker = null;
let centeredOnFix = false;

const statusBar = document.getElementById('status-bar');
const statFix = document.getElementById('stat-fix');
const valFix = document.getElementById('val-fix');
const valLat = document.getElementById('val-lat');
const valLon = document.getElementById('val-lon');
const valAlt = document.getElementById('val-alt');
const valSats = document.getElementById('val-sats');
const wrapSpeed = document.getElementById('wrap-speed');
const valSpeed = document.getElementById('val-speed');
const wrapTrack = document.getElementById('wrap-track');
const valTrack = document.getElementById('val-track');
const valUtc = document.getElementById('val-utc');
let stalenessTimer = null;

function _markStale() { statusBar.classList.add('stale'); }

function _resetStaleness() {
    clearTimeout(stalenessTimer);
    statusBar.classList.remove('stale');
    stalenessTimer = setTimeout(_markStale, 3000);
}

function _updateStatusBar(message, quality, label) {
    valFix.textContent = `${quality} - ${label}`;
    statFix.className = `stat ${FIX_CLASS[quality] ?? 'fix-invalid'}`;
    valLat.textContent = message.lat != null ? message.lat.toFixed(6) : '--';
    valLon.textContent = message.lon != null ? message.lon.toFixed(6) : '--';
    valAlt.textContent = message.alt != null ? message.alt.toFixed(1) : '--';
    valSats.textContent = message.num_satellites ?? '--';
    valUtc.textContent = message.utc_time ?? '--';
}

function _updateSpeedDisplay(message) {
    if (!message.vtg_valid) {
        wrapSpeed.style.display = 'none';
        return;
    }
    wrapSpeed.style.display = '';
    valSpeed.textContent = message.speed_ms != null ? message.speed_ms.toFixed(2) : '--';
}

function _updateTrackDisplay(message) {
    if (!message.vtg_valid || message.track_degrees == null) {
        wrapTrack.style.display = 'none';
        return;
    }
    wrapTrack.style.display = '';
    valTrack.textContent = message.track_degrees.toFixed(1);
}

function _buildPopupNode(label, numSatellites, hdop) {
    const popupNode = document.createElement('div');
    const strongEl = document.createElement('strong');
    strongEl.textContent = label;
    popupNode.appendChild(strongEl);
    popupNode.appendChild(document.createElement('br'));
    popupNode.appendChild(document.createTextNode(`Satellites: ${numSatellites ?? '--'}`));
    popupNode.appendChild(document.createElement('br'));
    popupNode.appendChild(document.createTextNode(`HDOP: ${hdop ?? '--'}`));
    return popupNode;
}

function _positionMarker(latlng, popupNode) {
    const zoom = centeredOnFix ? map.getZoom() : 17;
    centeredOnFix = true;
    map.setView(latlng, zoom);
    if (marker === null) {
        marker = L.marker(latlng).addTo(map).bindPopup(popupNode);
        return;
    }
    marker.setLatLng(latlng);
    marker.getPopup().setContent(popupNode);
}

function _updateMapMarker(message, label) {
    if (message.fix_quality <= 0 || message.lat == null || message.lon == null) return;
    const latlng = [message.lat, message.lon];
    const popupNode = _buildPopupNode(label, message.num_satellites, message.hdop);
    _positionMarker(latlng, popupNode);
}

/**
 * Handles a GNSS WebSocket message: updates the map marker and status bar.
 * @param {Record<string, unknown>} message - Parsed GNSS message object.
 * @returns {void}
 */
export function handleGnss(message) {
    _resetStaleness();
    const quality = message.fix_quality ?? 0;
    const label = FIX_LABEL[quality] ?? `Unknown (${quality})`;
    _updateStatusBar(message, quality, label);
    _updateSpeedDisplay(message);
    _updateTrackDisplay(message);
    _updateMapMarker(message, label);
}
