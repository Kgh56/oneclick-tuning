using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// "Patient 17" – patrouilliert, hört Geräusche, sieht Licht, jagt den Spieler.
/// Bewegt sich über das Zellraster (A*), braucht kein NavMesh.
/// </summary>
public class Monster : MonoBehaviour
{
    public enum State { Patrol, Investigate, Chase, Search, Jumpscare }
    public State state = State.Patrol;
    public bool SeenByPlayer { get; private set; }

    ClinicData data;
    PlayerController player;
    readonly List<Vector2Int> path = new List<Vector2Int>();
    int pathIdx;
    Vector3 goal, lastKnown;
    float repath, lostTimer, searchTimer, stepTimer, twitchTimer, idleTimer, animPhase, aggro;
    Transform head, legL, legR, armL, armR, body;
    Quaternion headTarget = Quaternion.identity;
    Light faceLight;
    Transform mouth;
    AudioSource growl, steps;
    Transform jumpCam;

    const float EyeHeight = 2.55f;

    public static Monster Create(Transform root, Vector3 pos, ClinicData d, PlayerController p)
    {
        var go = new GameObject("Patient17");
        go.transform.SetParent(root, false);
        go.transform.position = pos;
        var m = go.AddComponent<Monster>();
        m.data = d; m.player = p;
        m.BuildBody();

        m.growl = go.AddComponent<AudioSource>();
        m.growl.clip = ProcAudio.Get("growl"); m.growl.loop = true; m.growl.spatialBlend = 1f;
        m.growl.minDistance = 1.5f; m.growl.maxDistance = 18f; m.growl.rolloffMode = AudioRolloffMode.Linear;
        m.growl.volume = 0.6f; m.growl.Play();

        m.steps = go.AddComponent<AudioSource>();
        m.steps.spatialBlend = 1f; m.steps.minDistance = 2f; m.steps.maxDistance = 30f;
        m.steps.rolloffMode = AudioRolloffMode.Linear;
        return m;
    }

    void BuildBody()
    {
        var skin = ProcTex.Get("skin");
        var t = transform;
        body = new GameObject("Body").transform; body.SetParent(t, false);

        legL = Pivot(body, new Vector3(-0.15f, 1.45f, 0));
        legR = Pivot(body, new Vector3(0.15f, 1.45f, 0));
        ClinicBuilder.Part(PrimitiveType.Cylinder, legL, new Vector3(0, -0.72f, 0), new Vector3(0.12f, 0.74f, 0.12f), skin);
        ClinicBuilder.Part(PrimitiveType.Cylinder, legR, new Vector3(0, -0.72f, 0), new Vector3(0.12f, 0.74f, 0.12f), skin);

        ClinicBuilder.Part(PrimitiveType.Capsule, body, new Vector3(0, 1.85f, 0.03f), new Vector3(0.42f, 0.55f, 0.26f), skin, new Vector3(8, 0, 0));
        // Rippen
        for (int i = 0; i < 4; i++)
            ClinicBuilder.Part(PrimitiveType.Capsule, body, new Vector3(0, 1.75f + i * 0.1f, 0.12f), new Vector3(0.09f, 0.2f, 0.06f), skin, new Vector3(0, 0, 90));
        ClinicBuilder.Part(PrimitiveType.Cylinder, body, new Vector3(0, 2.38f, 0.08f), new Vector3(0.07f, 0.16f, 0.07f), skin, new Vector3(25, 0, 0));

        head = Pivot(body, new Vector3(0, 2.52f, 0.14f));
        ClinicBuilder.Part(PrimitiveType.Sphere, head, new Vector3(0, 0.12f, 0.02f), new Vector3(0.28f, 0.4f, 0.3f), skin);
        var eye = ProcTex.Get("eye");
        ClinicBuilder.Part(PrimitiveType.Sphere, head, new Vector3(-0.065f, 0.17f, 0.14f), Vector3.one * 0.045f, eye);
        ClinicBuilder.Part(PrimitiveType.Sphere, head, new Vector3(0.065f, 0.17f, 0.14f), Vector3.one * 0.045f, eye);
        mouth = ClinicBuilder.Part(PrimitiveType.Cube, head, new Vector3(0, 0.0f, 0.15f), new Vector3(0.13f, 0.05f, 0.03f), ProcTex.Get("mouth")).transform;
        var fl = new GameObject("EyeGlow").AddComponent<Light>();
        fl.transform.SetParent(head, false); fl.transform.localPosition = new Vector3(0, 0.15f, 0.35f);
        fl.type = LightType.Point; fl.color = new Color(1f, 0.85f, 0.75f); fl.range = 1.6f; fl.intensity = 0.6f;
        faceLight = fl;

        armL = Pivot(body, new Vector3(-0.3f, 2.2f, 0.02f));
        armR = Pivot(body, new Vector3(0.3f, 2.2f, 0.02f));
        foreach (var arm in new[] { armL, armR })
        {
            ClinicBuilder.Part(PrimitiveType.Cylinder, arm, new Vector3(0, -0.5f, 0), new Vector3(0.07f, 0.5f, 0.07f), skin);
            var fore = Pivot(arm, new Vector3(0, -1.0f, 0));
            fore.localRotation = Quaternion.Euler(-12, 0, 0);
            ClinicBuilder.Part(PrimitiveType.Cylinder, fore, new Vector3(0, -0.45f, 0), new Vector3(0.055f, 0.45f, 0.055f), skin);
            for (int f = -1; f <= 1; f++)
                ClinicBuilder.Part(PrimitiveType.Cylinder, fore, new Vector3(f * 0.03f, -1.05f, 0.02f), new Vector3(0.015f, 0.17f, 0.015f), skin, new Vector3(-10, 0, f * 8));
        }
    }

