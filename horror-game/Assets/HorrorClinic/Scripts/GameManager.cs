using System.Collections;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

/// <summary>
/// Startet das Spiel automatisch beim Drücken von Play – in jeder Szene.
/// Steuert Ablauf, Angstlevel, Jumpscare, Sieg/Tod und das HUD.
/// </summary>
public class GameManager : MonoBehaviour
{
    public static GameManager I;
    public enum State { Intro, Playing, Paused, Dead, Won }
    public State state = State.Intro;

    public float Fear { get; private set; }
    public int FusesFound { get; private set; }
    public bool NoteOpen { get; private set; }
    public int NoteClosedFrame { get; private set; } = -1;

    public PlayerController Player { get; private set; }
    public Monster Monster { get; private set; }
    public HorrorFX FX { get; private set; }
    public ClinicData Data { get; private set; }

    Transform world;
    float fearTarget, chaseStingerCd, ambientTimer, playTime, endTime;
    string msg; float msgTime;
    string noteTitle, noteBody;
    AudioSource sfx2D, ambience;
    bool skipIntro;

    // ---------- Bootstrap ----------
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void Boot()
    {
        if (FindFirstObjectByType<GameManager>() != null) return;
        // Standard-Kamera/Licht/Volume der Template-Szene entfernen
        foreach (var go in SceneManager.GetActiveScene().GetRootGameObjects())
            if (go.GetComponentInChildren<Camera>() || go.GetComponentInChildren<Light>() || go.GetComponentInChildren<Volume>())
                Destroy(go);
        new GameObject("HorrorClinic").AddComponent<GameManager>();
    }

    void Awake()
    {
        I = this;
        DontDestroyOnLoad(gameObject);
    }

    void Start() => Build();

    void Build()
    {
        if (world) Destroy(world.gameObject);
        world = new GameObject("World").transform;
        Fear = fearTarget = 0f; FusesFound = 0; NoteOpen = false; playTime = 0f;
        ambientTimer = Random.Range(12f, 25f); chaseStingerCd = 0f;

        Data = ClinicBuilder.Build(world, new System.Random());
        Player = PlayerController.Create(world, Data.PlayerSpawn, Data.PlayerYaw);
        Monster = Monster.Create(world, Data.MonsterSpawn, Data, Player);
        FX = HorrorFX.Create(world);

        sfx2D = world.gameObject.AddComponent<AudioSource>();
        ambience = world.gameObject.AddComponent<AudioSource>();
        ambience.clip = ProcAudio.Get("drone"); ambience.loop = true; ambience.volume = 0.45f; ambience.Play();

        state = skipIntro ? State.Playing : State.Intro;
        if (skipIntro) { LockCursor(true); ShowMessage("Finde die 3 Sicherungen. Bleib im Dunkeln."); }
        else LockCursor(false);
    }

    void LockCursor(bool l)
    {
        Cursor.lockState = l ? CursorLockMode.Locked : CursorLockMode.None;
        Cursor.visible = !l;
    }

    // ---------- Schnittstellen ----------
    public void ShowMessage(string m) { msg = m; msgTime = 4f; }
    public void Play2D(AudioClip c, float vol) { if (sfx2D) sfx2D.PlayOneShot(c, vol); }
    public void ReportFear(float f) => fearTarget = f;

    public void OpenNote(string title, string body)
    {
        noteTitle = title; noteBody = body; NoteOpen = true;
        Play2D(ProcAudio.Get("click"), 0.5f);
    }

    public void OnFusePicked()
    {
        FusesFound++;
        Play2D(ProcAudio.Get("pickup"), 0.9f);
        FlickerLight.SurgeAll(2f);
        FX.Flash(new Color(1f, 0.3f, 0.2f), 0.6f);
        Player.Shake(0.15f);
        Monster.HearNoise(Player.transform.position, true);
        ShowMessage(FusesFound < ExitGate.Needed
            ? $"Sicherung {FusesFound}/{ExitGate.Needed}. Irgendwo im Gebäude schreit etwas."
            : "Alle Sicherungen! Zum Notstromtor am Ende des Hauptflurs!");
    }

    public void OnChaseStart()
    {
        if (chaseStingerCd > 0f) return;
        chaseStingerCd = 18f;
        Play2D(ProcAudio.Get("stinger"), 0.9f);
        FX.Flash(new Color(0.8f, 0.05f, 0.05f), 0.5f);
        Player.Shake(0.12f);
    }

