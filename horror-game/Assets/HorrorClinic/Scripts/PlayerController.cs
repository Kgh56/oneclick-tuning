using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.Rendering.Universal;

public class PlayerController : MonoBehaviour
{
    public Camera Cam;
    public Light Flash;
    public float Battery = 1f, Stamina = 1f;
    public int Fuses;
    public bool Crouching, Frozen, Sprinting;
    public float NoiseRadius;
    public string CurrentPrompt;
    public bool FlashlightOn => Flash && Flash.enabled;

    const float WalkSpeed = 2.6f, SprintSpeed = 5.3f, CrouchSpeed = 1.3f;
    const float Sens = 0.09f, FlashIntensity = 7f;

    CharacterController cc;
    float yaw, pitch, vy, bob, crouchT, exhaustedT, shake;
    int lastStep;
    Vector3 vel;
    AudioSource stepSrc, heartSrc;

    public static PlayerController Create(Transform root, Vector3 pos, float yaw)
    {
        var go = new GameObject("Player");
        go.transform.SetParent(root, false);
        go.transform.position = pos + Vector3.up * 0.05f;

        var cc = go.AddComponent<CharacterController>();
        cc.height = 1.8f; cc.radius = 0.32f; cc.center = new Vector3(0, 0.9f, 0);
        cc.stepOffset = 0.35f; cc.slopeLimit = 50f;

        var camGo = new GameObject("PlayerCamera");
        camGo.tag = "MainCamera";
        camGo.transform.SetParent(go.transform, false);
        camGo.transform.localPosition = new Vector3(0, 1.62f, 0);
        var cam = camGo.AddComponent<Camera>();
        cam.fieldOfView = 72f; cam.nearClipPlane = 0.04f; cam.farClipPlane = 80f;
        cam.clearFlags = CameraClearFlags.SolidColor; cam.backgroundColor = Color.black;
        camGo.AddComponent<AudioListener>();
        var cd = cam.GetUniversalAdditionalCameraData();
        cd.renderPostProcessing = true;
        cd.renderShadows = true;
        cd.antialiasing = AntialiasingMode.SubpixelMorphologicalAntiAliasing;
        cd.antialiasingQuality = AntialiasingQuality.High;

        var fl = new GameObject("Flashlight");
        fl.transform.SetParent(go.transform, false);
        var l = fl.AddComponent<Light>();
        l.type = LightType.Spot; l.range = 24f; l.spotAngle = 58f; l.innerSpotAngle = 20f;
        l.intensity = FlashIntensity; l.color = new Color(1f, 0.93f, 0.8f);
        l.shadows = LightShadows.Soft; l.shadowNearPlane = 0.1f;
        l.cookie = ProcTex.FlashlightCookie();

        var p = go.AddComponent<PlayerController>();
        p.cc = cc; p.Cam = cam; p.Flash = l; p.yaw = yaw;

        p.stepSrc = go.AddComponent<AudioSource>();
        p.stepSrc.spatialBlend = 0f;
        p.heartSrc = camGo.AddComponent<AudioSource>();
        p.heartSrc.clip = ProcAudio.Get("heartbeat"); p.heartSrc.loop = true; p.heartSrc.volume = 0f; p.heartSrc.Play();
        return p;
    }

    public void Shake(float amount) => shake = Mathf.Max(shake, amount);

    public void ForceLook(Vector3 worldPoint, float dt)
    {
        Vector3 d = worldPoint - Cam.transform.position;
        float ty = Mathf.Atan2(d.x, d.z) * Mathf.Rad2Deg;
        float tp = -Mathf.Atan2(d.y, new Vector2(d.x, d.z).magnitude) * Mathf.Rad2Deg;
        yaw = Mathf.LerpAngle(yaw, ty, dt * 12f);
        pitch = Mathf.LerpAngle(pitch, tp, dt * 12f);
    }

