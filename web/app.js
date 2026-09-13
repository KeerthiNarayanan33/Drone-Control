/**
 * AeroFlight MK-1 Controller Logic
 * Virtual touch joysticks, keyboard mapping, WebSocket bridge, and HUD management.
 */

// State
let ws = null;
let isConnected = false;
let isSpeedFast = false;
let autoNeutralTimer = null;

// Stick Values (1-255, neutral 128)
const NEUTRAL = 128;
let roll = NEUTRAL;
let pitch = NEUTRAL;
let throttle = NEUTRAL;
let yaw = NEUTRAL;

// DOM Elements
const connectionBadge = document.getElementById('connectionBadge');
const connectionText = document.getElementById('connectionText');
const btnConnect = document.getElementById('btnConnect');
const livePacketHex = document.getElementById('livePacketHex');
const fpsVal = document.getElementById('fpsVal');
const resVal = document.getElementById('resVal');

const valThrottle = document.getElementById('valThrottle');
const valYaw = document.getElementById('valYaw');
const valPitch = document.getElementById('valPitch');
const valRoll = document.getElementById('valRoll');

// Buttons
const btnTakeoff = document.getElementById('btnTakeoff');
const btnLand = document.getElementById('btnLand');
const btnEmergency = document.getElementById('btnEmergency');
const btnGyroCal = document.getElementById('btnGyroCal');
const btnCameraSwitch = document.getElementById('btnCameraSwitch');
const btnSpeedToggle = document.getElementById('btnSpeedToggle');
const speedModeLabel = document.getElementById('speedModeLabel');

// Settings Modal
const btnSettings = document.getElementById('btnSettings');
const modalSettings = document.getElementById('modalSettings');
const btnCloseSettings = document.getElementById('btnCloseSettings');
const btnSaveSettings = document.getElementById('btnSaveSettings');
const inputSpeedLimit = document.getElementById('inputSpeedLimit');
const lblSpeedLimit = document.getElementById('lblSpeedLimit');
const inputDeadZone = document.getElementById('inputDeadZone');
const lblDeadZone = document.getElementById('lblDeadZone');
const inputWatchdog = document.getElementById('inputWatchdog');
const lblWatchdog = document.getElementById('lblWatchdog');
const chkYawDeadband = document.getElementById('chkYawDeadband');
const inputDroneIp = document.getElementById('inputDroneIp');
const inputDronePort = document.getElementById('inputDronePort');

// Dev Drawer
const btnDevMode = document.getElementById('btnDevMode');
const drawerDevMode = document.getElementById('drawerDevMode');
const btnCloseDev = document.getElementById('btnCloseDev');
const devSentCount = document.getElementById('devSentCount');
const devRecvCount = document.getElementById('devRecvCount');
const devHbCount = document.getElementById('devHbCount');
const devLastTxHex = document.getElementById('devLastTxHex');
const devLastRxHex = document.getElementById('devLastRxHex');
const devLogContainer = document.getElementById('devLogContainer');

// Fullscreen
const btnFullscreen = document.getElementById('btnFullscreen');

// -------------------------------------------------------------
// WEBSOCKET BRIDGE
// -------------------------------------------------------------
function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log('[WS] Connected to bridge server');
  };

  ws.onmessage = (event) => {
    try {
      const data = jsonParseSafe(event.data);
      if (!data) return;

      if (data.type === 'status') {
        updateHUDStatus(data);
      }
    } catch (e) {
      console.error('[WS] Parse error:', e);
    }
  };

  ws.onclose = () => {
    console.warn('[WS] Closed. Reconnecting in 1.5s...');
    setTimeout(initWebSocket, 1500);
  };

  ws.onerror = (err) => {
    console.error('[WS] Error:', err);
  };
}

function sendCommand(msgObj) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msgObj));
  }
}

function sendStickUpdate() {
  sendCommand({
    type: 'sticks',
    roll: roll,
    pitch: pitch,
    throttle: throttle,
    yaw: yaw
  });
}

function jsonParseSafe(str) {
  try { return JSON.parse(str); } catch { return null; }
}

// -------------------------------------------------------------
// HUD & STATUS UPDATES
// -------------------------------------------------------------
function updateHUDStatus(status) {
  isConnected = status.connected;

  if (isConnected) {
    connectionBadge.className = 'status-badge connected';
    connectionText.textContent = 'ONLINE // 192.168.1.1';
    btnConnect.textContent = 'DISCONNECT';
    btnConnect.classList.add('connected');
  } else {
    connectionBadge.className = 'status-badge disconnected';
    connectionText.textContent = 'DISCONNECTED';
    btnConnect.textContent = 'CONNECT';
    btnConnect.classList.remove('connected');
  }

  // Video info
  if (status.video) {
    fpsVal.textContent = status.video.fps.toFixed(1);
    resVal.textContent = status.video.resolution || 'OFFLINE';
  }

  // Active Hex
  if (status.last_sent_hex) {
    livePacketHex.textContent = formatHexWithSpaces(status.last_sent_hex);
    devLastTxHex.textContent = formatHexWithSpaces(status.last_sent_hex);
  }
  if (status.last_recv_hex) {
    devLastRxHex.textContent = formatHexWithSpaces(status.last_recv_hex);
  }

  // Dev metrics
  devSentCount.textContent = status.packets_sent || 0;
  devRecvCount.textContent = status.packets_recv || 0;
  devHbCount.textContent = status.heartbeats_sent || 0;

  // Render logs
  if (status.logs && status.logs.length > 0) {
    renderDevLogs(status.logs);
  }
}

