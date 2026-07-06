using UnityEngine;
using System;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Generic;
using System.Net.Sockets;
using GM;
using UnityEngine.Events;

namespace MultiPlayer {
    public class CoPlayerSocketMgr : MonoBehaviour {
        public static CoPlayerSocketMgr Instance { get; private set; }
        [Header("Socket Parameters")]
        public string serverIP = "127.0.0.1";
        public int serverPort = 8888;
        public string serverPath = "";
        private string deviceShortID = "";
        public string ServerUri {
            get {
                return $"ws://{serverIP}:{serverPort}/{serverPath}/{deviceShortID}";
            }
        }

        public float reconnectInterval = 5f;
        public float heartbeatInterval = 10f;
        public float heartbeatTimeout = 30f;

        [Header("GM Scripts")]
        public AweTest.MRUKMapper SpaceCalibrationMapper = null;
        public GM.RealWorldPlayerLocateMgr realWorldPlayerLocateMgr = null;

        private ClientWebSocket wsClient;
        public bool IsConnected { get; private set; } = false;

        [Header("Player Position Sync. Part")]
        public GameObject HMDObj;
        public Interaction.QuestDetectHand RHandDector;
        public Interaction.QuestDetectHand LHandDector;
        [Space]
        public GameObject PlayerVisualPrefab;

        private Queue<string> receivedMessages = new Queue<string>();
        private readonly object messageQueueLock = new object();

        private static int mySequence = 0;

        public static int MySequence {
            get {
                return mySequence;
            }
        }

        private long lastHeartbeatSendTime;
        private long lastHeartbeatReceiveTime;

        public event Action<string> OnMessageReceived;
        public event Action<bool> OnConnectionStatusChanged;
        private CancellationTokenSource cancellationTokenSource;
        
        [Space]
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
        

        void Awake() {
            if (Instance != null && Instance != this) {
                Destroy(gameObject);
            } else {
                Instance = this;
                DontDestroyOnLoad(gameObject);
            }
        }

        void InitialData() {
            deviceShortID = GM.Utils.ShortDeviceID();
            heartbeatPayload = new HeartbeatPayload(deviceShortID);
            readyToMovePayload = new ReadyToMovePayload(deviceShortID);
        }

        void Start() {
            InitialData();
            StartClient();
        }

        void FixedUpdate() {
            lock (messageQueueLock) {
                while (receivedMessages.Count > 0) {
                    string message = receivedMessages.Dequeue();
                    Debug.Log("<color=white>[CoPlayer Socket]</color> Recv.: " + message);
                    SocketPayloadBasic socketPayloadBasic = new SocketPayloadBasic();
                    socketPayloadBasic.LoadFromJson(message);
                    
                    if (socketPayloadBasic.IsValidType) {
                        RecvMsgHandler(socketPayloadBasic.message_type, message);
                    } else {
                        SocketPayloadEventBasic socketPayloadEventBasic = new SocketPayloadEventBasic();
                        socketPayloadEventBasic.LoadFromJson(message);
                        RecvMsgHandler(socketPayloadEventBasic.event_type, message);
                    }

                    OnMessageReceived?.Invoke(message);

                    lastHeartbeatReceiveTime = DateTime.Now.Ticks;
                }
            }

            if (IsConnected) {
                // Heartbeat PING
                if (DateTime.Now.Ticks - lastHeartbeatSendTime >= heartbeatInterval) {
                    PassHeartbeat();
                    lastHeartbeatSendTime = DateTime.Now.Ticks;
                }

                // // Check Timeout
                // if (DateTime.Now.Ticks - lastHeartbeatReceiveTime >= heartbeatTimeout) {
                //     Debug.LogWarning("<color=white>[CoPlayer Socket]</color> Heartbeat Timeout.");
                //     Disconnect();
                //     Invoke("Reconnect", reconnectInterval);
                // }
            }
        }

        void OnApplicationQuit() {
            Disconnect();
        }

        void OnDestroy() {
            Disconnect();
        }

        void OnChapterChange(int newChapter) {
            if (heartbeatPayload.heartbeat.chapter == newChapter) {
                return;
            }

            if (heartbeatPayload.heartbeat.chapter < 0 && newChapter == 0) {
                EventManager.Broadcast(Events.onGameStart);
                GameStartUEvent.Invoke();
            } else {
                MoveChapterUEvent.Invoke(newChapter);
            }
            
            heartbeatPayload.heartbeat.SetChapter(newChapter);
        }

