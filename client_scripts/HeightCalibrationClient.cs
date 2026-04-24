using UnityEngine;
using System;
using System.Text;
using System.Collections.Generic;

// Reuse your existing namespace or use a new one
namespace MultiPlayer
{
    // Make sure this class is attached to a GameObject in your scene
    public class HeightCalibrationClient : MonoBehaviour
    {
        [Header("Target Objects")]
        public GameObject chenyuhui;
        // 3in1 starts with digit, so we use a valid C# identifier
        public GameObject obj3in1; 
        public GameObject hollow;

        [Header("Calibration Settings")]
        [Tooltip("Scale factor for height. If server sends 100 and you want 1.0m, set to 0.01.")]
        public float heightScale = 0.01f; 
        
        // Initial Y positions to apply offset relative to
        private float initialY_Chen;
        private float initialY_3in1;
        private float initialY_Hollow;

        // Reference to the Socket Manager
        private CoPlayerSocketMgr socketMgr;

        void Start()
        {
            // Record initial Y positions
            if (chenyuhui != null) initialY_Chen = chenyuhui.transform.localPosition.y;
            if (obj3in1 != null) initialY_3in1 = obj3in1.transform.localPosition.y;
            if (hollow != null) initialY_Hollow = hollow.transform.localPosition.y;

            socketMgr = CoPlayerSocketMgr.Instance;
            if (socketMgr == null)
            {
                Debug.LogError("[HeightCalibrationClient] CoPlayerSocketMgr instance not found!");
                return;
            }

            // Subscribe to message events
            socketMgr.OnMessageReceived += OnMessageReceived;
            Debug.Log("[HeightCalibrationClient] Listening for commands...");
        }

        void OnDestroy()
        {
            if (socketMgr != null)
            {
                socketMgr.OnMessageReceived -= OnMessageReceived;
            }
        }

        private void OnMessageReceived(string jsonMessage)
        {
            try
            {
                // We do a simple check for "message_type":"height_calibration"
                // This avoids full parsing if it's not our message
                if (jsonMessage.Contains("\"height_calibration\""))
                {
                    // Basic parsing
                    // Since "3in1_height" is invalid for JsonUtility optimization,
                    // and we might not have NewtonSoft, we can do manual extraction 
                    // or a simple wrapper.
                    
                    // Let's use a helper that parses standard keys, 
                    // and manually extract 3in1 if needed.
                    
                    HeightCalibPayload payload = JsonUtility.FromJson<HeightCalibPayload>(jsonMessage);
                    
                    if (payload != null && payload.message_type == "height_calibration")
                    {
                         // Check target device id if present (handled by server unicast usually, 
                         // but if it's broadcast, we can check again)
                         // For now, we assume if we received it, we process it.
                         
                         // Parse 3in1 manually because JsonUtility won't map "3in1_height" to a field easily 
                         // unless we use a standardized naming.
                         // Hacky extract for "3in1_height"
                         int val3in1 = ExtractInt(jsonMessage, "3in1_height");
                         
                         ApplyHeights(payload.chenyuhui_height, val3in1, payload.hollow_height);
                    }
                }
            }
            catch (Exception e)
            {
                Debug.LogError($"[HeightCalibrationClient] Error parsing: {e.Message}");
            }
        }

        private void ApplyHeights(int h_chen, int h_3in1, int h_hollow)
        {
            Debug.Log($"[HeightCalibration] Applying Height Offsets: Chen={h_chen}, 3in1={h_3in1}, Hollow={h_hollow}");

            if (chenyuhui != null)
            {
                Vector3 pos = chenyuhui.transform.localPosition;
                // Offset from initial Y
                pos.y = initialY_Chen + (h_chen * heightScale);
                chenyuhui.transform.localPosition = pos;
            }

            if (obj3in1 != null)
            {
                Vector3 pos = obj3in1.transform.localPosition;
                // Offset from initial Y
                pos.y = initialY_3in1 + (h_3in1 * heightScale);
                obj3in1.transform.localPosition = pos;
            }

            if (hollow != null)
            {
                Vector3 pos = hollow.transform.localPosition;
                // Offset from initial Y
                pos.y = initialY_Hollow + (h_hollow * heightScale);
                hollow.transform.localPosition = pos;
            }
        }

        // Simple helper to extract int value from JSON string by key
        // Finds "key": 123
        private int ExtractInt(string json, string key)
        {
            try
            {
                string searchKey = $"\"{key}\":";
                int start = json.IndexOf(searchKey);
                if (start == -1) return 0;
                
                start += searchKey.Length;
                
                // Find end (comma or close brace)
                int endComma = json.IndexOf(',', start);
                int endBrace = json.IndexOf('}', start);
                
                int end = (endComma == -1) ? endBrace : (endBrace == -1 ? endComma : Math.Min(endComma, endBrace));
                
                if (end == -1) return 0;
                
                string valStr = json.Substring(start, end - start).Trim();
                return int.Parse(valStr);
            }
            catch
            {
                return 0;
            }
        }
    }

    [Serializable]
    public class HeightCalibPayload
    {
        public string message_type;
        public int chenyuhui_height;
        public int hollow_height;
        // public int 3in1_height; // INVALID in C#, handled manually
    }
}
