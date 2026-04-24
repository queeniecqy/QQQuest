#!/usr/bin/env node
/**
 * Room TCP/IP Socket Server
 * 為每個房間啟動一個獨立的 TCP/IP Socket Server
 * Protocol updated to match Unity Client requirements.
 */

const net = require('net');
const path = require('path');
const fs = require('fs');
const { execFile } = require('child_process');

// 從命令行參數獲取配置
const args = process.argv.slice(2);
const roomId = args[0];
const roomName = args[1];
const socketIp = args[2] || '0.0.0.0';
const socketPort = parseInt(args[3]) || 3000;

const ADB_BIN = process.env.ADB || 'adb';
const AUTO_RESUME_ENABLED = process.env.QQQUEST_AUTO_RESUME_ENABLED !== '0';
const AUTO_RESUME_PACKAGE = process.env.QQQUEST_AUTO_RESUME_PACKAGE || 'com.Awespire.OrientalBeauty';
const AUTO_RESUME_ACTIVITY = process.env.QQQUEST_AUTO_RESUME_ACTIVITY || 'com.unity3d.player.UnityPlayerGameActivity';
const AUTO_RESUME_ADB_PORT = process.env.QQQUEST_AUTO_RESUME_ADB_PORT || '5555';
const AUTO_RESUME_COOLDOWN_MS = parseInt(process.env.QQQUEST_AUTO_RESUME_COOLDOWN_MS || '5000', 10);
const AUTO_RESUME_COMMAND_TIMEOUT_MS = parseInt(process.env.QQQUEST_AUTO_RESUME_COMMAND_TIMEOUT_MS || '6000', 10);
const USER_POSITION_SYNC_CHAPTER = parseInt(process.env.QQQUEST_USER_POSITION_SYNC_CHAPTER || '5', 10);
const USER_POSITION_COMMAND_COOLDOWN_MS = parseInt(process.env.QQQUEST_USER_POSITION_COMMAND_COOLDOWN_MS || '1500', 10);

if (!roomId || !roomName) {
    console.error('❌ 錯誤：缺少必要參數');
    console.error('用法: node room_socket_server.js <room_id> <room_name> [ip] [port]');
    process.exit(1);
}

// 日誌設置
const logDir = path.join(__dirname, '..', 'logs', 'socket_servers');
if (!fs.existsSync(logDir)) {
    fs.mkdirSync(logDir, { recursive: true });
}

const logFile = path.join(logDir, `room_${roomId}_${socketPort}.log`);

function log(message) {
    const timestamp = new Date().toISOString();
    const logMessage = `[${timestamp}] ${message}`;
    console.log(logMessage);
}

// --------------------------------------------------------------------------
// State Management
// --------------------------------------------------------------------------

// 保存所有連接的客戶端
const clients = new Map();
// 保存玩家信息: device_id -> { sequence, chapter, last_heartbeat_time, socket }
const players = new Map();
const autoResumeState = new Map();
let desiredUserPositionZ = null;

// 序列號計數器
let sequenceCounter = 0;

// --------------------------------------------------------------------------
// Server Logic
// --------------------------------------------------------------------------