        void OnSequenceChange(int newSeq) {
            if (mySequence == newSeq) {
                Debug.Log("[<color=green>Seats</color>] Seats NOT chagned.");
                return;
            }

            mySequence = newSeq;
            PlayerPrefs.SetInt(MPConstant.PLAYER_SEQNUM, newSeq);
            Events.onSequenceChange.newSeq = newSeq;
            EventManager.Broadcast(Events.onSequenceChange);
        }

        public void SetReadyToMove(bool isReady) {
            PassReadyToMove(isReady);
        }

#region Passing Data Handlers
        void RecvMsgHandler(string msg_type, string msg) {
            SocketMsgType.FromServer fromServerType = SocketMsgType.GetFromServerMessageType(msg_type);

            switch (fromServerType) {
                case SocketMsgType.FromServer.Update:
                    positionInfo.LoadFromJson(msg);
                    positionInfo.PrintDebug();
                    Debug.Log($"<color=white>[CoPlayer Socket]</color> {msg_type} > Player Count {positionInfo.player_count}");
                    DebugModeConsole.Print($"ID - {heartbeatPayload.heartbeat.device_id}\nSeq - {mySequence}\nPlayers - {positionInfo.player_count}", false);
                    break;
                case SocketMsgType.FromServer.MoveCommand:
                    moveCommandPayload.LoadFromJson(msg);
                    moveCommandPayload.PrintDebug();
                    OnChapterChange(moveCommandPayload.move_command.chapter);
                    // //--- Testing Part
                    // heartbeatPayload.heartbeat.chapter = moveCommandPayload.move_command.chapter;
                    // //---
                    break;
                case SocketMsgType.FromServer.AssignSequence:
                    assignSequencePayload.LoadFromJson(msg);
                    assignSequencePayload.PrintDebug();
                    OnSequenceChange(assignSequencePayload.sequence);
                    break;
                default:
                    Debug.Log($"<color=white>[CoPlayer Socket]</color> Type {msg_type} Not Yet Implement.");
                    break;
            }
        }

        void PassHeartbeat() {
            if (HMDObj == null || SpaceCalibrationMapper == null) {
                Debug.Log("<color=red>[CoPlayer Socket]</color> Please Set HMD Object or SpaceCalibrationMapper.");
                return;
            }

            heartbeatPayload.heartbeat.UpdateData(
                SpaceCalibrationMapper.GetPositionInCoordinate(HMDObj.transform.position),
                SpaceCalibrationMapper.GetPositionInCoordinate(RHandDector.HandWorldPosition),
                RHandDector.IsNowHandTracked,
                SpaceCalibrationMapper.GetPositionInCoordinate(LHandDector.HandWorldPosition),
                LHandDector.IsNowHandTracked
            );

            if (realWorldPlayerLocateMgr != null) {
                heartbeatPayload.heartbeat.SetChapter(realWorldPlayerLocateMgr.nowPreset);
                heartbeatPayload.heartbeat.SetMessage(realWorldPlayerLocateMgr.AddtionalMsg);
            }

            SendData(heartbeatPayload.ToJson());
        }

        void PassReadyToMove(bool isReady) {
            readyToMovePayload.ready_to_move.SetChapter(isReady ? 1 : -1);
            SendData(readyToMovePayload.ToJson());
        }

#endregion

#region Socket Functions
        public void StartClient() {
            if (IsConnected) {
                Debug.LogWarning("<color=white>[CoPlayer Socket]</color> Already Connected.");
                return;
            }

            cancellationTokenSource = new CancellationTokenSource();
            ConnectToServerAsync(cancellationTokenSource.Token);
        }

        private async void ConnectToServerAsync(CancellationToken cancellationToken) {
            if (wsClient != null &&
               (wsClient.State == WebSocketState.Open || wsClient.State == WebSocketState.Connecting)) {
                await DisconnectAsync();
            }

            try {
                wsClient = new ClientWebSocket();
                Debug.Log($"<color=white>[CoPlayer Socket]</color> Connect to {ServerUri}");
                await wsClient.ConnectAsync(new Uri(ServerUri), cancellationToken);

                IsConnected = true;
                OnConnectionStatusChanged?.Invoke(true);
                Debug.Log("<color=white>[CoPlayer Socket]</color> Connect Successfully.");

                lastHeartbeatSendTime = DateTime.Now.Ticks;
                lastHeartbeatReceiveTime = DateTime.Now.Ticks;

                await ReceiveLoop(cancellationToken);
            } catch (WebSocketException ex) {
                Debug.LogError($"<color=red>[CoPlayer Socket]</color> WebSocket Connect Error: {ex.Message}");
                HandleConnectionFailure();
            } catch (OperationCanceledException) {
                Debug.Log("<color=red>[CoPlayer Socket]</color> WebSocket Connect be Cannceled.");
                HandleConnectionFailure();
            } catch (Exception ex) {
                Debug.LogError($"<color=red>[CoPlayer Socket]</color> WebSocket Error: {ex.Message}");
                HandleConnectionFailure();
            }
        }