    void Update()
    {
        var kb = Keyboard.current; var ms = Mouse.current;
        var gm = GameManager.I;
        float dt = Time.deltaTime;
        bool active = kb != null && ms != null && gm && gm.state == GameManager.State.Playing && !Frozen && !gm.NoteOpen;

        // --- Umsehen ---
        if (active)
        {
            Vector2 md = ms.delta.ReadValue() * Sens;
            yaw += md.x;
            pitch = Mathf.Clamp(pitch - md.y, -85f, 85f);
        }
        transform.rotation = Quaternion.Euler(0, yaw, 0);

        // --- Bewegung ---
        Vector2 input = Vector2.zero;
        if (active)
        {
            input.x = (kb.dKey.isPressed ? 1 : 0) - (kb.aKey.isPressed ? 1 : 0);
            input.y = (kb.wKey.isPressed ? 1 : 0) - (kb.sKey.isPressed ? 1 : 0);
            if (input.sqrMagnitude > 1f) input.Normalize();
        }
        Crouching = active && (kb.leftCtrlKey.isPressed || kb.cKey.isPressed);
        bool wantSprint = active && kb.leftShiftKey.isPressed && input.y > 0.1f && !Crouching && exhaustedT <= 0f;
        Sprinting = wantSprint && Stamina > 0f && input.sqrMagnitude > 0.01f;
        float speed = Crouching ? CrouchSpeed : Sprinting ? SprintSpeed : WalkSpeed;

        if (Sprinting)
        {
            Stamina -= dt / 4.5f;
            if (Stamina <= 0f) { Stamina = 0f; exhaustedT = 2.5f; gm.ShowMessage("Du bist außer Atem ..."); }
        }
        else
        {
            exhaustedT -= dt;
            if (exhaustedT <= 0f) Stamina = Mathf.Min(1f, Stamina + dt / 7f);
        }

        Vector3 target = (transform.right * input.x + transform.forward * input.y) * speed;
        vel = Vector3.Lerp(vel, target, dt * 10f);
        vy = cc.isGrounded ? -2f : vy - 20f * dt;
        if (cc.enabled) cc.Move((vel + Vector3.up * vy) * dt);

        crouchT = Mathf.MoveTowards(crouchT, Crouching ? 1f : 0f, dt * 5f);
        cc.height = Mathf.Lerp(1.8f, 1.1f, crouchT);
        cc.center = new Vector3(0, cc.height / 2f, 0);
        float camH = Mathf.Lerp(1.62f, 0.95f, crouchT);

        // --- Kopfwippen & Schritte ---
        float spd = new Vector3(vel.x, 0, vel.z).magnitude;
        bob += dt * spd * 2.3f;
        float bobAmt = spd > 0.2f ? Mathf.Lerp(0.025f, 0.075f, spd / SprintSpeed) : 0f;
        int stepIdx = Mathf.FloorToInt(bob / Mathf.PI);
        if (stepIdx != lastStep && spd > 0.5f)
        {
            stepSrc.pitch = Random.Range(0.85f, 1.1f);
            stepSrc.PlayOneShot(ProcAudio.Get("step"), Crouching ? 0.12f : Sprinting ? 0.8f : 0.4f);
        }
        lastStep = stepIdx;

        NoiseRadius = spd < 0.4f ? 0f : Crouching ? 1.5f : Sprinting ? 15f : 5f;

        shake = Mathf.MoveTowards(shake, 0f, dt * 0.8f);
        Vector3 sh = Random.insideUnitSphere * shake;
        float breathe = Mathf.Sin(Time.time * 1.3f) * 0.25f * (1f + (1f - Stamina) * 3f);
        Cam.transform.localPosition = new Vector3(Mathf.Cos(bob) * bobAmt * 0.6f, camH - Mathf.Abs(Mathf.Sin(bob)) * bobAmt, 0) + sh * 0.3f;
        Cam.transform.localRotation = Quaternion.Euler(pitch + breathe + sh.x * 20f, sh.y * 20f, Mathf.Sin(bob) * bobAmt * 10f + sh.z * 15f);

        // --- Taschenlampe ---
        if (active && kb.fKey.wasPressedThisFrame)
        {
            if (Battery > 0f) Flash.enabled = !Flash.enabled;
            stepSrc.PlayOneShot(ProcAudio.Get("click"), 0.7f);
        }
        if (Flash.enabled)
        {
            Battery -= dt / 300f;
            if (Battery <= 0f) { Battery = 0f; Flash.enabled = false; gm.ShowMessage("Die Batterie ist leer."); }
        }
        float fk = 1f;
        if (Battery < 0.2f && Random.value < 0.08f) fk = Random.Range(0f, 0.4f);
        if (gm && gm.Fear > 0.55f && Random.value < (gm.Fear - 0.5f) * 0.25f) fk *= Random.Range(0f, 0.3f);
        Flash.intensity = FlashIntensity * Mathf.Lerp(0.55f, 1f, Mathf.Clamp01(Battery * 3f)) * fk;

        // --- Interaktion ---
        CurrentPrompt = null;
        if (active && Physics.SphereCast(Cam.transform.position, 0.12f, Cam.transform.forward, out var hit, 2.4f, ~0, QueryTriggerInteraction.Collide))
        {
            var it = hit.collider.GetComponentInParent<IInteractable>();
            if (it != null)
            {
                CurrentPrompt = it.Prompt(this);
                if (kb.eKey.wasPressedThisFrame && gm.NoteClosedFrame != Time.frameCount) it.Interact(this);
            }
        }

        // --- Herzschlag ---
        float fear = gm ? gm.Fear : 0f;
        heartSrc.volume = Mathf.Lerp(0f, 0.9f, fear) + (1f - Stamina) * 0.25f;
        heartSrc.pitch = 0.75f + fear * 0.9f + (1f - Stamina) * 0.3f;
    }

    void LateUpdate()
    {
        // Taschenlampe folgt der Kamera mit leichter Trägheit -> lebendige Schatten
        Vector3 tp = Cam.transform.TransformPoint(new Vector3(0.22f, -0.22f, 0.15f));
        Flash.transform.position = tp;
        Flash.transform.rotation = Quaternion.Slerp(Flash.transform.rotation, Cam.transform.rotation, Time.deltaTime * 11f);
    }
}