    public void OnGateOpening(ExitGate gate)
    {
        FlickerLight.AlarmAll();
        Monster.HearNoise(gate.transform.position, true);
        Monster.state = Monster.State.Chase;
        ShowMessage("Das Tor öffnet sich ... ER KOMMT!");
        Play2D(ProcAudio.Get("scream"), 0.5f);
    }

    public void PlayerCaught(Monster m)
    {
        if (state != State.Playing) return;
        state = State.Dead;
        NoteOpen = false;
        StartCoroutine(JumpscareRoutine(m));
    }

    public void Win()
    {
        if (state != State.Playing) return;
        state = State.Won;
        endTime = playTime;
        StartCoroutine(WinRoutine());
    }

    IEnumerator JumpscareRoutine(Monster m)
    {
        Player.Frozen = true;
        m.BeginJumpscare(Player.Cam.transform);
        Play2D(ProcAudio.Get("scream"), 1f);
        ambience.volume = 0f;
        for (float t = 0; t < 1.6f; t += Time.deltaTime)
        {
            Player.ForceLook(m.transform.position + Vector3.up * 2.6f, Time.deltaTime);
            Player.Shake(0.35f);
            FX.Jumpscare = 1f;
            yield return null;
        }
        FX.Jumpscare = 0f;
        m.gameObject.SetActive(false);
        for (float t = 0; t < 1f; t += Time.deltaTime) { FX.DeathTint = t; yield return null; }
        FX.DeathTint = 1f;
        endTime = playTime;
        LockCursor(false);
    }

    IEnumerator WinRoutine()
    {
        Player.Frozen = true;
        Monster.gameObject.SetActive(false);
        Play2D(ProcAudio.Get("pickup"), 1f);
        for (float t = 0; t < 2.5f; t += Time.deltaTime) { FX.WhiteOut = t / 2.5f; ambience.volume = 0.45f * (1 - t / 2.5f); yield return null; }
        FX.WhiteOut = 1f;
        LockCursor(false);
    }

    // ---------- Ablauf ----------
    void Update()
    {
        var kb = Keyboard.current; var ms = Mouse.current;
        if (kb == null) return;
        float dt = Time.deltaTime;

        switch (state)
        {
            case State.Intro:
                if (kb.spaceKey.wasPressedThisFrame || kb.enterKey.wasPressedThisFrame || (ms != null && ms.leftButton.wasPressedThisFrame))
                {
                    state = State.Playing; LockCursor(true);
                    ShowMessage("Finde die 3 Sicherungen. Bleib im Dunkeln.");
                }
                break;

            case State.Playing:
                playTime += dt;
                if (NoteOpen)
                {
                    if (kb.eKey.wasPressedThisFrame || kb.escapeKey.wasPressedThisFrame)
                    { NoteOpen = false; NoteClosedFrame = Time.frameCount; }
                }
                else if (kb.escapeKey.wasPressedThisFrame || kb.pKey.wasPressedThisFrame)
                {
                    state = State.Paused; Time.timeScale = 0f; AudioListener.pause = true; LockCursor(false);
                }
                if (ms != null && ms.leftButton.wasPressedThisFrame) LockCursor(true);
                AmbientEvents(dt);
                break;

            case State.Paused:
                if (kb.escapeKey.wasPressedThisFrame || kb.pKey.wasPressedThisFrame || (ms != null && ms.leftButton.wasPressedThisFrame))
                {
                    state = State.Playing; Time.timeScale = 1f; AudioListener.pause = false; LockCursor(true);
                }
                break;

            case State.Dead:
            case State.Won:
                if (kb.rKey.wasPressedThisFrame) { skipIntro = true; Build(); }
                break;
        }

        chaseStingerCd -= dt;
        msgTime -= dt;
        float rate = fearTarget > Fear ? 1.5f : 0.3f;
        Fear = Mathf.MoveTowards(Fear, state == State.Playing ? fearTarget : (state == State.Dead ? 1f : 0f), dt * rate);
    }

    void AmbientEvents(float dt)
    {
        ambientTimer -= dt;
        if (ambientTimer > 0f) return;
        ambientTimer = Random.Range(14f, 40f);
        string[] clips = { "whisper", "bang", "creak", "creak", "whisper" };
        var clip = ProcAudio.Get(clips[Random.Range(0, clips.Length)]);
        Vector3 dir = Random.onUnitSphere; dir.y = 0;
        Vector3 pos = Player.transform.position + dir.normalized * Random.Range(4f, 12f) + Vector3.up * 1.5f;
        AudioSource.PlayClipAtPoint(clip, pos, clip.name == "whisper" ? 0.8f : 1f);
        if (Random.value < 0.3f) FlickerLight.SurgeAll(0.8f);
    }