const server = net.createServer((socket) => {
    const clientAddress = `${socket.remoteAddress}:${socket.remotePort}`;
    log(`✅ 新客戶端連接: ${clientAddress} (房間: ${roomName})`);
    socket.setNoDelay(true);

    // 初始化客戶端基礎信息
    const clientInfo = {
        socket: socket,
        address: clientAddress,
        device_id: null,
        is_server: false,
        connected_at: new Date()
    };

    clients.set(socket, clientInfo);

    // 處理接收到的數據 (Socket Stream Parser)
    let buffer = '';

    socket.on('data', (data) => {
        buffer += data.toString();

        // 簡單的括號計數解析器 (Bracket Counting Parser)
        // 支持 NDJSON 和 Pretty Printed JSON
        let startIndex = 0;
        let braceCount = 0;
        let inString = false;
        let escaped = false;

        for (let i = 0; i < buffer.length; i++) {
            const char = buffer[i];

            if (!inString) {
                if (char === '{') {
                    if (braceCount === 0) {
                        startIndex = i;
                    }
                    braceCount++;
                } else if (char === '}') {
                    braceCount--;
                    if (braceCount === 0) {
                        // 找到一個完整的 JSON 對象
                        const jsonStr = buffer.substring(startIndex, i + 1);
                        try {
                            const message = JSON.parse(jsonStr);

                            // Log filtering for clean UI
                            if (message.message_type !== 'heartbeat') {
                                log(`📨 收到消息 (${clientInfo.device_id || clientAddress}): ${JSON.stringify(message)}`);
                            }
                            // else {
                            // log(`💓 Heartbeat from ${clientInfo.device_id}`);
                            // }

                            handleMessage(socket, message, clientInfo);

                        } catch (e) {
                            log(`⚠️ 解析消息失敗 (${clientAddress}): ${e.message}`);
                        }

                        // 移動緩衝區
                        buffer = buffer.substring(i + 1);
                        i = -1; // reset loop relative to new buffer
                        inString = false;
                        escaped = false;
                    }
                    else if (braceCount < 0) {
                        // 異常情況：多了右括號，可能是雜訊或不完整的流
                        // 重置
                        braceCount = 0;
                        buffer = buffer.substring(i + 1);
                        i = -1;
                    }
                } else if (char === '"') {
                    inString = true;
                }
            } else {
                // In String
                if (!escaped && char === '"') {
                    inString = false;
                } else if (!escaped && char === '\\') {
                    escaped = true;
                    continue; // Skip resetting escaped flag
                }
                escaped = false;
            }
        }

        // 防止緩衝區過大 (例如異常數據導致永遠不閉合)
        if (buffer.length > 1024 * 1024) { // 1MB Limit
            log(`⚠️ 緩衝區溢出，清空數據 (${clientAddress})`);
            buffer = '';
        }
    });

    socket.on('close', () => {
        log(`❌ 客戶端斷開連接: ${clientInfo.device_id || clientAddress}`);

        // 移除玩家記錄
        if (clientInfo.device_id && players.has(clientInfo.device_id)) {
            // 注意：我們可能想保留 sequence 一段時間以便重連？
            // 根據需求，這裡暫時完全移除，或者保留在 players map 但 socket 為 null
            players.delete(clientInfo.device_id);
            log(`🗑️ 移除玩家記錄: ${clientInfo.device_id}`);
        }

        clients.delete(socket);
    });

    socket.on('error', (err) => {
        log(`❌ Socket 錯誤 (${clientAddress}): ${err.message}`);
    });
});

/**
 * 處理消息分發
 */
function handleMessage(socket, message, clientInfo) {
    // 優先檢查 standard Unity format: { "message_type": "..." }
    // 老協議使用 { "type": "..." }

    const msgType = message.message_type || message.type;

    switch (msgType) {
        // -------------------------
        // Core Unity Protocol
        // -------------------------

        case 'heartbeat':
            handleHeartbeat(socket, message, clientInfo);
            break;

        case 'identify':
            handleIdentify(socket, message, clientInfo);
            break;

        case 'ready_to_move':
            handleReadyToMove(socket, message, clientInfo);
            break;

        case 'focus_state':
            handleFocusState(socket, message, clientInfo);
            break;

        case 'user_transform_sync':
            handleUserTransformSync(socket, message, clientInfo);
            break;

        // -------------------------
        // Legacy / Admin Protocol
        // -------------------------

        case 'login': // Admin or Debug client login
            handleLogin(socket, message, clientInfo);
            break;

        case 'admin_broadcast': // Python UI Command
            handleAdminBroadcast(socket, message, clientInfo);
            break;

        case 'reset_sequences': // Python UI Command
            handleResetSequences(socket, message, clientInfo);
            break;

        case 'admin_unicast': // Python UI Command
            handleAdminUnicast(socket, message, clientInfo);
            break;

        case 'set_user_position_target':
            handleSetUserPositionTarget(socket, message, clientInfo);
            break;

        case 'who':
            handleWho(socket, message, clientInfo);
            break;

        default:
            // 轉發未知消息？或者忽略
            log(`⚠️ 未知消息類型: ${msgType}`);
    }
}

// --------------------------------------------------------------------------
// Handlers
// --------------------------------------------------------------------------


/**
 * 處理心跳
 * 更新玩家狀態並回復 PositionInfo (Update)
 */
