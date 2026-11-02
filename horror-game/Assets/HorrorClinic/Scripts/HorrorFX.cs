using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

/// <summary>
/// Globales URP-Post-Processing. Alle Effekte werden vom Angstlevel gesteuert:
/// je näher Patient 17, desto stärker Verzerrung, Farbsäume, Korn und Vignette.
/// </summary>
public class HorrorFX : MonoBehaviour
{
    Bloom bloom; Vignette vig; FilmGrain grain; ChromaticAberration ca; LensDistortion lens;
    ColorAdjustments col; MotionBlur mb;

    public float Jumpscare;   // 0..1
    public float DeathTint;   // 0..1
    public float WhiteOut;    // 0..1
    float flash, glitch;
    Color flashColor = Color.red;

    static readonly Color BaseFilter = new Color(0.86f, 1f, 0.93f);

    public static HorrorFX Create(Transform root)
    {
        var go = new GameObject("PostFX");
        go.transform.SetParent(root, false);
        var vol = go.AddComponent<Volume>();
        vol.isGlobal = true; vol.priority = 100f; vol.weight = 1f;
        var p = ScriptableObject.CreateInstance<VolumeProfile>();
        vol.sharedProfile = p;
        var fx = go.AddComponent<HorrorFX>();

        fx.bloom = p.Add<Bloom>(true);
        fx.bloom.threshold.Override(0.85f);
        fx.bloom.intensity.Override(1.4f);
        fx.bloom.scatter.Override(0.75f);
        fx.bloom.tint.Override(new Color(1f, 0.92f, 0.85f));

        fx.vig = p.Add<Vignette>(true);
        fx.vig.intensity.Override(0.45f);
        fx.vig.smoothness.Override(0.55f);
        fx.vig.color.Override(Color.black);

        fx.grain = p.Add<FilmGrain>(true);
        fx.grain.type.Override(FilmGrainLookup.Medium4);
        fx.grain.intensity.Override(0.4f);
        fx.grain.response.Override(0.75f);

        fx.ca = p.Add<ChromaticAberration>(true);
        fx.ca.intensity.Override(0.15f);

        fx.lens = p.Add<LensDistortion>(true);
        fx.lens.intensity.Override(-0.1f);
        fx.lens.scale.Override(1f);

        fx.col = p.Add<ColorAdjustments>(true);
        fx.col.postExposure.Override(0.35f);
        fx.col.contrast.Override(28f);
        fx.col.saturation.Override(-35f);
        fx.col.colorFilter.Override(BaseFilter);

        var split = p.Add<SplitToning>(true);
        split.shadows.Override(new Color(0.25f, 0.45f, 0.45f));
        split.highlights.Override(new Color(0.75f, 0.65f, 0.5f));
        split.balance.Override(-20f);

        var tone = p.Add<Tonemapping>(true);
        tone.mode.Override(TonemappingMode.ACES);

        fx.mb = p.Add<MotionBlur>(true);
        fx.mb.intensity.Override(0.25f);
        fx.mb.clamp.Override(0.05f);

        // Atmosphäre
        RenderSettings.fog = true;
        RenderSettings.fogMode = FogMode.ExponentialSquared;
        RenderSettings.fogDensity = 0.065f;
        RenderSettings.fogColor = new Color(0.012f, 0.016f, 0.018f);
        RenderSettings.ambientMode = AmbientMode.Flat;
        RenderSettings.ambientLight = new Color(0.025f, 0.03f, 0.035f);
        RenderSettings.skybox = null;
        RenderSettings.reflectionIntensity = 0.3f;
        return fx;
    }

    public void Flash(Color c, float amount)
    {
        flashColor = c;
        flash = Mathf.Max(flash, amount);
    }

    void Update()
    {
        var gm = GameManager.I;
        float f = gm ? gm.Fear : 0f;
        float t = Time.time, dt = Time.deltaTime;

        if (Random.value < f * f * 0.03f) glitch = Random.Range(0.05f, 0.18f);
        glitch -= dt;
        float g = glitch > 0f ? 1f : 0f;
        flash = Mathf.MoveTowards(flash, 0f, dt * 1.5f);

        float pulse = 0.5f + 0.5f * Mathf.Sin(t * (2f + f * 6f));
        vig.intensity.value = Mathf.Clamp01(0.42f + 0.2f * f + 0.08f * f * pulse + Jumpscare * 0.2f + DeathTint * 0.2f);
        vig.color.value = Color.Lerp(Color.black, new Color(0.25f, 0f, 0f), Mathf.Max(f * 0.8f, DeathTint));
        ca.intensity.value = Mathf.Clamp01(0.12f + 0.55f * f + g * 0.6f + Jumpscare);
        lens.intensity.value = Mathf.Clamp(-0.1f - 0.25f * f * pulse - g * 0.35f + Jumpscare * 0.6f * Mathf.Sin(t * 40f), -1f, 1f);
        lens.scale.value = 1f + g * 0.08f;
        grain.intensity.value = Mathf.Clamp01(0.38f + 0.45f * f + g * 0.4f + Jumpscare);
        col.saturation.value = Mathf.Clamp(-35f - 30f * f + Jumpscare * 40f - DeathTint * 40f, -100f, 100f);
        col.contrast.value = 28f + 20f * f + Jumpscare * 30f;
        float red = Mathf.Max(flash, Mathf.Max(DeathTint, g * 0.35f));
        Color filter = Color.Lerp(BaseFilter, flashColor, Mathf.Clamp01(red));
        col.colorFilter.value = Color.Lerp(filter, Color.white, WhiteOut);
        col.postExposure.value = 0.35f + flash * 1.2f + Jumpscare * 0.8f - DeathTint * 1.5f + WhiteOut * 6f;
        bloom.intensity.value = 1.4f + WhiteOut * 6f + Jumpscare * 2f;
    }
}