    // ---------- HUD ----------
    GUIStyle title, sub, small, hud, prompt, noteT, noteB;

    void InitStyles()
    {
        int h = Screen.height;
        title = new GUIStyle(GUI.skin.label) { fontSize = h / 9, fontStyle = FontStyle.Bold, alignment = TextAnchor.MiddleCenter };
        sub = new GUIStyle(title) { fontSize = h / 30, fontStyle = FontStyle.Normal };
        small = new GUIStyle(sub) { fontSize = h / 48 };
        hud = new GUIStyle(GUI.skin.label) { fontSize = h / 45, alignment = TextAnchor.UpperLeft };
        prompt = new GUIStyle(GUI.skin.label) { fontSize = h / 40, alignment = TextAnchor.MiddleCenter };
        noteT = new GUIStyle(GUI.skin.label) { fontSize = h / 30, fontStyle = FontStyle.Bold, wordWrap = true };
        noteB = new GUIStyle(GUI.skin.label) { fontSize = h / 42, wordWrap = true };
        noteT.normal.textColor = noteB.normal.textColor = new Color(0.12f, 0.1f, 0.08f);
    }

    static void Shadowed(Rect r, string s, GUIStyle st, Color c)
    {
        var old = st.normal.textColor;
        st.normal.textColor = new Color(0, 0, 0, c.a * 0.8f);
        GUI.Label(new Rect(r.x + 2, r.y + 2, r.width, r.height), s, st);
        st.normal.textColor = c;
        GUI.Label(r, s, st);
        st.normal.textColor = old;
    }

    static void Fill(Rect r, Color c)
    {
        var o = GUI.color; GUI.color = c;
        GUI.DrawTexture(r, Texture2D.whiteTexture);
        GUI.color = o;
    }

    void OnGUI()
    {
        if (title == null || title.fontSize != Screen.height / 9) InitStyles();
        float W = Screen.width, H = Screen.height;
        var blood = new Color(0.75f, 0.05f, 0.04f);

        switch (state)
        {
            case State.Intro:
            {
                Fill(new Rect(0, 0, W, H), new Color(0, 0, 0, 0.75f));
                Vector2 j = Random.value < 0.06f ? Random.insideUnitCircle * 8f : Vector2.zero;
                Shadowed(new Rect(j.x, H * 0.18f + j.y, W, H * 0.2f), "ST. AGNES", title, blood);
                Shadowed(new Rect(0, H * 0.36f, W, H * 0.06f), "Psychiatrische Klinik – geschlossen seit 1987", sub, new Color(0.8f, 0.8f, 0.75f));
                Shadowed(new Rect(0, H * 0.5f, W, H * 0.2f),
                    "WASD  bewegen      SHIFT  rennen      STRG / C  ducken\nF  Taschenlampe      E  benutzen      ESC  Pause\n\n" +
                    "Finde 3 Sicherungen und bring sie zum Notstromtor.\nEr hört dich, wenn du rennst. Er sieht dein Licht.",
                    small, new Color(0.7f, 0.7f, 0.68f));
                float a = 0.5f + 0.5f * Mathf.Sin(Time.unscaledTime * 3f);
                Shadowed(new Rect(0, H * 0.8f, W, H * 0.06f), "[ Klicken zum Starten ]  –  Kopfhörer empfohlen", sub, new Color(1, 1, 1, a));
                break;
            }
            case State.Playing:
            case State.Paused:
                DrawHud(W, H);
                if (state == State.Paused)
                {
                    Fill(new Rect(0, 0, W, H), new Color(0, 0, 0, 0.6f));
                    Shadowed(new Rect(0, H * 0.35f, W, H * 0.2f), "PAUSE", title, new Color(0.8f, 0.8f, 0.8f));
                    Shadowed(new Rect(0, H * 0.55f, W, H * 0.06f), "ESC / Klick – weiter", sub, Color.gray);
                }
                break;

            case State.Dead:
                if (FX && FX.DeathTint >= 1f)
                {
                    Fill(new Rect(0, 0, W, H), new Color(0.05f, 0, 0, 0.7f));
                    Shadowed(new Rect(0, H * 0.3f, W, H * 0.2f), "DU BIST TOT", title, blood);
                    Shadowed(new Rect(0, H * 0.5f, W, H * 0.06f), $"Patient 17 hat dich gefunden.   Überlebt: {FormatTime(endTime)}   Sicherungen: {FusesFound}/3", sub, new Color(0.8f, 0.7f, 0.7f));
                    Shadowed(new Rect(0, H * 0.65f, W, H * 0.06f), "[R]  Nochmal", sub, Color.white);
                }
                break;

            case State.Won:
                if (FX && FX.WhiteOut >= 1f)
                {
                    var dark = new Color(0.1f, 0.1f, 0.1f);
                    var st = new GUIStyle(title); st.normal.textColor = dark;
                    GUI.Label(new Rect(0, H * 0.3f, W, H * 0.2f), "ENTKOMMEN", st);
                    var s2 = new GUIStyle(sub); s2.normal.textColor = dark;
                    GUI.Label(new Rect(0, H * 0.5f, W, H * 0.06f), $"Zeit: {FormatTime(endTime)}  ...  aber in deinem Rückspiegel flackert ein Licht.", s2);
                    GUI.Label(new Rect(0, H * 0.65f, W, H * 0.06f), "[R]  Nochmal", s2);
                }
                break;
        }
    }