    static Transform Pivot(Transform parent, Vector3 lp)
    {
        var p = new GameObject("Pivot").transform;
        p.SetParent(parent, false); p.localPosition = lp;
        return p;
    }

    // ---------- Sinne ----------
    public void HearNoise(Vector3 pos, bool loud)
    {
        if (state == State.Jumpscare) return;
        lastKnown = pos;
        if (state != State.Chase)
        {
            state = State.Investigate;
            SetGoal(pos);
        }
        if (loud) aggro = Mathf.Min(aggro + 0.15f, 0.6f);
    }

    bool CanSeePlayer(float dist)
    {
        Vector3 eye = transform.position + Vector3.up * 2.0f; // unter den Türstürzen
        Vector3 target = player.transform.position + Vector3.up * (player.Crouching ? 0.8f : 1.4f);
        float range = player.FlashlightOn ? 20f : 9f;
        if (player.Crouching) range *= 0.55f;
        if (state == State.Chase) range = 26f;
        if (dist > range) return false;
        Vector3 to = target - eye;
        Vector3 flat = new Vector3(to.x, 0, to.z);
        float fov = state == State.Chase ? 180f : 80f;
        if (dist > 2.5f && Vector3.Angle(transform.forward, flat) > fov) return false;
        if (Physics.Raycast(eye, to.normalized, out var hit, to.magnitude + 0.5f, ~0, QueryTriggerInteraction.Ignore))
            return hit.collider.GetComponent<PlayerController>() != null;
        return false;
    }

    bool PlayerSeesMe()
    {
        var cam = player.Cam;
        Vector3 chest = transform.position + Vector3.up * 1.9f;
        Vector3 vp = cam.WorldToViewportPoint(chest);
        if (vp.z <= 0 || vp.x < -0.05f || vp.x > 1.05f || vp.y < -0.1f || vp.y > 1.1f) return false;
        Vector3 to = chest - cam.transform.position;
        if (Physics.Raycast(cam.transform.position, to.normalized, out var hit, to.magnitude - 0.3f, ~0, QueryTriggerInteraction.Ignore))
            return false;
        return to.magnitude < 22f;
    }

    // ---------- Navigation ----------
    void SetGoal(Vector3 world)
    {
        goal = world;
        path.Clear();
        path.AddRange(GridPath.Find(data, data.WorldToCell(transform.position), data.WorldToCell(world)));
        pathIdx = 0;
        repath = 0.35f;
    }

    void PickPatrolGoal()
    {
        var pc = data.WorldToCell(player.transform.position);
        Vector2Int best = data.WalkCells[Random.Range(0, data.WalkCells.Count)];
        // meistens in der Nähe des Spielers herumschleichen -> Spannung
        if (Random.value < 0.65f)
        {
            for (int i = 0; i < 30; i++)
            {
                var c = data.WalkCells[Random.Range(0, data.WalkCells.Count)];
                float d = Vector2Int.Distance(c, pc);
                if (d > 3 && d < 9) { best = c; break; }
            }
        }
        SetGoal(data.CellToWorld(best));
    }