function formatHexWithSpaces(hexStr) {
  return hexStr.match(/.{1,2}/g)?.join(' ') || hexStr;
}

function renderDevLogs(logs) {
  devLogContainer.innerHTML = '';
  logs.forEach(log => {
    const div = document.createElement('div');
    div.className = `log-entry ${log.level.toLowerCase()}`;
    div.textContent = `[${log.timestamp}] [${log.level}] ${log.message}`;
    devLogContainer.appendChild(div);
  });
  devLogContainer.scrollTop = devLogContainer.scrollHeight;
}

// -------------------------------------------------------------
// VIRTUAL JOYSTICK ENGINE (TOUCH & POINTER)
// -------------------------------------------------------------
function setupJoystick(padId, knobId, onMoveCallback, onReleaseCallback) {
  const pad = document.getElementById(padId);
  const knob = document.getElementById(knobId);
  const radius = 70; // Max movement radius in px

  let activePointerId = null;

  function updateKnob(clientX, clientY) {
    const rect = pad.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;

    let dx = clientX - centerX;
    let dy = clientY - centerY;

    const distance = Math.sqrt(dx * dx + dy * dy);
    if (distance > radius) {
      dx = (dx / distance) * radius;
      dy = (dy / distance) * radius;
    }

    knob.style.transform = `translate(${dx}px, ${dy}px)`;

    // Normalized coordinates from -1.0 to 1.0
    const normX = dx / radius;
    const normY = dy / radius;

    onMoveCallback(normX, normY);
  }

  function resetKnob() {
    knob.style.transform = 'translate(0px, 0px)';
    onReleaseCallback();
  }

  pad.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    activePointerId = e.pointerId;
    pad.setPointerCapture(activePointerId);
    updateKnob(e.clientX, e.clientY);
  });

  pad.addEventListener('pointermove', (e) => {
    if (e.pointerId === activePointerId) {
      e.preventDefault();
      updateKnob(e.clientX, e.clientY);
    }
  });

  const onEnd = (e) => {
    if (e.pointerId === activePointerId) {
      e.preventDefault();
      activePointerId = null;
      try { pad.releasePointerCapture(e.pointerId); } catch {}
      resetKnob();
    }
  };

  pad.addEventListener('pointerup', onEnd);
  pad.addEventListener('pointercancel', onEnd);
}

// Left Stick (Throttle: Y invert, Yaw: X)
setupJoystick(
  'padLeft',
  'knobLeft',
  (normX, normY) => {
    // Up is positive throttle (128 -> 255), Down is negative throttle (128 -> 1)
    // normY is positive downwards in screen space
    throttle = Math.round(128 - normY * 127);
    yaw = Math.round(128 + normX * 127);

    throttle = Math.max(1, Math.min(255, throttle));
    yaw = Math.max(1, Math.min(255, yaw));

    valThrottle.textContent = throttle;
    valYaw.textContent = yaw;
    sendStickUpdate();
  },
  () => {
    throttle = NEUTRAL;
    yaw = NEUTRAL;
    valThrottle.textContent = NEUTRAL;
    valYaw.textContent = NEUTRAL;
    sendStickUpdate();
  }
);

// Right Stick (Pitch: Y invert, Roll: X)
setupJoystick(
  'padRight',
  'knobRight',
  (normX, normY) => {
    // Up is forward pitch (128 -> 255), Down is backward pitch (128 -> 1)
    pitch = Math.round(128 - normY * 127);
    roll = Math.round(128 + normX * 127);

    pitch = Math.max(1, Math.min(255, pitch));
    roll = Math.max(1, Math.min(255, roll));

    valPitch.textContent = pitch;
    valRoll.textContent = roll;
    sendStickUpdate();
  },
  () => {
    pitch = NEUTRAL;
    roll = NEUTRAL;
    valPitch.textContent = NEUTRAL;
    valRoll.textContent = NEUTRAL;
    sendStickUpdate();
  }
);

// -------------------------------------------------------------
// KEYBOARD CONTROLS FOR DESKTOP / LAPTOP OPERATION
// -------------------------------------------------------------
const keysPressed = {};

window.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT') return;
  keysPressed[e.code] = true;
  handleKeyboardFlight();
});