function handleHeartbeat(socket, message, clientInfo) {
    // Payload structure: { message_type: 'heartbeat', heartbeat: { device_id: '...', chapter: number, ... } }
    const hb = message.heartbeat;
    if (!hb || !hb.device_id) return;

    const deviceId = hb.device_id;
    clientInfo.device_id = deviceId; // Ensure bind

    // Update Player State
    let player = players.get(deviceId);
    if (!player) {
        // 新玩家 (或者 identify 沒調用直接發 heartbeat)
        player = createPlayer(deviceId, socket);
    }

    // Update data
    player.socket = socket; // 更新 socket 引用 (重連情況)
    player.last_heartbeat_time = Date.now();
    player.chapter = normalizeChapter(hb.chapter, player.chapter);
    player.message = hb.message;      // Store custom message (e.g. time string)
    player.timestamp = hb.timestamp;  // Store timestamp
    player.address = normalizeRemoteAddress(socket.remoteAddress);

    // Respond with PositionInfo (Update)
    // Unity expects: PositionInfo { player_count, ... }
    // Unity MsgType: "update"
    const response = {
        message_type: "update",
        player_count: players.size,
        timestamp: Date.now()
    };

    sendJson(socket, response);
    maybeApplySavedUserPositionTarget(player, `heartbeat_chapter_${player.chapter}`);
}

// ... existing code ...

/**
 * 處理 Who 指令 (Admin/Debug)
 * 返回當前所有連線玩家信息
 */
function handleWho(socket, message, clientInfo) {
    const playerList = [];
    players.forEach((p, deviceId) => {
        playerList.push({
            device_id: deviceId,
            chapter: p.chapter,
            sequence: p.sequence,
            message: p.message,
            timestamp: p.timestamp,
            last_heartbeat: p.last_heartbeat_time,
            address: normalizeRemoteAddress(p.socket ? p.socket.remoteAddress : p.address),
            focus_state: p.focus_state || null,
            last_focus_time: p.last_focus_time || null,
            last_adb_resume: p.last_adb_resume || null,
            user_position_z: p.user_transform && p.user_transform.position ? p.user_transform.position.z : null
        });
    });

    const response = {
        message_type: "who_response",
        players_count: players.size,
        players: playerList
    };

    sendJson(socket, response);
}


/**
 * 處理 Identify
 * 分配 Sequence ID
 */
function handleIdentify(socket, message, clientInfo) {
    // Payload: { message_type: 'identify', device_id: '...' }
    const deviceId = message.device_id;
    if (!deviceId) return;

    clientInfo.device_id = deviceId;

    let player = players.get(deviceId);
    if (!player) {
        player = createPlayer(deviceId, socket);
    } else {
        // 已經存在，可能重連，socket 更新
        player.socket = socket;
    }

    log(`🆔 Identify: ${deviceId} -> Seq: ${player.sequence}`);

    // Send AssignSequencePayload
    // Unity MsgType: "assign_sequence"
    const response = {
        message_type: "assign_sequence",
        sequence: player.sequence,
        device_id: deviceId
    };

    sendJson(socket, response);
}

/**
 * 處理 ReadyToMove
 */
function handleReadyToMove(socket, message, clientInfo) {
    // Payload: { message_type: 'ready_to_move', ready_to_move: { device_id: '...', chapter: 1/-1 } }
    const rtm = message.ready_to_move;
    if (rtm && rtm.device_id) {
        // Optional: track readiness in player state
        // log(`Ready State ${rtm.device_id}: ${rtm.chapter}`);
    }
}

/**
 * 處理 Unity focus / pause 狀態。
 * Unity 發現 Quest 誤觸系統層時，server 直接用 ADB 嘗試把遊戲帶回前景。
 */