    bool FollowPath(float speed, float dt)
    {
        if (pathIdx >= path.Count)
        {
            Vector3 g = new Vector3(goal.x, 0, goal.z);
            return MoveTowards(g, speed, dt) < 0.2f;
        }
        Vector3 target = data.CellToWorld(path[pathIdx]);
        if (pathIdx == path.Count - 1) target = new Vector3(goal.x, 0, goal.z);
        if (MoveTowards(target, speed, dt) < 0.25f) pathIdx++;
        return false;
    }

    float MoveTowards(Vector3 target, float speed, float dt)
    {
        Vector3 p = transform.position;
        Vector3 to = target - p; to.y = 0;
        float d = to.magnitude;
        if (d > 0.001f)
        {
            Vector3 step = to / d * Mathf.Min(d, speed * dt);
            transform.position = new Vector3(p.x + step.x, 0, p.z + step.z);
            var rot = Quaternion.LookRotation(to / d);
            transform.rotation = Quaternion.Slerp(transform.rotation, rot, dt * 6f);
        }
        animSpeed = speed;
        return d;
    }

    float animSpeed, duck;

    // ---------- Update ----------
    void Update()
    {
        var gm = GameManager.I;
        float dt = Time.deltaTime;
        if (state == State.Jumpscare) { JumpscareUpdate(dt); return; }
        if (!gm || gm.state != GameManager.State.Playing) { Animate(0f, dt); return; }

        animSpeed = 0f;
        float dist = Vector3.Distance(new Vector3(transform.position.x, 0, transform.position.z),
                                      new Vector3(player.transform.position.x, 0, player.transform.position.z));
        bool sees = CanSeePlayer(dist);
        SeenByPlayer = PlayerSeesMe();
        float mul = 1f + aggro + gm.FusesFound * 0.1f;

        if (sees)
        {
            if (state != State.Chase) gm.OnChaseStart();
            state = State.Chase;
            lastKnown = player.transform.position;
            lostTimer = 0f;
        }
        else if (dist < player.NoiseRadius && state != State.Chase)
        {
            HearNoise(player.transform.position, false);
        }

        switch (state)
        {
            case State.Patrol:
                if (idleTimer > 0) { idleTimer -= dt; break; }
                if (path.Count == 0 || FollowPath(1.4f * mul, dt))
                {
                    idleTimer = Random.Range(1f, 4f);
                    PickPatrolGoal();
                }
                break;

            case State.Investigate:
                if (FollowPath(2.5f * mul, dt))
                {
                    state = State.Search; searchTimer = 10f; idleTimer = 1.5f; path.Clear();
                }
                break;

            case State.Chase:
                if (!sees)
                {
                    lostTimer += dt;
                    // die ersten Sekunden "ahnt" er, wohin du läufst
                    if (lostTimer < 2.2f) lastKnown = player.transform.position;
                    if (lostTimer > 6f) { state = State.Search; searchTimer = 12f; SetGoal(lastKnown); break; }
                }
                repath -= dt;
                if (sees && dist < 4.5f)
                {
                    MoveTowards(player.transform.position, 4.1f * mul, dt);
                    path.Clear();
                }
                else
                {
                    if (repath <= 0f || path.Count == 0) SetGoal(lastKnown);
                    FollowPath(4.1f * mul, dt);
                }
                break;

            case State.Search:
                searchTimer -= dt;
                if (idleTimer > 0) { idleTimer -= dt; break; }
                if (path.Count == 0 || FollowPath(2f * mul, dt))
                {
                    idleTimer = Random.Range(0.5f, 2f);
                    var lc = data.WorldToCell(lastKnown);
                    var c = lc + new Vector2Int(Random.Range(-3, 4), Random.Range(-3, 4));
                    SetGoal(data.CellToWorld(data.NearestWalk(c)));
                }
                if (searchTimer <= 0f) { state = State.Patrol; path.Clear(); }
                break;
        }

        // Angst-Meldung an den GameManager
        float prox = Mathf.Clamp01(1f - dist / 18f);
        float fear = prox * 0.65f;
        if (SeenByPlayer) fear = Mathf.Max(fear, 0.55f + prox * 0.45f);
        if (state == State.Chase) fear = Mathf.Max(fear, 0.6f + prox * 0.4f);
        gm.ReportFear(fear);

        growl.volume = state == State.Chase ? 1f : 0.55f;
        growl.pitch = state == State.Chase ? 1.15f : 0.9f;

        Animate(animSpeed, dt);

        if (dist < 1.25f) gm.PlayerCaught(this);
    }

