using UnityEngine;
using System;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Collections.Generic;
using System.Globalization;
using GM;
using UnityEngine.Events;

namespace MultiPlayer
{
    public class CoPlayerSocketMgr : MonoBehaviour
    {
        public static CoPlayerSocketMgr Instance { get; private set; }

        [Header("TCP Parameters")]
        public string serverIP = "127.0.0.1";
        public int serverPort = 5000;

        [Tooltip("可选：连接成功后立即发送一条 hello/identify（仍然是 JSON+\\n）。若你的服务器不需要，可关掉。")]
        public bool sendIdentifyOnConnect = false;

        [Tooltip("除錯用：把整包 JSON 夾進 heartbeat.message 一起送出（會讓每則心跳大小翻倍）。預設關閉以縮小封包。")]
        public bool embedDebugJsonInMessage = false;

        private string deviceShortID = "";

        [Header("Connection Behavior")]
        [Tooltip("断线后多久重连（秒）")]
        public float reconnectInterval = 5f;

        [Tooltip("心跳发送间隔（秒）")]
        public float heartbeatInterval = 0.1f;

        [Tooltip("心跳超时（秒）。0 或负数表示不启用超时断线。")]
        public float heartbeatTimeout = 0f;

        [Header("GM Scripts")]
        public AweTest.MRUKMapper SpaceCalibrationMapper = null;
        public GM.RealWorldPlayerLocateMgr realWorldPlayerLocateMgr = null;

        [Header("Player Position Sync. Part")]
        public GameObject HMDObj;
        public Interaction.QuestDetectHand RHandDector;
        public Interaction.QuestDetectHand LHandDector;

        [Space]
        public GameObject PlayerVisualPrefab;

        [Header("User Position Sync")]
        public Transform UserPositionTransform;

        [Header("Sound Trigger")]
        [Tooltip("收到後台 play_sound 指令時播放一次音效。需在 Inspector 指定場景中的 SoundTrigger。")]
        public SoundTrigger soundTrigger;

        [Tooltip("收到後台 set_language 指令時切換語言。把場景中的 LanguageObjectActiveSwitcher 拉進來即可" +
                 "（0 = 第一個 group / 中文、1 = 第二個 group / 英文）。")]
        public LanguageObjectActiveSwitcher languageSwitcher;

        // TCP
        private TcpClient _client;
        private NetworkStream _stream;
        private Thread _receiveThread;

        private volatile bool _isConnected = false;
        public bool IsConnected => _isConnected;

        // Message queue (thread -> main)
        private readonly Queue<string> receivedMessages = new Queue<string>();
        private readonly Queue<Action> pendingActions = new Queue<Action>();
        private readonly object messageQueueLock = new object();

        // Sequence
        private static int mySequence = 0;
        public static int MySequence => mySequence;
        private const int GameStartChapter = 2;
        private const int UserPositionSyncChapterInitial = 0;
        private const int UserPositionSyncChapter = 5;
        private int _lastObservedUserPositionChapter = int.MinValue;

        // Heartbeat timing
        private float _lastHeartbeatSendTimeSec = -999f;
        private float _lastHeartbeatRecvTimeSec = -999f;

        // Events
        public event Action<string> OnMessageReceived;
        public event Action<bool> OnConnectionStatusChanged;

        [Header("Server Event Handler")]
        public UnityEvent GameStartUEvent = new UnityEvent();
        public UnityEvent<int> MoveChapterUEvent = new UnityEvent<int>();
        // 語言切換：0 = 中文、1 = 英文。請在 Inspector 把這個事件接到 LanguageSwitch 的
        // Current Group Index（把 LanguageSwitch 上設定 group index 的 public 方法/屬性拉進來）。
        public UnityEvent<int> SetLanguageUEvent = new UnityEvent<int>();

        #region To Server Objects
        private HeartbeatPayload heartbeatPayload;
        private ReadyToMovePayload readyToMovePayload;
        #endregion

        #region From Server Objects
        private PositionInfo positionInfo = new PositionInfo();
        private AssignSequencePayload assignSequencePayload = new AssignSequencePayload();
        private MoveCommandPayload moveCommandPayload = new MoveCommandPayload();
        #endregion