function handleFocusState(socket, message, clientInfo) {
    const focus = message.focus_state || message.data || {};
    const deviceId = focus.device_id || message.device_id || clientInfo.device_id;

    if (!deviceId) {
        log(`⚠️ focus_state 缺少 device_id (${clientInfo.address})`);
        return;
    }

    clientInfo.device_id = deviceId;

    let player = players.get(deviceId);
    if (!player) {
        player = createPlayer(deviceId, socket);
    }

    player.socket = socket;
    player.address = normalizeRemoteAddress(socket.remoteAddress);
    player.focus_state = focus;
    player.last_focus_time = Date.now();
    if (focus.chapter !== undefined && focus.chapter !== null) {
        player.chapter = normalizeChapter(focus.chapter, player.chapter);
    }

    const eventName = String(focus.event_name || '').toLowerCase();
    const hasInputFocus = focus.has_input_focus;
    const appPaused = focus.app_paused === true;
    const shouldResume = AUTO_RESUME_ENABLED && (
        appPaused ||
        hasInputFocus === false ||
        eventName.includes('lost') ||
        eventName.includes('pause')
    );

    log(
        `🥽 FocusState ${deviceId}: event=${focus.event_name || 'unknown'} ` +
        `input=${hasInputFocus} paused=${appPaused} reason=${focus.reason || ''}`
    );

    if (shouldResume) {
        triggerAutoResume(deviceId, player, focus);
    }
}

/**
 * 處理 Client 回傳的使用者 transform，同步到房間管理 UI。
 */
function handleUserTransformSync(socket, message, clientInfo) {
    const payload = message.user_transform_sync || message.data || {};
    const deviceId = payload.device_id || message.device_id || clientInfo.device_id;

    if (!deviceId) {
        log(`⚠️ user_transform_sync 缺少 device_id (${clientInfo.address})`);
        return;
    }

    clientInfo.device_id = deviceId;

    let player = players.get(deviceId);
    if (!player) {
        player = createPlayer(deviceId, socket);
    }

    player.socket = socket;
    player.address = normalizeRemoteAddress(socket.remoteAddress);

    const chapter = normalizeChapter(payload.chapter, player.chapter);
    player.chapter = chapter;
    player.user_transform = {
        position: normalizeVector3(payload.position),
        rotation: normalizeVector3(payload.rotation),
        scale: normalizeVector3(payload.scale),
        reason: String(payload.reason || ''),
        timestamp: normalizeNumber(payload.timestamp, Date.now()),
        sequence: normalizeInteger(payload.sequence, player.sequence),
        chapter,
        updated_at: Date.now()
    };

    const positionZ = player.user_transform.position ? player.user_transform.position.z : null;
    const zText = positionZ === null ? 'n/a' : positionZ.toFixed(3);
    log(`📍 UserTransform ${deviceId}: z=${zText} reason=${player.user_transform.reason || 'sync'}`);
    maybeApplySavedUserPositionTarget(player, 'user_transform_sync');
}

/**
 * 處理 Admin Broadcast
 * 這是 Python UI 用來發送 MoveCommand 或其他指令給所有 Unity Client 的接口
 */
function handleAdminBroadcast(socket, message, clientInfo) {
    // Payload: { type: 'admin_broadcast', data: { message_type: 'move_command', ... } }

    const broadcastPayload = message.data;
    if (!broadcastPayload) return;

    log(`📢 Admin Broadcast from ${clientInfo.device_id || clientInfo.address}`);

    // Broadcast to ALL connected sockets
    broadcast(broadcastPayload);

    sendJson(socket, {
        type: 'command_response',
        success: true,
        message: 'Broadcast sent'
    });
}

/**
 * 處理 Admin Unicast
 * 發送指令給特定設備
 */
function handleAdminUnicast(socket, message, clientInfo) {
    // Payload: { type: 'admin_unicast', target_device_id: '...', data: { ... } }
    // Note: Python SocketClient wraps everything in 'data', so we might receive:
    // { type: 'admin_unicast', data: { target_device_id: '...', data: { ... } } }

    let targetId = message.target_device_id;
    let unicastPayload = message.data;

    // Check if data is wrapped inside message.data (as sent by Python SocketClient)
    if (!targetId && message.data && message.data.target_device_id) {
        targetId = message.data.target_device_id;
        unicastPayload = message.data.data;
    }

    if (!targetId || !unicastPayload) {
        sendJson(socket, {
            type: 'command_response',
            success: false,
            message: 'Missing target_device_id or data'
        });
        return;
    }

    log(`🎯 Admin Unicast to ${targetId} from ${clientInfo.device_id || clientInfo.address}`);

    const targetPlayer = players.get(targetId);
    if (targetPlayer && targetPlayer.socket) {
        sendJson(targetPlayer.socket, unicastPayload);
        sendJson(socket, {
            type: 'command_response',
            success: true,
            message: `Unicast sent to ${targetId}`
        });
    } else {
        sendJson(socket, {
            type: 'command_response',
            success: false,
            message: `Target device ${targetId} not found or not connected`
        });
    }
}