    void Animate(float speed, float dt)
    {
        animPhase += dt * (1.5f + speed * 1.6f);
        float swing = Mathf.Clamp01(speed / 2f) * 28f;
        legL.localRotation = Quaternion.Euler(Mathf.Sin(animPhase) * swing, 0, 0);
        legR.localRotation = Quaternion.Euler(-Mathf.Sin(animPhase) * swing, 0, 0);
        float armSwing = state == State.Chase ? 55f : 12f;
        armL.localRotation = Quaternion.Euler(-Mathf.Sin(animPhase) * armSwing * Mathf.Clamp01(speed) - (state == State.Chase ? 40f : 0f), 0, 6f);
        armR.localRotation = Quaternion.Euler(Mathf.Sin(animPhase) * armSwing * Mathf.Clamp01(speed) - (state == State.Chase ? 40f : 0f), 0, -6f);
        // in Durchgängen bückt er sich unter dem Sturz hindurch
        var cell = data.WorldToCell(transform.position);
        bool inDoor = data.InBounds(cell.x, cell.y) && data.Map[cell.y][cell.x] == 'D';
        duck = Mathf.MoveTowards(duck, inDoor ? 1f : 0f, dt * 2.5f);
        body.localPosition = new Vector3(0, Mathf.Abs(Mathf.Sin(animPhase)) * 0.06f * Mathf.Clamp01(speed) - duck * 0.55f, 0);
        body.localRotation = Quaternion.Euler((state == State.Chase ? 18f : 6f) + duck * 22f, 0, Mathf.Sin(animPhase * 0.5f) * 4f);

        // ruckartige Kopfzuckungen
        twitchTimer -= dt;
        if (twitchTimer <= 0f)
        {
            bool fast = state == State.Chase || SeenByPlayer;
            twitchTimer = fast ? Random.Range(0.05f, 0.4f) : Random.Range(0.4f, 2.5f);
            headTarget = Random.value < 0.6f
                ? Quaternion.Euler(Random.Range(-20f, 25f), Random.Range(-35f, 35f), Random.Range(-60f, 60f))
                : Quaternion.identity;
        }
        head.localRotation = Quaternion.Slerp(head.localRotation, headTarget, dt * 30f);

        if (speed > 0.1f)
        {
            stepTimer -= dt * speed;
            if (stepTimer <= 0f)
            {
                stepTimer = 1.1f;
                steps.pitch = Random.Range(0.8f, 1.05f);
                steps.PlayOneShot(ProcAudio.Get("monsterStep"), state == State.Chase ? 1f : 0.7f);
                if (state == State.Chase && player) player.Shake(0.03f);
            }
        }
    }

    // ---------- Jumpscare ----------
    public void BeginJumpscare(Transform cam)
    {
        state = State.Jumpscare;
        jumpCam = cam;
        faceLight.color = new Color(1f, 0.15f, 0.1f);
        faceLight.range = 3f; faceLight.intensity = 5f;
        growl.volume = 1f; growl.pitch = 0.7f;
    }

    void JumpscareUpdate(float dt)
    {
        if (!jumpCam) return;
        Vector3 fwd = jumpCam.forward; fwd.y = 0; fwd.Normalize();
        Vector3 p = jumpCam.position + fwd * 0.75f;
        transform.position = new Vector3(p.x, jumpCam.position.y - EyeHeight + 0.05f, p.z);
        transform.rotation = Quaternion.LookRotation(-fwd);
        head.localRotation = Quaternion.Euler(Random.Range(-15f, 15f), Random.Range(-15f, 15f), Random.Range(-35f, 35f));
        mouth.localScale = new Vector3(0.13f, Mathf.Lerp(mouth.localScale.y, 0.2f, dt * 8f), 0.03f);
        armL.localRotation = Quaternion.Euler(-100f + Random.Range(-10f, 10f), 0, 25f);
        armR.localRotation = Quaternion.Euler(-100f + Random.Range(-10f, 10f), 0, -25f);
    }
}