    void DrawHud(float W, float H)
    {
        var p = Player;
        if (!p) return;
        // Fadenkreuz
        Fill(new Rect(W / 2 - 2, H / 2 - 2, 4, 4), new Color(1, 1, 1, p.CurrentPrompt != null ? 0.9f : 0.35f));
        if (p.CurrentPrompt != null && !NoteOpen)
            Shadowed(new Rect(0, H / 2 + 20, W, 40), "[E]  " + p.CurrentPrompt, prompt, new Color(0.9f, 0.9f, 0.85f));

        Shadowed(new Rect(24, 18, W, 40), $"Sicherungen  {FusesFound}/{ExitGate.Needed}", hud, new Color(0.85f, 0.85f, 0.8f));
        if (p.Fuses > 0) Shadowed(new Rect(24, 18 + H / 40, W, 40), $"Im Inventar: {p.Fuses}", hud, new Color(1f, 0.6f, 0.2f));

        // Batterie & Ausdauer
        float bw = W * 0.14f, bh = 6f, x = 24f, y = H - 40f;
        Shadowed(new Rect(x, y - 26, 300, 30), p.FlashlightOn ? "LAMPE" : "LAMPE (aus)", hud, new Color(0.7f, 0.7f, 0.65f, 0.8f));
        Fill(new Rect(x, y, bw, bh), new Color(0, 0, 0, 0.5f));
        Fill(new Rect(x, y, bw * p.Battery, bh), p.Battery < 0.2f ? new Color(0.8f, 0.15f, 0.1f) : new Color(0.85f, 0.8f, 0.6f, 0.8f));
        if (p.Stamina < 0.99f)
        {
            Fill(new Rect(x + bw + 20, y, bw, bh), new Color(0, 0, 0, 0.5f));
            Fill(new Rect(x + bw + 20, y, bw * p.Stamina, bh), new Color(0.6f, 0.75f, 0.8f, 0.7f));
        }

        if (msgTime > 0f && !NoteOpen)
            Shadowed(new Rect(0, H * 0.78f, W, 40), msg, prompt, new Color(0.9f, 0.85f, 0.8f, Mathf.Clamp01(msgTime)));

        if (NoteOpen)
        {
            Fill(new Rect(0, 0, W, H), new Color(0, 0, 0, 0.55f));
            float nw = Mathf.Min(W * 0.5f, H * 0.75f), nh = H * 0.7f;
            var r = new Rect((W - nw) / 2, (H - nh) / 2, nw, nh);
            Fill(r, new Color(0.8f, 0.76f, 0.62f));
            Fill(new Rect(r.x + 8, r.y + 8, r.width - 16, r.height - 16), new Color(0.86f, 0.82f, 0.68f));
            GUI.Label(new Rect(r.x + 30, r.y + 25, r.width - 60, 80), noteTitle, noteT);
            GUI.Label(new Rect(r.x + 30, r.y + 25 + H / 14, r.width - 60, r.height - 120), noteBody, noteB);
            var hint = new GUIStyle(noteB) { alignment = TextAnchor.LowerRight };
            GUI.Label(new Rect(r.x + 30, r.y, r.width - 60, r.height - 20), "[E] schließen", hint);
        }
    }

    static string FormatTime(float t) => $"{(int)(t / 60):00}:{(int)(t % 60):00}";
}