/**
 * 更新房間記憶的使用者位置 z 值，必要時立即套用到目前連線中的設備。
 */
function handleSetUserPositionTarget(socket, message, clientInfo) {
    const payload = message.data || {};
    const nextZ = normalizeNumber(payload.z, null);

    if (nextZ === null) {
        sendJson(socket, {
            type: 'command_response',
            success: false,
            message: 'Missing or invalid z value'
        });
        return;
    }

    desiredUserPositionZ = nextZ;

    let appliedCount = 0;
    if (payload.apply_now !== false) {
        appliedCount = applySavedUserPositionTargetToEligiblePlayers('admin_set_target');
    }

    log(`💾 User position target updated: z=${nextZ.toFixed(3)} apply_now=${payload.apply_now !== false} applied=${appliedCount}`);

    sendJson(socket, {
        type: 'command_response',
        success: true,
        message: `User position target updated to ${nextZ.toFixed(3)}`,
        applied_count: appliedCount,
        z: nextZ
    });
}

/**
 * 處理 Reset Sequences
 */
function handleResetSequences(socket, message, clientInfo) {
    log(`🔄 Resetting Sequences (Requested by ${clientInfo.device_id || clientInfo.address})`);

    sequenceCounter = 0;
    players.clear();

    sendJson(socket, {
        type: 'command_response',
        success: true,
        message: 'Sequences reset and player list cleared.'
    });
}

/**
 * 處理 Login (Legacy / Admin)
 */
function handleLogin(socket, message, clientInfo) {
    const deviceId = message.device_id;
    if (deviceId) {
        clientInfo.device_id = deviceId;
        clientInfo.is_server = (deviceId === 'Server');

        sendJson(socket, {
            type: 'login_response',
            success: true,
            message: `Logged in as ${deviceId}`
        });
    }
}



// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

function createPlayer(deviceId, socket) {
    sequenceCounter++;
    const player = {
        device_id: deviceId,
        sequence: sequenceCounter,
        chapter: -1,
        last_heartbeat_time: Date.now(),
        socket: socket,
        address: normalizeRemoteAddress(socket.remoteAddress),
        user_transform: null
    };
    players.set(deviceId, player);
    return player;
}

function normalizeNumber(value, fallback = null) {
    if (typeof value === 'number' && Number.isFinite(value)) {
        return value;
    }

    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
        return parsed;
    }

    return fallback;
}

function normalizeInteger(value, fallback = null) {
    const parsed = normalizeNumber(value, null);
    if (parsed === null) {
        return fallback;
    }

    return Math.trunc(parsed);
}

desiredUserPositionZ = normalizeNumber(process.env.QQQUEST_USER_POSITION_Z, null);

function normalizeChapter(value, fallback = -1) {
    return normalizeInteger(value, fallback);
}

function normalizeVector3(value) {
    if (!value || typeof value !== 'object') {
        return null;
    }

    const x = normalizeNumber(value.x, null);
    const y = normalizeNumber(value.y, null);
    const z = normalizeNumber(value.z, null);

    if (x === null && y === null && z === null) {
        return null;
    }

    return {
        x: x === null ? 0 : x,
        y: y === null ? 0 : y,
        z: z === null ? 0 : z
    };
}

function buildUserPositionAdjustPayload(player, zValue, reason) {
    return {
        message_type: 'user_position_adjust',
        user_position_adjust: {
            device_id: player.device_id,
            z: zValue,
            reason: reason || '',
            timestamp: Date.now()
        }
    };
}