        // 接收缓冲：TCP 是 stream，需要拼包/拆包
        private readonly StringBuilder _recvSb = new StringBuilder(8192);

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);
        }

        void Start()
        {
            InitialData();
            StartClient();
        }

        void InitialData()
        {
            deviceShortID = GM.Utils.ShortDeviceID();
            heartbeatPayload = new HeartbeatPayload(deviceShortID);
            // Default to 0 (Standby) because RealWorldPlayerLocateMgr now auto-inits to 0.
            heartbeatPayload.heartbeat.SetChapter(0);
            _lastObservedUserPositionChapter = int.MinValue;
            readyToMovePayload = new ReadyToMovePayload(deviceShortID);
        }

        void FixedUpdate()
        {
            // 1) 主线程处理来自接收线程的消息
            DrainReceivedMessagesOnMainThread();

            // 2) 心跳发送
            if (_isConnected)
            {
                float now = Time.realtimeSinceStartup;

                if (now - _lastHeartbeatSendTimeSec >= heartbeatInterval)
                {
                    PassHeartbeat();
                    _lastHeartbeatSendTimeSec = now;
                }

                // 3) 心跳超时（可选）
                if (heartbeatTimeout > 0f && _lastHeartbeatRecvTimeSec > 0f)
                {
                    if (now - _lastHeartbeatRecvTimeSec >= heartbeatTimeout)
                    {
                        Debug.LogWarning("<color=white>[TCP CoPlayer]</color> Heartbeat Timeout -> reconnect.");
                        HandleConnectionFailure();
                    }
                }
            }
        }

        private void DrainReceivedMessagesOnMainThread()
        {
            lock (messageQueueLock)
            {
                while (pendingActions.Count > 0)
                {
                    pendingActions.Dequeue()?.Invoke();
                }

                while (receivedMessages.Count > 0)
                {
                    string message = receivedMessages.Dequeue();
                    if (string.IsNullOrWhiteSpace(message)) continue;

                    Debug.Log("<color=white>[TCP CoPlayer]</color> Recv.: " + message);

                    try
                    {
                        if (message.IndexOf("\"message_type\":\"user_position_adjust\"", StringComparison.OrdinalIgnoreCase) >= 0)
                        {
                            HandleUserPositionAdjust(message);
                            OnMessageReceived?.Invoke(message);
                            _lastHeartbeatRecvTimeSec = Time.realtimeSinceStartup;
                            continue;
                        }

                        SocketPayloadBasic socketPayloadBasic = new SocketPayloadBasic();
                        socketPayloadBasic.LoadFromJson(message);

                        if (socketPayloadBasic.IsValidType)
                        {
                            RecvMsgHandler(socketPayloadBasic.message_type, message);
                        }
                        else
                        {
                            SocketPayloadEventBasic socketPayloadEventBasic = new SocketPayloadEventBasic();
                            socketPayloadEventBasic.LoadFromJson(message);
                            RecvMsgHandler(socketPayloadEventBasic.event_type, message);
                        }

                        OnMessageReceived?.Invoke(message);
                        _lastHeartbeatRecvTimeSec = Time.realtimeSinceStartup;
                    }
                    catch (Exception ex)
                    {
                        Debug.LogError($"<color=red>[TCP CoPlayer]</color> Message Handle Error: {ex.Message}\nRaw: {message}");
                    }
                }
            }
        }

        void OnApplicationQuit() => Disconnect();
        void OnDestroy() => Disconnect();

        #region Public API
        public void StartClient()
        {
            if (_isConnected)
            {
                Debug.LogWarning("<color=white>[TCP CoPlayer]</color> Already Connected.");
                return;
            }

            CancelInvoke(nameof(Reconnect));
            Connect();
        }

        public void Disconnect()
        {
            CancelInvoke(nameof(Reconnect));
            InternalDisconnect("Client Disconnect()");
        }

        public void SetReadyToMove(bool isReady)
        {
            PassReadyToMove(isReady);
        }

        public void SendFocusState(string eventName, bool hasInputFocus, bool appPaused, string reason = "")
        {
            if (string.IsNullOrEmpty(deviceShortID))
            {
                deviceShortID = GM.Utils.ShortDeviceID();
            }

            int chapter = -1;
            if (heartbeatPayload != null)
            {
                chapter = heartbeatPayload.heartbeat.chapter;
            }

            string json =
                "{\"message_type\":\"focus_state\",\"focus_state\":{" +
                $"\"device_id\":\"{EscapeJson(deviceShortID)}\"," +
                $"\"event_name\":\"{EscapeJson(eventName)}\"," +
                $"\"has_input_focus\":{BoolJson(hasInputFocus)}," +
                $"\"app_paused\":{BoolJson(appPaused)}," +
                $"\"reason\":\"{EscapeJson(reason)}\"," +
                $"\"chapter\":{chapter}," +
                $"\"sequence\":{mySequence}," +
                $"\"timestamp\":{GetUnixTimeMilliseconds()}," +
                $"\"realtime_since_startup\":{Time.realtimeSinceStartup.ToString("F3", CultureInfo.InvariantCulture)}" +
                "}}";

            SendData(json);
        }
        #endregion

        #region Connection / TCP
        private void Connect()
        {
            try
            {
                Debug.Log($"<color=white>[TCP CoPlayer]</color> Connect to {serverIP}:{serverPort} (Async)...");

                _client = new TcpClient();
                // Begin Async Connect
                _client.BeginConnect(serverIP, serverPort, new AsyncCallback(OnConnectCallback), _client);
            }
            catch (Exception ex)
            {
                Debug.LogError($"<color=red>[TCP CoPlayer]</color> Connect Error: {ex.Message}");
                HandleConnectionFailure();
            }
        }

        private void OnConnectCallback(IAsyncResult ar)
        {
            try
            {
                TcpClient tClient = (TcpClient)ar.AsyncState;
                if (tClient != null)
                {
                    tClient.EndConnect(ar);

                    // Connection Successful
                    // Dispatch to Main Thread
                    lock (messageQueueLock)
                    {
                        pendingActions.Enqueue(() =>
                        {
                            if (tClient.Connected)
                            {
                                _client = tClient;
                                _client.NoDelay = true;
                                _stream = _client.GetStream();

                                _isConnected = true;
                                OnConnectionStatusChanged?.Invoke(true);

                                _lastHeartbeatSendTimeSec = Time.realtimeSinceStartup;
                                _lastHeartbeatRecvTimeSec = Time.realtimeSinceStartup;

                                Debug.Log("<color=white>[TCP CoPlayer]</color> Connect Successfully.");

                                if (sendIdentifyOnConnect)
                                {
                                    SendData($"{{\"message_type\":\"identify\",\"device_id\":\"{deviceShortID}\"}}");
                                }

                                StartReceiveThread();
                            }
                            else
                            {
                                HandleConnectionFailure();
                            }
                        });
                    }
                }
            }
            catch (Exception ex)
            {
                // Ensure HandleConnectionFailure runs on main thread
                lock (messageQueueLock)
                {
                    pendingActions.Enqueue(() =>
                    {
                        Debug.LogWarning($"<color=white>[TCP CoPlayer]</color> Async Connect Failed: {ex.Message}");
                        HandleConnectionFailure();
                    });
                }
            }
        }

        private void StartReceiveThread()
        {
            if (_receiveThread != null && _receiveThread.IsAlive) return;

            _receiveThread = new Thread(ReceiveLoop);
            _receiveThread.IsBackground = true;
            _receiveThread.Start();
        }

        private void ReceiveLoop()
        {
            byte[] buffer = new byte[8192];

            try
            {
                while (_isConnected)
                {
                    if (_stream == null || !_stream.CanRead) break;

                    int bytesRead = _stream.Read(buffer, 0, buffer.Length);
                    if (bytesRead <= 0)
                    {
                        Debug.LogWarning("<color=white>[TCP CoPlayer]</color> Server closed connection.");
                        break;
                    }

                    string chunk = Encoding.UTF8.GetString(buffer, 0, bytesRead);

                    // NDJSON：累计到 StringBuilder，按 '\n' 切出一条条 JSON
                    AppendAndExtractLines(chunk);
                }
            }
            catch (Exception ex)
            {
                // 注意：不要在这里频繁调用 Unity API；但 Debug.LogError 通常还能工作
                Debug.LogError($"<color=red>[TCP CoPlayer]</color> ReceiveLoop Error: {ex.Message}");
            }

            // Loop 退出，视为断线
            HandleConnectionFailure();
        }

        private void AppendAndExtractLines(string chunk)
        {
            lock (_recvSb)
            {
                _recvSb.Append(chunk);

                while (true)
                {
                    // 找换行
                    int newlineIndex = IndexOfNewline(_recvSb);
                    if (newlineIndex < 0) break;

                    // 取一行（不含 '\n'）
                    string line = _recvSb.ToString(0, newlineIndex).Trim();

                    // 删除这行 + '\n'
                    _recvSb.Remove(0, newlineIndex + 1);

                    if (string.IsNullOrEmpty(line)) continue;

                    lock (messageQueueLock)
                    {
                        receivedMessages.Enqueue(line);
                    }
                }
            }
        }

        // 在 StringBuilder 里找 '\n'
        private int IndexOfNewline(StringBuilder sb)
        {
            for (int i = 0; i < sb.Length; i++)
            {
                if (sb[i] == '\n') return i;
            }
            return -1;
        }

        public void SendData(string messageJson)
        {
            if (!_isConnected || _stream == null || !_stream.CanWrite)
            {
                Debug.LogWarning("<color=white>[TCP CoPlayer]</color> No Connection.");
                return;
            }

            try
            {
                // NDJSON framing
                string framed = messageJson + "\n";
                byte[] bytes = Encoding.UTF8.GetBytes(framed);
                _stream.Write(bytes, 0, bytes.Length);
                // 可按需开 log
                // Debug.Log("<color=white>[TCP CoPlayer]</color> Send: " + messageJson);
            }
            catch (Exception ex)
            {
                Debug.LogError($"<color=red>[TCP CoPlayer]</color> Send Error: {ex.Message}");
                HandleConnectionFailure();
            }
        }

        private void HandleConnectionFailure()
        {
            // 避免多次重入导致重复 Invoke
            bool wasConnected = _isConnected;

            InternalDisconnect("HandleConnectionFailure()");

            if (wasConnected)
            {
                Invoke(nameof(Reconnect), reconnectInterval);
            }
        }

        private void InternalDisconnect(string reason)
        {
            if (_isConnected)
            {
                Debug.LogWarning($"<color=white>[TCP CoPlayer]</color> Disconnect: {reason}");
            }

            _isConnected = false;
            OnConnectionStatusChanged?.Invoke(false);

            // 关闭 stream/client，让 ReceiveLoop 自然退出
            try { _stream?.Close(); } catch { }
            try { _client?.Close(); } catch { }

            _stream = null;
            _client = null;

            // 不用 Thread.Abort：让线程自然结束
            _receiveThread = null;

            // 清理接收 buffer（可选）
            lock (_recvSb)
            {
                _recvSb.Clear();
            }
        }

        private void Reconnect()
        {
            if (_isConnected) return;

            Debug.Log("<color=white>[TCP CoPlayer]</color> Try to Reconnect...");
            CancelInvoke(nameof(Reconnect));
            StartClient();
        }
        #endregion

        #region Message Handling (Same as WebSocket version)
        private void RecvMsgHandler(string msg_type, string msg)
        {
            if (string.Equals(msg_type, "user_position_adjust", StringComparison.OrdinalIgnoreCase))
            {
                HandleUserPositionAdjust(msg);
                return;
            }

            if (string.Equals(msg_type, "play_sound", StringComparison.OrdinalIgnoreCase))
            {
                HandlePlaySound(msg);
                return;
            }

            if (string.Equals(msg_type, "set_language", StringComparison.OrdinalIgnoreCase))
            {
                HandleSetLanguage(msg);
                return;
            }

            SocketMsgType.FromServer fromServerType = SocketMsgType.GetFromServerMessageType(msg_type);

            switch (fromServerType)
            {
                case SocketMsgType.FromServer.Update:
                    positionInfo.LoadFromJson(msg);
                    positionInfo.PrintDebug();
                    Debug.Log($"<color=white>[TCP CoPlayer]</color> {msg_type} > Player Count {positionInfo.player_count}");
                    
                    // 構建完整的顯示資訊
                    string roomName = "Unknown";
                    if (realWorldPlayerLocateMgr != null && realWorldPlayerLocateMgr.roomVisualRoot != null)
                    {
                        roomName = realWorldPlayerLocateMgr.roomVisualRoot.name;
                    }
                    
                    string timelineName = "";
                    if (realWorldPlayerLocateMgr != null && realWorldPlayerLocateMgr.realLocationPresets != null && 
                        realWorldPlayerLocateMgr.nowPreset >= 0 && realWorldPlayerLocateMgr.nowPreset < realWorldPlayerLocateMgr.realLocationPresets.Count)
                    {
                        timelineName = $"[{realWorldPlayerLocateMgr.realLocationPresets[realWorldPlayerLocateMgr.nowPreset].name}]";
                    }
                    
                    DebugModeConsole.Print($"Room - {roomName}\nID - {heartbeatPayload.heartbeat.device_id}\nPlayers - {positionInfo.player_count}\n{timelineName}", false);
                    break;

                case SocketMsgType.FromServer.MoveCommand:
                    moveCommandPayload.LoadFromJson(msg);
                    moveCommandPayload.PrintDebug();
                    OnChapterChange(moveCommandPayload.move_command.chapter);
                    break;

                case SocketMsgType.FromServer.AssignSequence:
                    assignSequencePayload.LoadFromJson(msg);
                    assignSequencePayload.PrintDebug();
                    OnSequenceChange(assignSequencePayload.sequence);
                    break;

                default:
                    Debug.Log($"<color=white>[TCP CoPlayer]</color> Type {msg_type} Not Yet Implement.");
                    break;
            }
        }

        // 收到後台 play_sound 指令：觸發一次音效。
        // sound_index 指定要播放清單裡的哪一個（發送提示1 = 0、發送提示2 = 1）；沒帶就預設 0。
        // 在主執行緒 (DrainReceivedMessagesOnMainThread) 上呼叫，可安全播放音效。
        private void HandlePlaySound(string msg)
        {
            // 診斷用：把收到的原始 JSON 印出來，確認 sound_index 有沒有送到。
            Debug.Log($"<color=cyan>[TCP CoPlayer]</color> play_sound RAW: {msg}");

            int soundIndex = 0;
            try
            {
                PlaySoundEnvelope env = JsonUtility.FromJson<PlaySoundEnvelope>(msg);
                if (env != null)
                    soundIndex = env.sound_index;
            }
            catch (Exception e)
            {
                Debug.LogWarning($"<color=yellow>[TCP CoPlayer]</color> play_sound 解析失敗，改用索引 0：{e.Message}");
            }

            if (soundTrigger != null)
            {
                soundTrigger.PlayOnce(soundIndex);
                Debug.Log($"<color=cyan>[TCP CoPlayer]</color> play_sound -> SoundTrigger.PlayOnce({soundIndex})");
            }
            else
            {
                Debug.LogWarning("<color=yellow>[TCP CoPlayer]</color> 收到 play_sound 但未指定 soundTrigger。");
            }
        }

        // 收到後台 set_language 指令：切換語言（group_index：0 = 中文、1 = 英文）。
        // 透過 SetLanguageUEvent 通知；請在 Inspector 把它接到 LanguageSwitch 的 Current Group Index。
        private void HandleSetLanguage(string msg)
        {
            int groupIndex = 0;
            try
            {
                SetLanguageEnvelope env = JsonUtility.FromJson<SetLanguageEnvelope>(msg);
                if (env != null)
                    groupIndex = env.group_index;
            }
            catch (Exception e)
            {
                Debug.LogWarning($"<color=yellow>[TCP CoPlayer]</color> set_language 解析失敗，改用 0(中文)：{e.Message}");
            }

            groupIndex = groupIndex == 1 ? 1 : 0;   // 夾在 0/1

            // 直接呼叫 LanguageObjectActiveSwitcher.SetGroup()（會設 index 並真正套用語言）——最穩，
            // 不必在 Inspector 接 dynamic int。只要把 languageSwitcher 拉進來即可。
            if (languageSwitcher != null)
            {
                languageSwitcher.SetGroup(groupIndex);
            }
            else
            {
                Debug.LogWarning("<color=yellow>[TCP CoPlayer]</color> 收到 set_language 但未指定 languageSwitcher（改由 SetLanguageUEvent 通知，請確認事件已接好）。");
            }

            // 事件通知（給其他監聽者用；若你偏好用事件接線，也可接到 SetGroup 的 dynamic int）
            SetLanguageUEvent.Invoke(groupIndex);
            Debug.Log($"<color=cyan>[TCP CoPlayer]</color> set_language -> SetGroup({groupIndex}) ({(groupIndex == 0 ? "中文" : "英文")})");
        }

        private void OnChapterChange(int newChapter)
        {
            bool isSameChapter = heartbeatPayload.heartbeat.chapter == newChapter;

            if (!isSameChapter)
            {
                MoveChapterUEvent.Invoke(newChapter);
            }

            if (newChapter == GameStartChapter)
            {
                EventManager.Broadcast(Events.onGameStart);
                GameStartUEvent.Invoke();
            }

            heartbeatPayload.heartbeat.SetChapter(newChapter);
            MaybeSendUserPositionTransform(newChapter);
        }

        private void OnSequenceChange(int newSeq)
        {
            if (mySequence == newSeq)
            {
                Debug.Log("[<color=green>Seats</color>] Seats NOT changed.");
                return;
            }

            mySequence = newSeq;
            PlayerPrefs.SetInt(MPConstant.PLAYER_SEQNUM, newSeq);
            Events.onSequenceChange.newSeq = newSeq;
            EventManager.Broadcast(Events.onSequenceChange);
        }
        #endregion

        #region Passing Data (Same as WebSocket version)
        private void PassHeartbeat()
        {
            if (HMDObj == null || SpaceCalibrationMapper == null)
            {
                Debug.Log("<color=red>[TCP CoPlayer]</color> Please Set HMD Object or SpaceCalibrationMapper.");
                return;
            }

            heartbeatPayload.heartbeat.UpdateData(
                SpaceCalibrationMapper.GetPositionInCoordinate(HMDObj.transform.position),
                SpaceCalibrationMapper.GetPositionInCoordinate(RHandDector.HandWorldPosition),
                RHandDector.IsNowHandTracked,
                SpaceCalibrationMapper.GetPositionInCoordinate(LHandDector.HandWorldPosition),
                LHandDector.IsNowHandTracked
            );

            if (realWorldPlayerLocateMgr != null)
            {
                heartbeatPayload.heartbeat.SetChapter(realWorldPlayerLocateMgr.nowPreset);
                // 附加信息（含後台要用的時間字串），保持精簡即可
                heartbeatPayload.heartbeat.SetMessage(realWorldPlayerLocateMgr.AddtionalMsg);
            }

            MaybeSendUserPositionTransform(heartbeatPayload.heartbeat.chapter);

            // 除錯用：需要時才把整包 JSON 夾進 message（會讓封包翻倍）。預設關閉。
            if (embedDebugJsonInMessage)
            {
                heartbeatPayload.heartbeat.SetMessage("[TCP] Send HB: " + heartbeatPayload.ToJson());
            }

            // 发给 server
            SendData(heartbeatPayload.ToJson());
        }

        private void PassReadyToMove(bool isReady)
        {
            readyToMovePayload.ready_to_move.SetChapter(isReady ? 1 : -1);
            SendData(readyToMovePayload.ToJson());
        }

        private static string BoolJson(bool value)
        {
            return value ? "true" : "false";
        }

        private void MaybeSendUserPositionTransform(int chapter)
        {
            if (IsUserPositionSyncChapter(chapter) && _lastObservedUserPositionChapter != chapter)
            {
                SendUserPositionTransform(BuildUserPositionSyncReason(chapter));
            }

            _lastObservedUserPositionChapter = chapter;
        }

        private static bool IsUserPositionSyncChapter(int chapter)
        {
            return chapter == UserPositionSyncChapterInitial || chapter == UserPositionSyncChapter;
        }

        private static string BuildUserPositionSyncReason(int chapter)
        {
            if (chapter == UserPositionSyncChapterInitial)
            {
                return "chapter_0_enter";
            }

            if (chapter == UserPositionSyncChapter)
            {
                return "chapter_5_enter";
            }

            return $"chapter_{chapter}_enter";
        }

        private void SendUserPositionTransform(string reason)
        {
            if (!_isConnected)
            {
                return;
            }

            if (UserPositionTransform == null)
            {
                Debug.LogWarning("<color=yellow>[TCP CoPlayer]</color> UserPositionTransform is not assigned.");
                return;
            }

            if (string.IsNullOrEmpty(deviceShortID))
            {
                deviceShortID = GM.Utils.ShortDeviceID();
            }

            int chapter = heartbeatPayload != null ? heartbeatPayload.heartbeat.chapter : -1;
            Vector3 position = UserPositionTransform.position;
            Vector3 rotation = UserPositionTransform.eulerAngles;
            Vector3 scale = UserPositionTransform.localScale;

            string json =
                "{\"message_type\":\"user_transform_sync\",\"user_transform_sync\":{" +
                $"\"device_id\":\"{EscapeJson(deviceShortID)}\"," +
                $"\"chapter\":{chapter}," +
                $"\"sequence\":{mySequence}," +
                $"\"reason\":\"{EscapeJson(reason)}\"," +
                $"\"timestamp\":{GetUnixTimeMilliseconds()}," +
                $"\"position\":{Vector3Json(position)}," +
                $"\"rotation\":{Vector3Json(rotation)}," +
                $"\"scale\":{Vector3Json(scale)}" +
                "}}";

            SendData(json);
        }

        private void HandleUserPositionAdjust(string msg)
        {
            try
            {
                UserPositionAdjustEnvelope payload = JsonUtility.FromJson<UserPositionAdjustEnvelope>(msg);
                if (payload == null || payload.user_position_adjust == null)
                {
                    Debug.LogWarning("<color=yellow>[TCP CoPlayer]</color> Invalid user_position_adjust payload.");
                    return;
                }

                string targetDeviceId = payload.user_position_adjust.device_id;
                if (!string.IsNullOrEmpty(targetDeviceId) &&
                    !string.Equals(targetDeviceId, deviceShortID, StringComparison.OrdinalIgnoreCase))
                {
                    return;
                }

                if (UserPositionTransform == null)
                {
                    Debug.LogWarning("<color=yellow>[TCP CoPlayer]</color> UserPositionTransform is not assigned.");
                    return;
                }

                Vector3 currentPosition = UserPositionTransform.position;
                currentPosition.z = payload.user_position_adjust.z;
                UserPositionTransform.position = currentPosition;

                SendUserPositionTransform("server_adjust_z");
            }
            catch (Exception ex)
            {
                Debug.LogError($"<color=red>[TCP CoPlayer]</color> user_position_adjust parse failed: {ex.Message}");
            }
        }

        private static string FloatJson(float value)
        {
            return value.ToString("0.######", CultureInfo.InvariantCulture);
        }

        private static string Vector3Json(Vector3 value)
        {
            return "{" +
                $"\"x\":{FloatJson(value.x)}," +
                $"\"y\":{FloatJson(value.y)}," +
                $"\"z\":{FloatJson(value.z)}" +
                "}";
        }

        private static long GetUnixTimeMilliseconds()
        {
            return (long)(DateTime.UtcNow - new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc)).TotalMilliseconds;
        }

        private static string EscapeJson(string value)
        {
            if (string.IsNullOrEmpty(value))
            {
                return "";
            }

            return value
                .Replace("\\", "\\\\")
                .Replace("\"", "\\\"")
                .Replace("\n", "\\n")
                .Replace("\r", "\\r");
        }
        #endregion
    }

    [Serializable]
    public class PlaySoundEnvelope
    {
        public string message_type;
        public string device_id;
        public int sound_index;
    }

    [Serializable]
    public class SetLanguageEnvelope
    {
        public string message_type;
        public int group_index;   // 0 = 中文、1 = 英文
    }

    [Serializable]
    public class UserPositionAdjustEnvelope
    {
        public string message_type;
        public UserPositionAdjustPayload user_position_adjust;
    }

    [Serializable]
    public class UserPositionAdjustPayload
    {
        public string device_id;
        public float z;
        public long timestamp;
    }
}
