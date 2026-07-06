using UnityEngine;
using UnityEngine.Playables;

public class QuestFocusSafeTimeline : MonoBehaviour
{
    [Header("Timeline")]
    [SerializeField] private PlayableDirector[] directors;
    [SerializeField] private bool autoFindSceneDirectors = true;
    [SerializeField] private bool useUnscaledTime = true;
    [SerializeField] private bool resumeAfterRealPause = true;

    [Header("Disable only when input focus is lost")]
    [SerializeField] private Behaviour[] inputBehaviours;
    [SerializeField] private GameObject[] trackedVisuals;
    [SerializeField] private bool disableTrackedVisualsOnInputFocusLost = false;

    [Header("Pause these only on real app pause")]
    [SerializeField] private AudioSource[] audioSources;
    [SerializeField] private bool keepMobileAudioOutputAlive = true;

    [Header("Socket focus notification")]
    [SerializeField] private bool notifyServerOnFocusChange = true;
    [SerializeField] private float duplicateFocusEventCooldown = 0.5f;

    private bool pausedByRealAppPause;
    private bool[] wasPlayingBeforePause;
    private string lastFocusEventKey = "";
    private float lastFocusEventSentAt = -999f;

    private void Awake()
    {
        CacheDirectors();
        ApplyTimelineClock();
        EnsureMobileAudioOutput();
    }

    private void OnEnable()
    {
        OVRManager.InputFocusLost += HandleInputFocusLost;
        OVRManager.InputFocusAcquired += HandleInputFocusAcquired;
    }

    private void OnDisable()
    {
        OVRManager.InputFocusLost -= HandleInputFocusLost;
        OVRManager.InputFocusAcquired -= HandleInputFocusAcquired;
    }

    private void HandleInputFocusLost()
    {
        NotifyServerFocusState("input_focus_lost", false, pausedByRealAppPause, "OVRManager.InputFocusLost");
        SetBehavioursEnabled(inputBehaviours, false);
        if (disableTrackedVisualsOnInputFocusLost)
        {
            SetGameObjectsActive(trackedVisuals, false);
        }
        EnsureMobileAudioOutput();
    }

    private void HandleInputFocusAcquired()
    {
        RestoreInputFocusObjects();
        EnsureMobileAudioOutput();
        NotifyServerFocusState("input_focus_acquired", true, pausedByRealAppPause, "OVRManager.InputFocusAcquired");
    }

    private void OnApplicationFocus(bool hasFocus)
    {
        if (!hasFocus)
        {
            return;
        }

        RestoreInputFocusObjects();
        EnsureMobileAudioOutput();
    }

    private void OnApplicationPause(bool pauseStatus)
    {
        if (pauseStatus)
        {
            pausedByRealAppPause = true;
            NotifyServerFocusState("application_pause", false, true, "OnApplicationPause(true)");

            if (directors == null || directors.Length == 0)
            {
                SetAudioPaused(true);
                return;
            }

            wasPlayingBeforePause = new bool[directors.Length];

            for (int i = 0; i < directors.Length; i++)
            {
                var director = directors[i];
                if (director == null)
                {
                    continue;
                }

                wasPlayingBeforePause[i] = director.state == PlayState.Playing;
                if (wasPlayingBeforePause[i])
                {
                    director.Pause();
                }
            }

            SetAudioPaused(true);
            return;
        }

        if (!pausedByRealAppPause)
        {
            return;
        }

        pausedByRealAppPause = false;
        RestoreInputFocusObjects();
        EnsureMobileAudioOutput();
        NotifyServerFocusState("application_resume", true, false, "OnApplicationPause(false)");

        if (directors == null || directors.Length == 0)
        {
            SetAudioPaused(false);
            return;
        }

        if (resumeAfterRealPause && wasPlayingBeforePause != null)
        {
            ApplyTimelineClock();

            for (int i = 0; i < directors.Length; i++)
            {
                var director = directors[i];
                if (director == null)
                {
                    continue;
                }

                if (i < wasPlayingBeforePause.Length && wasPlayingBeforePause[i])
                {
                    director.Resume();
                }
            }
        }

        SetAudioPaused(false);
    }

    private void RestoreInputFocusObjects()
    {
        SetBehavioursEnabled(inputBehaviours, true);
        SetGameObjectsActive(trackedVisuals, true);
    }

    private void ApplyTimelineClock()
    {
        if (!useUnscaledTime || directors == null)
        {
            return;
        }

        foreach (var director in directors)
        {
            if (director != null)
            {
                director.timeUpdateMode = DirectorUpdateMode.UnscaledGameTime;
            }
        }
    }

    private void CacheDirectors()
    {
        if (directors != null && directors.Length > 0)
        {
            return;
        }

        if (autoFindSceneDirectors)
        {
            directors = FindObjectsOfType<PlayableDirector>(true);
            return;
        }

        var localDirector = GetComponent<PlayableDirector>();
        if (localDirector != null)
        {
            directors = new[] { localDirector };
        }
    }

    private void SetAudioPaused(bool paused)
    {
        if (audioSources == null)
        {
            return;
        }

        foreach (var src in audioSources)
        {
            if (src == null)
            {
                continue;
            }

            if (paused)
            {
                src.Pause();
            }
            else
            {
                src.UnPause();
            }
        }
    }

    private void EnsureMobileAudioOutput()
    {
#if UNITY_ANDROID && !UNITY_EDITOR
        if (!keepMobileAudioOutputAlive)
        {
            return;
        }

        if (!AudioSettings.Mobile.audioOutputStarted)
        {
            AudioSettings.Mobile.StartAudioOutput();
        }

        AudioListener.pause = false;
#endif
    }

    private void NotifyServerFocusState(
        string eventName,
        bool hasInputFocus,
        bool appPaused,
        string reason,
        bool force = false
    )
    {
        if (!notifyServerOnFocusChange)
        {
            return;
        }

        var socketMgr = MultiPlayer.CoPlayerSocketMgr.Instance;
        if (socketMgr == null || !socketMgr.IsConnected)
        {
            return;
        }

        string eventKey = eventName + "|" + hasInputFocus + "|" + appPaused;
        float now = Time.realtimeSinceStartup;
        if (!force && eventKey == lastFocusEventKey && now - lastFocusEventSentAt < duplicateFocusEventCooldown)
        {
            return;
        }

        lastFocusEventKey = eventKey;
        lastFocusEventSentAt = now;
        socketMgr.SendFocusState(eventName, hasInputFocus, appPaused, reason);
    }

    private static void SetBehavioursEnabled(Behaviour[] behaviours, bool enabled)
    {
        if (behaviours == null)
        {
            return;
        }

        foreach (var behaviour in behaviours)
        {
            if (behaviour != null)
            {
                behaviour.enabled = enabled;
            }
        }
    }

    private static void SetGameObjectsActive(GameObject[] objects, bool active)
    {
        if (objects == null)
        {
            return;
        }

        foreach (var obj in objects)
        {
            if (obj != null)
            {
                obj.SetActive(active);
            }
        }
    }
}
