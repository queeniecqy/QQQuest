using UnityEngine;
using System;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Collections.Generic;
using System.Globalization;
using System.Text.RegularExpressions;
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

        // TCP
        private TcpClient _client;
        private NetworkStream _stream;
        private Thread _receiveThread;

        private volatile bool _isConnected = false;
        public bool IsConnected => _isConnected;

        // Message queue (thread -> main)
        private readonly Queue<string> receivedMessages = new Queue<string>();
        private readonly object messageQueueLock = new object();

        // Sequence
        private static int mySequence = 0;
        public static int MySequence => mySequence;
        private const int GameStartChapter = 2;
        private int currentChapter = -1;

        // Heartbeat timing
        private float _lastHeartbeatSendTimeSec = -999f;
        private float _lastHeartbeatRecvTimeSec = -999f;

        // Events
        public event Action<string> OnMessageReceived;
        public event Action<bool> OnConnectionStatusChanged;

        [Header("Server Event Handler")]
        public UnityEvent GameStartUEvent = new UnityEvent();
        public UnityEvent<int> MoveChapterUEvent = new UnityEvent<int>();

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

            // [FIX] Initialize to -1 so that the first '0' from server triggers the change event.
            heartbeatPayload.heartbeat.SetChapter(-1);
            currentChapter = -1;
            
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
                while (receivedMessages.Count > 0)
                {
                    string message = receivedMessages.Dequeue();
                    if (string.IsNullOrWhiteSpace(message)) continue;

                    Debug.Log("<color=white>[TCP CoPlayer]</color> Recv.: " + message);

                    try
                    {
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

            string json =
                "{\"message_type\":\"focus_state\",\"focus_state\":{" +
                $"\"device_id\":\"{EscapeJson(deviceShortID)}\"," +
                $"\"event_name\":\"{EscapeJson(eventName)}\"," +
                $"\"has_input_focus\":{BoolJson(hasInputFocus)}," +
                $"\"app_paused\":{BoolJson(appPaused)}," +
                $"\"reason\":\"{EscapeJson(reason)}\"," +
                $"\"chapter\":{currentChapter}," +
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
                Debug.Log($"<color=white>[TCP CoPlayer]</color> Connect to {serverIP}:{serverPort}");

                _client = new TcpClient();
                _client.NoDelay = true;
                _client.Connect(serverIP, serverPort);
                _stream = _client.GetStream();

                _isConnected = true;
                OnConnectionStatusChanged?.Invoke(true);

                _lastHeartbeatSendTimeSec = Time.realtimeSinceStartup;
                _lastHeartbeatRecvTimeSec = Time.realtimeSinceStartup;

                Debug.Log("<color=white>[TCP CoPlayer]</color> Connect Successfully.");

                if (sendIdentifyOnConnect)
                {
                    // 可选：如果你想让 server 端更快识别 device id，可在这里发一条自定义消息
                    // 注意：必须符合你现有协议或 server 端能处理
                    SendData($"{{\"message_type\":\"identify\",\"device_id\":\"{deviceShortID}\"}}");
                }

                StartReceiveThread();
            }
            catch (Exception ex)
            {
                Debug.LogError($"<color=red>[TCP CoPlayer]</color> Connect Error: {ex.Message}");
                HandleConnectionFailure();
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
            SocketMsgType.FromServer fromServerType = SocketMsgType.GetFromServerMessageType(msg_type);

            switch (fromServerType)
            {
                case SocketMsgType.FromServer.Update:
                    positionInfo.LoadFromJson(msg);
                    positionInfo.PrintDebug();
                    Debug.Log($"<color=white>[TCP CoPlayer]</color> {msg_type} > Player Count {positionInfo.player_count}");
                    DebugModeConsole.Print($"ID - {heartbeatPayload.heartbeat.device_id}\nSeq - {mySequence}\nPlayers - {positionInfo.player_count}", false);
                    break;

                case SocketMsgType.FromServer.MoveCommand:
                    int newChapter = ExtractMoveCommandChapter(msg, currentChapter);
                    try
                    {
                        moveCommandPayload.LoadFromJson(msg);
                        moveCommandPayload.PrintDebug();
                    }
                    catch (Exception ex)
                    {
                        Debug.LogWarning($"<color=yellow>[TCP CoPlayer]</color> MoveCommand payload parse fallback: {ex.Message}");
                    }
                    OnChapterChange(newChapter);
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

        private void OnChapterChange(int newChapter)
        {
            bool isSameChapter = currentChapter == newChapter;

            if (!isSameChapter)
            {
                MoveChapterUEvent.Invoke(newChapter);
            }

            if (newChapter == GameStartChapter)
            {
                EventManager.Broadcast(Events.onGameStart);
                GameStartUEvent.Invoke();
            }

            currentChapter = newChapter;
            heartbeatPayload.heartbeat.SetChapter(newChapter);
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
                // 原本的附加信息（下面会被 debug 文本覆盖；如果你想保留两者，请改成拼接）
                heartbeatPayload.heartbeat.SetMessage(realWorldPlayerLocateMgr.AddtionalMsg);
            }

            // 发给 server
            SendData(BuildHeartbeatJson());
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

        private static int ExtractMoveCommandChapter(string json, int fallback)
        {
            if (string.IsNullOrEmpty(json))
            {
                return fallback;
            }

            Match match = Regex.Match(json, "\"chapter\"\\s*:\\s*(-?\\d+(?:\\.\\d+)?)", RegexOptions.CultureInvariant);
            if (!match.Success)
            {
                return fallback;
            }

            if (float.TryParse(match.Groups[1].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out float parsedChapter))
            {
                int chapter = Mathf.RoundToInt(parsedChapter);
                if (Mathf.Approximately(parsedChapter, chapter))
                {
                    return chapter;
                }
            }

            return fallback;
        }

        private string BuildHeartbeatJson()
        {
            string json = heartbeatPayload.ToJson();
            return Regex.Replace(
                json,
                "\"chapter\"\\s*:\\s*-?\\d+(?:\\.\\d+)?",
                $"\"chapter\":{currentChapter}",
                RegexOptions.CultureInvariant
            );
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
}
