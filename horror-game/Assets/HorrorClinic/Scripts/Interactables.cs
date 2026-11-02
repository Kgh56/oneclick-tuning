using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public interface IInteractable
{
    string Prompt(PlayerController p);
    void Interact(PlayerController p);
}

/// <summary>Neonröhre: steht, flackert oder ist tot. Flackert stark, wenn das Monster in der Nähe ist.</summary>
public class FlickerLight : MonoBehaviour
{
    public static readonly List<FlickerLight> All = new List<FlickerLight>();
    public enum Mode { Steady, Flicker, Dead }

    public Mode mode;
    Light l; Material panel; Color emis; float baseI;
    float next, surge; bool on = true; bool alarm;
    AudioSource buzz;

    void OnEnable() => All.Add(this);
    void OnDisable() => All.Remove(this);

    public void Init(Light light, Renderer panelRenderer, Mode m)
    {
        l = light; mode = m; baseI = light.intensity;
        panel = panelRenderer.material;
        emis = light.color * 2.2f;
        if (m == Mode.Flicker)
        {
            buzz = gameObject.AddComponent<AudioSource>();
            buzz.clip = ProcAudio.Get("buzz");
            buzz.loop = true; buzz.spatialBlend = 1f; buzz.volume = 0.18f;
            buzz.minDistance = 1f; buzz.maxDistance = 9f; buzz.rolloffMode = AudioRolloffMode.Linear;
            buzz.Play();
        }
    }

    public static void SurgeAll(float dur)
    {
        foreach (var f in All) f.surge = dur * Random.Range(0.8f, 1.2f);
    }

    public static void AlarmAll()
    {
        foreach (var f in All)
        {
            f.alarm = true;
            if (f.mode == Mode.Dead && Random.value < 0.5f) f.mode = Mode.Flicker;
            f.l.color = new Color(1f, 0.08f, 0.04f);
            f.emis = new Color(3f, 0.1f, 0.05f);
        }
    }

    void Update()
    {
        if (!l) return;
        float k = 1f;
        if (mode == Mode.Dead) k = 0f;
        else if (mode == Mode.Flicker)
        {
            if (Time.time > next)
            {
                on = Random.value > 0.35f;
                next = Time.time + (on ? Random.Range(0.05f, 1.6f) : Random.Range(0.03f, 0.25f));
            }
            k = on ? 1f : 0.04f;
        }

        var gm = GameManager.I;
        if (gm && gm.Monster && k > 0f)
        {
            float d = Vector3.Distance(gm.Monster.transform.position, transform.position);
            if (d < 8f && Random.value < (1f - d / 8f) * 0.45f) k *= Random.Range(0f, 0.25f);
        }
        if (surge > 0f)
        {
            surge -= Time.deltaTime;
            if (surge > 0.25f) k = Random.value < 0.12f ? 1.5f : 0f;
        }
        if (alarm) k *= 0.55f + 0.45f * Mathf.Sin(Time.time * 5f);

        l.intensity = baseI * k;
        l.enabled = k > 0.01f;
        panel.SetColor("_EmissionColor", emis * k);
        if (buzz) buzz.volume = 0.18f * (k > 0.1f ? 1f : 0.2f);
    }
}

public class Pickup : MonoBehaviour, IInteractable
{
    public enum Kind { Fuse, Battery }
    public Kind kind;
    public Transform visual;
    float seed;

    void Start() => seed = Random.value * 10f;

    public string Prompt(PlayerController p) => kind == Kind.Fuse ? "Sicherung nehmen" : "Batterie nehmen";

    public void Interact(PlayerController p)
    {
        if (kind == Kind.Fuse)
        {
            p.Fuses++;
            GameManager.I.OnFusePicked();
        }
        else
        {
            p.Battery = Mathf.Min(1f, p.Battery + 0.5f);
            GameManager.I.ShowMessage("Batterie eingelegt.");
            GameManager.I.Play2D(ProcAudio.Get("click"), 0.8f);
        }
        Destroy(gameObject);
    }

    void Update()
    {
        if (visual) visual.localRotation = Quaternion.Euler(0, (Time.time + seed) * 40f, kind == Kind.Fuse ? 90 : 0);
    }
}

public class NoteItem : MonoBehaviour, IInteractable
{
    public string Title, Body;
    public string Prompt(PlayerController p) => "Lesen";
    public void Interact(PlayerController p) => GameManager.I.OpenNote(Title, Body);
}

/// <summary>Notstromtor + Sicherungskasten. 3 Sicherungen -> Tor öffnet sich langsam -> Flucht.</summary>
public class ExitGate : MonoBehaviour, IInteractable
{
    public const int Needed = 3;
    public int Inserted;
    public bool Open, Opening;
    Transform door; Material[] lamps; Light alarmLight; GameObject glow;

