using System.Collections;
using UnityEngine;

/// <summary>
/// 「聲音按鈕」物件：被觸發時播放清單中「指定索引」的音效（固定對應，不輪播）。
/// 平時這個 GameObject 是 inactive，收到指令才啟用、播一次、再自動 inactive。
/// 後台 play_sound 會帶 sound_index：
///   0 = 發送提示1（clips[0]）、1 = 發送提示2（clips[1]）、2 = 提示3 ...
/// 同一顆按鈕永遠播同一個索引，按幾次都一樣。
/// </summary>
[RequireComponent(typeof(AudioSource))]
public class SoundTrigger : MonoBehaviour
{
    [Header("音效設定")]
    [Tooltip("音效清單，與後台「發送提示N」按鈕一對一固定對應（不輪播）：\n" +
             "Element 0 = 提示1、Element 1 = 提示2、Element 2 = 提示3 ...\n" +
             "後台送哪個 sound_index 就播對應的那一個。")]
    [SerializeField] private AudioClip[] clips;

    [Tooltip("音量 (0~1)")]
    [Range(0f, 1f)]
    [SerializeField] private float volume = 1f;

    [Header("觸發方式")]
    [Tooltip("物件被 SetActive(true) 時自動播放一次（用 PlayOnce 啟用時會播當次指定的那一個）")]
    [SerializeField] private bool playOnEnable = true;

    [Tooltip("兩次觸發間的最短間隔(秒)，0 = 不限制。可避免同一幀被連點多次")]
    [SerializeField] private float minInterval = 0f;

    [Header("自動關閉")]
    [Tooltip("播放完後自動把這個 GameObject SetActive(false)")]
    [SerializeField] private bool deactivateAfterPlay = true;

    [Tooltip("自動關閉的延遲秒數；<= 0 表示改用音效本身的長度（讓聲音完整播完）")]
    [SerializeField] private float deactivateDelay = 0f;

    private AudioSource _audioSource;
    private float _lastPlayTime = -999f;
    private Coroutine _deactivateRoutine;

    // 最近一次實際播放的音效，用來決定自動關閉要等多久（不同 clip 長度不同）。
    private AudioClip _lastPlayedClip;

    // PlayOnce(index) 先把要播的索引記起來，等 OnEnable 啟用後再播這一個。
    // 預設 0；因為每次 PlayOnce 都會先覆寫它，所以「指定哪個就固定播哪個」。
    private int _pendingClipIndex = 0;

    private void Awake()
    {
        _audioSource = GetComponent<AudioSource>();
        // 用 PlayOneShot 手動控制，關掉自動播放避免重複
        _audioSource.playOnAwake = false;
    }

    private void OnEnable()
    {
        if (playOnEnable)
            PlayClipAt(_pendingClipIndex);

        // 用實際播出的那個 clip 決定關閉延遲（PlayClipAt 會更新 _lastPlayedClip）
        ScheduleDeactivate(_lastPlayedClip);
    }

    private void OnDisable()
    {
        // 物件被關閉時，掛在它身上的協程會自動停止，這裡只清掉引用
        _deactivateRoutine = null;
    }

    /// <summary>
    /// 後台 / 其他程式呼叫：啟用物件→播放清單第 clipIndex 個音效（固定對應）→自動關閉。
    /// 即使這個 GameObject 目前是 inactive 也可以呼叫（會把它打開）。index 從 0 起算。
    /// </summary>
    public void PlayOnce(int clipIndex)
    {
        _pendingClipIndex = clipIndex;

        if (!gameObject.activeSelf)
        {
            // OnEnable 會用 _pendingClipIndex 播放並排程自動關閉
            gameObject.SetActive(true);
            return;
        }

        // 已經是 active：直接播指定的那個，並重置自動關閉計時
        PlayClipAt(clipIndex);
        ScheduleDeactivate(_lastPlayedClip);
    }

    /// <summary>沒帶索引時預設播第 0 個（提示1）。</summary>
    public void PlayOnce()
    {
        PlayOnce(0);
    }

    /// <summary>
    /// 臨時指定一個音效播放（需物件已是 active），不影響上面的索引設定。
    /// </summary>
    public void Trigger(AudioClip overrideClip)
    {
        if (overrideClip != null)
            Play(overrideClip);
    }

    /// <summary>
    /// 播放清單中第 index 個音效（index 從 0 起算）。
    /// </summary>
    private void PlayClipAt(int index)
    {
        AudioClip c = GetClipAt(index);
        if (c == null)
        {
            Debug.LogWarning($"[{nameof(SoundTrigger)}] 索引 {index} 沒有對應的 AudioClip：{name}", this);
            return;
        }
        Play(c);
    }

    /// <summary>取得清單中第 index 個音效；超出範圍回傳 null。</summary>
    private AudioClip GetClipAt(int index)
    {
        if (clips != null && index >= 0 && index < clips.Length)
            return clips[index];
        return null;
    }

    private void Play(AudioClip clipToPlay)
    {
        if (clipToPlay == null)
            return;

        // 間隔保護：在 minInterval 內重複觸發就忽略
        if (minInterval > 0f && Time.unscaledTime - _lastPlayTime < minInterval)
            return;

        _lastPlayTime = Time.unscaledTime;
        _lastPlayedClip = clipToPlay;

        // PlayOneShot 每次都疊加播放，連續觸發不會互相打斷
        _audioSource.PlayOneShot(clipToPlay, volume);
    }

    private void ScheduleDeactivate(AudioClip playedClip)
    {
        if (!deactivateAfterPlay || !gameObject.activeInHierarchy)
            return;

        if (_deactivateRoutine != null)
            StopCoroutine(_deactivateRoutine);

        AudioClip reference = playedClip != null ? playedClip : _lastPlayedClip;
        float wait = deactivateDelay > 0f
            ? deactivateDelay
            : (reference != null ? reference.length : 1.5f);

        _deactivateRoutine = StartCoroutine(DeactivateAfter(wait));
    }

    private IEnumerator DeactivateAfter(float seconds)
    {
        // 用 realtime，timeScale=0（暫停）時音效仍會播放，也才會正常關閉
        yield return new WaitForSecondsRealtime(seconds);
        _deactivateRoutine = null;
        gameObject.SetActive(false);
    }
}