        private async Task ReceiveLoop(CancellationToken cancellationToken) {
            byte[] buffer = new byte[8192];
            ArraySegment<byte> bufferSegment = new ArraySegment<byte>(buffer);

            while (wsClient != null && wsClient.State == WebSocketState.Open && !cancellationToken.IsCancellationRequested) {
                try {
                    WebSocketReceiveResult result = await wsClient.ReceiveAsync(bufferSegment, cancellationToken);

                    if (result.MessageType == WebSocketMessageType.Text) {
                        string message = Encoding.UTF8.GetString(buffer, 0, result.Count);
                        lock (messageQueueLock) {
                            receivedMessages.Enqueue(message);
                        }
                    } else if (result.MessageType == WebSocketMessageType.Close) {
                        Debug.LogWarning($"<color=white>[CoPlayer Socket]</color> WebSocket Server Closed. Status: {result.CloseStatus} - {result.CloseStatusDescription}");
                        HandleConnectionFailure();
                        break;
                    } else if (result.MessageType == WebSocketMessageType.Binary) {
                        Debug.LogWarning("<color=white>[CoPlayer Socket]</color> Recevied Binary Data.");
                    }
                } catch (WebSocketException ex) {
                    Debug.LogError($"<color=red>[CoPlayer Socket]</color> WebSocket Recv. Error: {ex.Message}");
                    HandleConnectionFailure();
                    break;
                } catch (OperationCanceledException) {
                    Debug.Log("<color=red>[CoPlayer Socket]</color> WebSocket Recv. Op. Canceled.");
                    break;
                } catch (Exception ex) {
                    Debug.LogError($"<color=red>[CoPlayer Socket]</color> WebSocket Error: {ex.Message}");
                    HandleConnectionFailure();
                    break;
                }
            }
            Debug.Log("<color=white>[CoPlayer Socket]</color> WebSocket Stop Recv. Loop.");
        }

        private void HandleConnectionFailure() {
            if (IsConnected) {
                IsConnected = false;
                OnConnectionStatusChanged?.Invoke(false);
            }

            cancellationTokenSource?.Cancel();
            cancellationTokenSource?.Dispose();
            cancellationTokenSource = null;

            Invoke(nameof(Reconnect), reconnectInterval);
        }

        public async void SendData(string message) {
            if (!IsConnected || wsClient == null || wsClient.State != WebSocketState.Open) {
                Debug.LogWarning("<color=white>[CoPlayer Socket]</color> No Connection.");
                return;
            }

            try {
                byte[] bytesToSend = Encoding.UTF8.GetBytes(message);
                ArraySegment<byte> bufferSegment = new ArraySegment<byte>(bytesToSend);

                await wsClient.SendAsync(bufferSegment, WebSocketMessageType.Text, true, CancellationToken.None);
                // Debug.Log("<color=white>[CoPlayer Socket]</color> Send: " + message);
            } catch (WebSocketException ex) {
                Debug.LogError("<color=white>[CoPlayer Socket]</color> Send Error: " + ex.Message);
                HandleConnectionFailure();
            } catch (Exception ex) {
                Debug.LogError("<color=white>[CoPlayer Socket]</color> Error: " + ex.Message);
            }
        }

        public async void Disconnect() {
            await DisconnectAsync();
        }

        private async Task DisconnectAsync() {
            if (wsClient == null) return;

            IsConnected = false;
            OnConnectionStatusChanged?.Invoke(false);

            cancellationTokenSource?.Cancel();
            cancellationTokenSource?.Dispose();
            cancellationTokenSource = null;

            if (wsClient.State == WebSocketState.Open || wsClient.State == WebSocketState.Connecting) {
                try {
                    await wsClient.CloseAsync(WebSocketCloseStatus.NormalClosure, "Client initiated close", CancellationToken.None);
                } catch (Exception ex) {
                    Debug.LogError($"<color=red>[CoPlayer Socket]</color> Close WebSocket Error: {ex.Message}");
                }
            }
            
            wsClient.Dispose();
            wsClient = null;

            Debug.Log("<color=white>[CoPlayer Socket]</color> WebSocket Disconnected.");
            CancelInvoke(nameof(Reconnect));
        }

        private void Reconnect() {
            if (!IsConnected) {
                Debug.Log("<color=white>[CoPlayer Socket]</color> Try to Reconnect...");
                CancelInvoke(nameof(Reconnect));
                StartClient();
            }
        }

#endregion

    }
}