    public static void Build(Transform parent, Vector3 cell, Vector3 wallDir)
    {
        if (wallDir == Vector3.zero) wallDir = Vector3.right;
        var root = new GameObject("ExitGate");
        root.transform.SetParent(parent, false);
        root.transform.position = cell + wallDir * (ClinicData.S / 2f);
        root.transform.rotation = Quaternion.LookRotation(-wallDir);
        var g = root.AddComponent<ExitGate>();
        var t = root.transform;

        g.glow = ClinicBuilder.Part(PrimitiveType.Quad, t, new Vector3(0, 1.4f, 0.02f), new Vector3(2.1f, 2.7f, 1f), ProcTex.Get("exitglow"), new Vector3(0, 180, 0));
        g.glow.SetActive(false);

        var doorGo = GameObject.CreatePrimitive(PrimitiveType.Cube);
        doorGo.name = "Door";
        doorGo.transform.SetParent(t, false);
        doorGo.transform.localPosition = new Vector3(0, 1.4f, 0.12f);
        doorGo.transform.localScale = new Vector3(2.2f, 2.8f, 0.2f);
        doorGo.GetComponent<Renderer>().sharedMaterial = ProcTex.Get("gate");
        g.door = doorGo.transform;
        ClinicBuilder.Part(PrimitiveType.Cube, g.door, new Vector3(0, 0.45f, 0.6f), new Vector3(1.01f, 0.06f, 0.4f), ProcTex.Get("hazard"));
        ClinicBuilder.Part(PrimitiveType.Cube, g.door, new Vector3(0, -0.45f, 0.6f), new Vector3(1.01f, 0.06f, 0.4f), ProcTex.Get("hazard"));

        var box = GameObject.CreatePrimitive(PrimitiveType.Cube);
        box.name = "FuseBox";
        box.transform.SetParent(t, false);
        box.transform.localPosition = new Vector3(1.75f, 1.3f, 0.12f);
        box.transform.localScale = new Vector3(0.6f, 0.8f, 0.2f);
        box.GetComponent<Renderer>().sharedMaterial = ProcTex.Get("metal");

        g.lamps = new Material[Needed];
        for (int i = 0; i < Needed; i++)
        {
            var lamp = ClinicBuilder.Part(PrimitiveType.Cube, t, new Vector3(1.6f + 0.15f * i, 1.5f, 0.24f), Vector3.one * 0.08f, ProcTex.Get("panel"));
            g.lamps[i] = lamp.GetComponent<Renderer>().material;
            ProcTex.SetEmission(g.lamps[i], new Color(2f, 0.05f, 0.02f));
        }

        var lg = new GameObject("AlarmLight");
        lg.transform.SetParent(t, false);
        lg.transform.localPosition = new Vector3(0, 3.0f, 0.8f);
        g.alarmLight = lg.AddComponent<Light>();
        g.alarmLight.type = LightType.Point; g.alarmLight.range = 7f; g.alarmLight.intensity = 1.6f;
        g.alarmLight.color = new Color(1f, 0.1f, 0.05f);
        g.alarmLight.shadows = LightShadows.Soft;
    }

    public string Prompt(PlayerController p)
    {
        if (Open) return "FLIEHEN";
        if (Opening) return "Das Tor öffnet sich ... halte durch!";
        if (p.Fuses > 0) return $"Sicherung einsetzen ({Inserted}/{Needed})";
        return $"Sicherungskasten – es fehlen {Needed - Inserted} Sicherungen";
    }

    public void Interact(PlayerController p)
    {
        if (Open) { GameManager.I.Win(); return; }
        if (Opening || p.Fuses <= 0) return;
        while (p.Fuses > 0 && Inserted < Needed)
        {
            p.Fuses--;
            ProcTex.SetEmission(lamps[Inserted], new Color(0.1f, 3f, 0.3f));
            Inserted++;
        }
        GameManager.I.Play2D(ProcAudio.Get("bang"), 0.7f);
        FlickerLight.SurgeAll(1.2f);
        if (Inserted >= Needed) StartCoroutine(OpenRoutine());
        else
        {
            GameManager.I.ShowMessage($"Strom fließt ... {Needed - Inserted} fehlen noch. Er hat das gehört.");
            GameManager.I.Monster.HearNoise(transform.position, true);
        }
    }

    IEnumerator OpenRoutine()
    {
        Opening = true;
        GameManager.I.OnGateOpening(this);
        var siren = gameObject.AddComponent<AudioSource>();
        siren.clip = ProcAudio.Get("siren"); siren.loop = true; siren.volume = 0.5f; siren.spatialBlend = 0.6f;
        siren.maxDistance = 60f; siren.Play();
        glow.SetActive(true);
        Vector3 start = door.localPosition, end = start + Vector3.up * 2.75f;
        const float dur = 9f;
        for (float t = 0; t < dur; t += Time.deltaTime)
        {
            float k = t / dur;
            door.localPosition = Vector3.Lerp(start, end, k * k);
            if (Random.value < 0.05f) GameManager.I.Player.Shake(0.05f);
            yield return null;
        }
        door.localPosition = end;
        door.GetComponent<Collider>().enabled = false;
        Open = true;
        GameManager.I.ShowMessage("DAS TOR IST OFFEN – LAUF!");
    }

    void Update()
    {
        if (alarmLight) alarmLight.intensity = (Opening ? 4f : 1.6f) * (0.6f + 0.4f * Mathf.Sin(Time.time * (Opening ? 9f : 2f)));
    }
}