window.addEventListener('keyup', (e) => {
  if (e.target.tagName === 'INPUT') return;
  delete keysPressed[e.code];
  handleKeyboardFlight();
});

function handleKeyboardFlight() {
  let t = NEUTRAL;
  let y = NEUTRAL;
  let p = NEUTRAL;
  let r = NEUTRAL;

  const step = 60; // Moderate keyboard deflection

  // Left stick: W/S = Throttle, A/D = Yaw
  if (keysPressed['KeyW']) t += step;
  if (keysPressed['KeyS']) t -= step;
  if (keysPressed['KeyA']) y -= step;
  if (keysPressed['KeyD']) y += step;

  // Right stick: ArrowUp/ArrowDown = Pitch, ArrowLeft/ArrowRight = Roll
  if (keysPressed['ArrowUp']) p += step;
  if (keysPressed['ArrowDown']) p -= step;
  if (keysPressed['ArrowLeft']) r -= step;
  if (keysPressed['ArrowRight']) r += step;

  throttle = Math.max(1, Math.min(255, t));
  yaw = Math.max(1, Math.min(255, y));
  pitch = Math.max(1, Math.min(255, p));
  roll = Math.max(1, Math.min(255, r));

  valThrottle.textContent = throttle;
  valYaw.textContent = yaw;
  valPitch.textContent = pitch;
  valRoll.textContent = roll;

  sendStickUpdate();
}

// -------------------------------------------------------------
// FLIGHT BUTTON ACTIONS
// -------------------------------------------------------------
btnConnect.addEventListener('click', () => {
  if (isConnected) {
    sendCommand({ type: 'disconnect' });
  } else {
    sendCommand({
      type: 'connect',
      ip: inputDroneIp.value.trim() || '192.168.1.1',
      port: parseInt(inputDronePort.value.trim()) || 7099
    });
  }
});

btnTakeoff.addEventListener('click', () => {
  if (confirm('Engage motors and initiate Auto-Takeoff?')) {
    sendCommand({ type: 'takeoff' });
  }
});

btnLand.addEventListener('click', () => {
  sendCommand({ type: 'land' });
});

// Guarded Emergency Stop
btnEmergency.addEventListener('click', () => {
  if (confirm('⚠ EMERGENCY STOP: Immediate rotor shutdown! Are you sure?')) {
    sendCommand({ type: 'emergency' });
    // Reset sticks
    throttle = 0;
    roll = NEUTRAL;
    pitch = NEUTRAL;
    yaw = NEUTRAL;
    valThrottle.textContent = '0';
  }
});

btnGyroCal.addEventListener('click', () => {
  sendCommand({ type: 'gyro_cal' });
  alert('Gyroscope calibration pulse sent. Ensure drone is on a level surface.');
});

btnCameraSwitch.addEventListener('click', () => {
  sendCommand({ type: 'camera_switch' });
});

btnSpeedToggle.addEventListener('click', () => {
  isSpeedFast = !isSpeedFast;
  speedModeLabel.textContent = isSpeedFast ? 'FAST (HIGH)' : 'NORMAL';
  sendCommand({ type: 'speed_mode', fast: isSpeedFast });
});

// -------------------------------------------------------------
// SETTINGS MODAL
// -------------------------------------------------------------
btnSettings.addEventListener('click', () => modalSettings.classList.remove('hidden'));
btnCloseSettings.addEventListener('click', () => modalSettings.classList.add('hidden'));

inputSpeedLimit.addEventListener('input', (e) => {
  lblSpeedLimit.textContent = `${e.target.value}%`;
});

inputDeadZone.addEventListener('input', (e) => {
  lblDeadZone.textContent = `±${e.target.value}`;
});

inputWatchdog.addEventListener('input', (e) => {
  lblWatchdog.textContent = `${e.target.value} ms`;
});

btnSaveSettings.addEventListener('click', () => {
  sendCommand({
    type: 'settings',
    speed_limit_pct: parseFloat(inputSpeedLimit.value),
    dead_zone: parseInt(inputDeadZone.value),
    watchdog_timeout_sec: parseFloat(inputWatchdog.value) / 1000.0,
    yaw_hardware_deadband: chkYawDeadband.checked
  });
  modalSettings.classList.add('hidden');
});

// -------------------------------------------------------------
// DEVELOPER DRAWER
// -------------------------------------------------------------
btnDevMode.addEventListener('click', () => drawerDevMode.classList.toggle('hidden'));
btnCloseDev.addEventListener('click', () => drawerDevMode.classList.add('hidden'));

// -------------------------------------------------------------
// FULLSCREEN
// -------------------------------------------------------------
btnFullscreen.addEventListener('click', () => {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else {
    document.exitFullscreen().catch(() => {});
  }
});

// Initialize on page load
window.addEventListener('DOMContentLoaded', () => {
  initWebSocket();
});
