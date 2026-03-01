/* Sensing Dashboard - WebSocket client, Leaflet map, and GNSS status bar. */
'use strict';

// Fix quality codes -> human-readable labels and CSS class names.
const FIX_LABEL = {
    0: 'Invalid',
    1: 'GPS',
    2: 'DGPS',
    4: 'RTK Fixed',
    5: 'RTK Float',
    6: 'Dead Reckoning',
};

const FIX_CLASS = {
    0: 'fix-invalid',
    1: 'fix-gps',
    2: 'fix-dgps',
    4: 'fix-rtk-fixed',
    5: 'fix-rtk-float',
    6: 'fix-dr',
};

// --- Map ---

const map = L.map('map').setView([0, 0], 2);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
}).addTo(map);

let marker = null;
let centeredOnFix = false;

// --- Status bar ---

const statusBar = document.getElementById('status-bar');
const statFix   = document.getElementById('stat-fix');
const valFix    = document.getElementById('val-fix');
const valLat    = document.getElementById('val-lat');
const valLon    = document.getElementById('val-lon');
const valAlt    = document.getElementById('val-alt');
const valSats   = document.getElementById('val-sats');
const wrapSpeed = document.getElementById('wrap-speed');
const valSpeed  = document.getElementById('val-speed');
const wrapTrack = document.getElementById('wrap-track');
const valTrack  = document.getElementById('val-track');
const valUtc    = document.getElementById('val-utc');

let stalenessTimer = null;

function markStale() {
    statusBar.classList.add('stale');
}

function resetStaleness() {
    clearTimeout(stalenessTimer);
    statusBar.classList.remove('stale');
    stalenessTimer = setTimeout(markStale, 3000);
}

// --- GNSS message handler ---

function handleGnss(msg) {
    resetStaleness();

    const quality = msg.fix_quality ?? 0;
    const label = FIX_LABEL[quality] ?? `Unknown (${quality})`;

    valFix.textContent = `${quality} - ${label}`;
    statFix.className = `stat ${FIX_CLASS[quality] ?? 'fix-invalid'}`;

    valLat.textContent  = msg.lat != null ? msg.lat.toFixed(6) : '--';
    valLon.textContent  = msg.lon != null ? msg.lon.toFixed(6) : '--';
    valAlt.textContent  = msg.alt != null ? msg.alt.toFixed(1) : '--';
    valSats.textContent = msg.num_satellites ?? '--';
    valUtc.textContent  = msg.utc_time ?? '--';

    // Speed: visible when vtg_valid is truthy.
    if (msg.vtg_valid) {
        wrapSpeed.style.display = '';
        valSpeed.textContent = msg.speed_ms != null ? msg.speed_ms.toFixed(2) : '--';
    } else {
        wrapSpeed.style.display = 'none';
    }

    // Track: visible when vtg_valid and track_degrees is not null.
    if (msg.vtg_valid && msg.track_degrees != null) {
        wrapTrack.style.display = '';
        valTrack.textContent = msg.track_degrees.toFixed(1);
    } else {
        wrapTrack.style.display = 'none';
    }

    // Update map marker on a valid fix with known coordinates.
    if (quality > 0 && msg.lat != null && msg.lon != null) {
        const latlng = [msg.lat, msg.lon];

        // Pan to first valid fix; user can pan freely after that.
        if (!centeredOnFix) {
            map.setView(latlng, 17);
            centeredOnFix = true;
        }

        const popupHtml =
            `<strong>${label}</strong><br>` +
            `Satellites: ${msg.num_satellites ?? '--'}<br>` +
            `HDOP: ${msg.hdop ?? '--'}`;

        if (marker === null) {
            marker = L.marker(latlng).addTo(map).bindPopup(popupHtml);
        } else {
            marker.setLatLng(latlng);
            marker.getPopup().setContent(popupHtml);
        }
    }
}

// --- WebSocket with auto-reconnect ---

function connect() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${location.host}/ws`);

    ws.addEventListener('message', (event) => {
        let msg;
        try {
            msg = JSON.parse(event.data);
        } catch {
            return;
        }

        if (msg.type === 'gnss') {
            handleGnss(msg);
        }
        // msg.type === 'imu' will be handled in #40.
    });

    ws.addEventListener('close', () => setTimeout(connect, 2000));
}

connect();