function maybeApplySavedUserPositionTarget(player, reason = 'saved_target') {
    if (!player || !player.socket || !player.socket.writable) {
        return false;
    }

    if (desiredUserPositionZ === null) {
        return false;
    }

    const currentChapter = normalizeChapter(player.chapter, -1);
    const canAutoApply = currentChapter === 0 || currentChapter === USER_POSITION_SYNC_CHAPTER;
    if (!canAutoApply) {
        return false;
    }

    const currentZ = player.user_transform && player.user_transform.position
        ? normalizeNumber(player.user_transform.position.z, null)
        : null;

    if (currentZ !== null && Math.abs(currentZ - desiredUserPositionZ) < 0.0005) {
        player.last_user_position_command_z = desiredUserPositionZ;
        return false;
    }

    const lastCommandZ = normalizeNumber(player.last_user_position_command_z, null);
    const lastCommandAt = player.last_user_position_command_at || 0;
    if (
        lastCommandZ !== null &&
        Math.abs(lastCommandZ - desiredUserPositionZ) < 0.0005 &&
        Date.now() - lastCommandAt < USER_POSITION_COMMAND_COOLDOWN_MS
    ) {
        return false;
    }

    sendJson(player.socket, buildUserPositionAdjustPayload(player, desiredUserPositionZ, reason));
    player.last_user_position_command_z = desiredUserPositionZ;
    player.last_user_position_command_at = Date.now();
    log(`📐 Apply saved user position ${player.device_id}: z=${desiredUserPositionZ.toFixed(3)} chapter=${currentChapter} reason=${reason}`);
    return true;
}

function applySavedUserPositionTargetToEligiblePlayers(reason = 'saved_target') {
    let appliedCount = 0;
    players.forEach((player) => {
        if (maybeApplySavedUserPositionTarget(player, reason)) {
            appliedCount += 1;
        }
    });
    return appliedCount;
}

function normalizeRemoteAddress(remoteAddress) {
    if (!remoteAddress) return '';

    if (remoteAddress.startsWith('::ffff:')) {
        return remoteAddress.substring('::ffff:'.length);
    }

    if (remoteAddress === '::1') {
        return '127.0.0.1';
    }

    return remoteAddress;
}

function getAdbTargetForPlayer(player) {
    const ip = normalizeRemoteAddress(player && player.socket ? player.socket.remoteAddress : player.address);
    if (!ip) return '';

    if (ip.includes(':') && !ip.includes('.')) {
        return ip;
    }

    return `${ip}:${AUTO_RESUME_ADB_PORT}`;
}

function triggerAutoResume(deviceId, player, focus) {
    const now = Date.now();
    const state = autoResumeState.get(deviceId) || { last_trigger_at: 0, in_flight: false };

    if (state.in_flight) {
        log(`⏳ Auto resume 已在執行中，略過重複觸發: ${deviceId}`);
        return;
    }

    if (now - state.last_trigger_at < AUTO_RESUME_COOLDOWN_MS) {
        log(`⏱️ Auto resume cooldown 中，略過: ${deviceId}`);
        return;
    }

    state.last_trigger_at = now;
    state.in_flight = true;
    autoResumeState.set(deviceId, state);

    runAutoResumeSequence(deviceId, player, focus)
        .catch((err) => {
            log(`❌ Auto resume 例外 ${deviceId}: ${err.message}`);
        })
        .finally(() => {
            state.in_flight = false;
            autoResumeState.set(deviceId, state);
        });
}

async function runAutoResumeSequence(deviceId, player, focus) {
    const target = getAdbTargetForPlayer(player);
    if (!target) {
        log(`⚠️ Auto resume 找不到 ADB target: ${deviceId}`);
        return;
    }

    log(`🎮 Auto resume ${deviceId} via ${target} (${focus.event_name || 'focus_state'})`);

    const connectResult = await runAdb(['connect', target], 'adb connect');
    if (!connectResult.success && !connectResult.output.includes('already connected')) {
        log(`⚠️ ADB connect 可能失敗 ${deviceId}: ${connectResult.output}`);
    }

    await runAdbShell(target, ['input', 'keyevent', 'KEYCODE_ESCAPE'], 'escape');
    await sleep(150);
    await runAdbShell(target, ['input', 'keyevent', '4'], 'back 1');
    await sleep(150);
    await runAdbShell(target, ['input', 'keyevent', '4'], 'back 2');
    await sleep(150);

    const component = `${AUTO_RESUME_PACKAGE}/${AUTO_RESUME_ACTIVITY}`;
    await runAdbShell(target, [
        'am', 'start',
        '--activity-reorder-to-front',
        '--activity-single-top',
        '--activity-no-animation',
        '-a', 'android.intent.action.MAIN',
        '-c', 'android.intent.category.LAUNCHER',
        '-c', 'com.oculus.intent.category.VR',
        '-n', component
    ], 'explicit vr activity');
    await sleep(250);

    await runAdbShell(target, [
        'monkey',
        '-p', AUTO_RESUME_PACKAGE,
        '-c', 'android.intent.category.LAUNCHER',
        '1'
    ], 'monkey');
    await sleep(250);

    const finalStart = await runAdbShell(target, [
        'am', 'start',
        '--activity-reorder-to-front',
        '--activity-single-top',
        '--activity-no-animation',
        '-a', 'android.intent.action.MAIN',
        '-c', 'android.intent.category.LAUNCHER',
        '-c', 'com.oculus.intent.category.VR',
        '-n', component
    ], 'final explicit vr activity');

    const focusCheck = await runAdbShell(target, [
        'dumpsys', 'window', 'windows'
    ], 'focus check', 8000, false);

    const focusOk = focusCheck.output.includes(AUTO_RESUME_PACKAGE);
    player.last_adb_resume = {
        at: Date.now(),
        target,
        success: finalStart.success,
        focus_ok: focusOk,
        event_name: focus.event_name || ''
    };

    log(`✅ Auto resume 已送出 ${deviceId}: command=${finalStart.success} focus_has_app=${focusOk}`);
}

function runAdb(args, label, timeoutMs = AUTO_RESUME_COMMAND_TIMEOUT_MS, shouldLog = true) {
    return new Promise((resolve) => {
        execFile(ADB_BIN, args, { timeout: timeoutMs }, (err, stdout, stderr) => {
            const output = [stdout, stderr, err ? err.message : '']
                .filter(Boolean)
                .join('\n')
                .trim();
            const success = !err;

            if (shouldLog) {
                if (success) {
                    log(`ADB ${label}: ${output || 'OK'}`);
                } else {
                    log(`⚠️ ADB ${label} failed: ${output}`);
                }
            }

            resolve({ success, output });
        });
    });
}

function runAdbShell(target, shellArgs, label, timeoutMs = AUTO_RESUME_COMMAND_TIMEOUT_MS, shouldLog = true) {
    return runAdb(['-s', target, 'shell', ...shellArgs], label, timeoutMs, shouldLog);
}

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function sendJson(socket, data) {
    if (socket && socket.writable) {
        socket.write(JSON.stringify(data) + '\n');
    }
}

function broadcast(data, excludeSocket = null) {
    let count = 0;
    const jsonStr = JSON.stringify(data) + '\n';

    for (const socket of clients.keys()) {
        if (socket !== excludeSocket && socket.writable) {
            try {
                socket.write(jsonStr);
                count++;
            } catch (e) {
                log(`Failed to broadcast to socket: ${e.message}`);
            }
        }
    }
    log(`📢 Broadcasted to ${count} clients: ${JSON.stringify(data)}`);
}

// --------------------------------------------------------------------------
// Server Startup
// --------------------------------------------------------------------------

server.on('error', (err) => {
    log(`❌ 服務器錯誤: ${err.message}`);
    if (err.code === 'EADDRINUSE') {
        process.exit(1);
    }
});

server.listen(socketPort, socketIp, () => {
    log(`🚀 Socket Server 已啟動`);
    log(`📡 監聽地址: ${socketIp}:${socketPort}`);
    log(`🏠 房間: ${roomName} (ID: ${roomId})`);
    if (desiredUserPositionZ !== null) {
        log(`📐 Saved user position target: z=${desiredUserPositionZ.toFixed(3)}`);
    }

    // Stdout for Python manager
    process.stdout.write(JSON.stringify({
        status: 'started',
        room_id: roomId,
        room_name: roomName,
        ip: socketIp,
        port: socketPort
    }) + '\n');
});

process.on('SIGTERM', () => {
    log('🛑 SIGTERM received, shutting down...');
    server.close(() => process.exit(0));
});

process.on('SIGINT', () => {
    log('🛑 SIGINT received, shutting down...');
    server.close(() => process.exit(0));
});
