using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Synthetisiert alle Sounds zur Laufzeit – keine Audiodateien nötig.
/// </summary>
public static class ProcAudio
{
    const int SR = 44100;
    const float TAU = Mathf.PI * 2f;
    static readonly Dictionary<string, AudioClip> cache = new Dictionary<string, AudioClip>();
    static System.Random rng = new System.Random(1337);

    static float N() => (float)(rng.NextDouble() * 2.0 - 1.0);

    class Biquad
    {
        float b0, b1, b2, a1, a2, x1, x2, y1, y2;
        public static Biquad LowPass(float f, float q) { var b = new Biquad(); b.SetLP(f, q); return b; }
        public static Biquad BandPass(float f, float q) { var b = new Biquad(); b.SetBP(f, q); return b; }
        public void SetLP(float f, float q)
        {
            float w = TAU * f / SR, al = Mathf.Sin(w) / (2 * q), cs = Mathf.Cos(w), a0 = 1 + al;
            b0 = (1 - cs) / 2 / a0; b1 = (1 - cs) / a0; b2 = b0; a1 = -2 * cs / a0; a2 = (1 - al) / a0;
        }
        public void SetBP(float f, float q)
        {
            float w = TAU * f / SR, al = Mathf.Sin(w) / (2 * q), cs = Mathf.Cos(w), a0 = 1 + al;
            b0 = al / a0; b1 = 0; b2 = -al / a0; a1 = -2 * cs / a0; a2 = (1 - al) / a0;
        }
        public float P(float x)
        {
            float y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
            x2 = x1; x1 = x; y2 = y1; y1 = y;
            return y;
        }
    }

    static void Normalize(float[] d, float peak)
    {
        float m = 0.0001f;
        foreach (var v in d) m = Mathf.Max(m, Mathf.Abs(v));
        float k = peak / m;
        for (int i = 0; i < d.Length; i++) d[i] *= k;
    }

    /// <summary>Überblendet das Ende in den Anfang -> nahtlose Schleife.</summary>
    static float[] Loopify(float[] d, int fade)
    {
        int len = d.Length - fade;
        var o = new float[len];
        for (int i = 0; i < len; i++)
        {
            if (i < fade) { float t = i / (float)fade; o[i] = d[i] * t + d[len + i] * (1 - t); }
            else o[i] = d[i];
        }
        return o;
    }

    static AudioClip Make(string name, float[] d)
    {
        var c = AudioClip.Create(name, d.Length, 1, SR, false);
        c.SetData(d, 0);
        return c;
    }

    public static AudioClip Get(string key)
    {
        if (cache.TryGetValue(key, out var c) && c) return c;
        c = Create(key);
        cache[key] = c;
        return c;
    }

    static AudioClip Create(string key)
    {
        switch (key)
        {
            case "drone": return Drone();
            case "heartbeat": return Heartbeat();
            case "step": return Step();
            case "monsterStep": return MonsterStep();
            case "scream": return Scream();
            case "stinger": return Stinger();
            case "growl": return Growl();
            case "buzz": return Buzz();
            case "pickup": return PickupSting();
            case "whisper": return Whisper();
            case "bang": return Bang();
            case "creak": return Creak();
            case "click": return Click();
            case "siren": return Siren();
        }
        Debug.LogWarning("Unbekannter Sound: " + key);
        return Make(key, new float[SR / 10]);
    }

    static AudioClip Drone()
    {
        int fade = SR * 2, n = SR * 12 + fade;
        var d = new float[n];
        var lp = Biquad.LowPass(300, 0.9f);
        var lp2 = Biquad.LowPass(1800, 3f);
        float ph = 0;
        for (int i = 0; i < n; i++)
        {
            float t = i / (float)SR;
            if (i % 64 == 0) lp.SetLP(220 + 180 * Mathf.Sin(TAU * 0.09f * t), 1.2f);
            float s = 0.35f * Mathf.Sin(TAU * 41f * t) + 0.3f * Mathf.Sin(TAU * 41.6f * t);
            s += 0.12f * Mathf.Sin(TAU * 82.3f * t + Mathf.Sin(TAU * 0.1f * t) * 2f);
            s += lp.P(N()) * 3.5f * (0.6f + 0.4f * Mathf.Sin(TAU * 0.07f * t));
            ph += TAU * (1240f + 30f * Mathf.Sin(TAU * 0.2f * t)) / SR;
            s += lp2.P(Mathf.Sin(ph) * N()) * 0.15f * Mathf.Max(0, Mathf.Sin(TAU * 0.05f * t));
            d[i] = s;
        }
        d = Loopify(d, fade);
        Normalize(d, 0.6f);
        return Make("drone", d);
    }

    static void Thump(float[] d, float t0, float amp, float f0)
    {
        float ph = 0;
        for (int i = (int)(t0 * SR); i < d.Length; i++)
        {
            float dt = i / (float)SR - t0;
            float env = Mathf.Exp(-dt * 16f) * (1 - Mathf.Exp(-dt * 400f));
            ph += TAU * (f0 * Mathf.Exp(-dt * 3f) + 30f) / SR;
            d[i] += Mathf.Sin(ph) * env * amp;
        }
    }

    static AudioClip Heartbeat()
    {
        var d = new float[SR];
        Thump(d, 0.02f, 1f, 45f);
        Thump(d, 0.3f, 0.7f, 40f);
        Normalize(d, 0.95f);
        return Make("heartbeat", d);
    }

    static AudioClip Step()
    {
        int n = (int)(SR * 0.3f); var d = new float[n];
        var lp = Biquad.LowPass(1100, 0.8f);
        for (int i = 0; i < n; i++)
        {
            float t = i / (float)SR;
            d[i] = lp.P(N()) * Mathf.Exp(-t * 35f) + Mathf.Sin(TAU * 85f * t) * Mathf.Exp(-t * 40f) * 0.5f;
        }
        Normalize(d, 0.8f);
        return Make("step", d);
    }

    static AudioClip MonsterStep()
    {
        int n = (int)(SR * 0.6f); var d = new float[n];
        var lp = Biquad.LowPass(450, 1f);
        var bp = Biquad.BandPass(2600, 4f);
        for (int i = 0; i < n; i++)
        {
            float t = i / (float)SR;
            float s = Mathf.Sin(TAU * (48f + 30f * Mathf.Exp(-t * 10f)) * t) * Mathf.Exp(-t * 10f);
            s += lp.P(N()) * 2f * Mathf.Exp(-t * 18f);
            s += bp.P(N()) * 1.5f * Mathf.Exp(-t * 60f);
            d[i] = s;
        }
        Normalize(d, 0.95f);
        return Make("monsterStep", d);
    }

    static AudioClip Scream()
    {
        int n = (int)(SR * 1.9f); var d = new float[n];
        var bp = Biquad.BandPass(2500, 1.5f);
        float[] det = { 1f, 1.031f, 0.968f, 1.497f, 2.01f };
        var ph = new float[det.Length];
        for (int i = 0; i < n; i++)
        {
            float t = i / (float)SR;
            float env = Smooth01(t / 0.03f) * (t < 1.3f ? 1f : Mathf.Exp(-(t - 1.3f) * 6f));
            float f0 = 520f * Mathf.Exp(-t * 0.5f) + 40f * Mathf.Sin(TAU * 7f * t);
            float s = 0;
            for (int k = 0; k < det.Length; k++)
            {
                ph[k] += f0 * det[k] / SR;
                ph[k] -= Mathf.Floor(ph[k]);
                s += (ph[k] * 2f - 1f) * (k > 2 ? 0.4f : 1f);
            }
            s = s * 0.35f + bp.P(N()) * 1.8f;
            d[i] = Tanh(s * 3f) * env;
        }
        Normalize(d, 1f);
        return Make("scream", d);
    }

    static AudioClip Stinger()
    {
        int n = (int)(SR * 2.6f); var d = new float[n];
        float[] fr = { 1180f, 1243f, 1311f, 1397f, 1475f, 98f };
        var ph = new float[fr.Length];
        var bp = Biquad.BandPass(1300, 0.8f);
        for (int i = 0; i < n; i++)
        {
            float t = i / (float)SR;
            float env = Mathf.Pow(Mathf.Clamp01(t / 2.2f), 2f) * (t > 2.2f ? Mathf.Exp(-(t - 2.2f) * 25f) : 1f);
            float s = 0;
            for (int k = 0; k < fr.Length - 1; k++)
            {
                ph[k] += fr[k] * (1f + 0.01f * Mathf.Sin(TAU * (5f + k) * t)) / SR;
                ph[k] -= Mathf.Floor(ph[k]);
                s += ph[k] * 2f - 1f;
            }
            s = bp.P(s) * env;
            float hit = Mathf.Sin(TAU * 55f * t) * Mathf.Exp(-t * 3f) * 1.5f + N() * Mathf.Exp(-t * 20f);
            d[i] = Tanh(s * 2f + hit);
        }
        Normalize(d, 0.9f);
        return Make("stinger", d);
    }

    static AudioClip Growl()
    {
        int fade = SR, n = SR * 4 + fade; var d = new float[n];
        var lp = Biquad.LowPass(320, 2f);
        var bp = Biquad.BandPass(700, 3f);
        for (int i = 0; i < n; i++)
        {
            float t = i / (float)SR;
            float breath = Mathf.Pow(0.5f + 0.5f * Mathf.Sin(TAU * 0.5f * t), 2f);
            float s = lp.P(N()) * 3f * breath;
            s += bp.P(N()) * 0.8f * breath;
            s += Mathf.Sin(TAU * 52f * t) * (0.5f + 0.5f * Mathf.Sin(TAU * 11f * t)) * 0.35f * breath;
            d[i] = Tanh(s * 1.5f);
        }
        d = Loopify(d, fade);
        Normalize(d, 0.8f);
        return Make("growl", d);
    }

    static AudioClip Buzz()
    {
        int n = SR * 2; var d = new float[n];
        var lp = Biquad.LowPass(2500, 0.7f);
        for (int i = 0; i < n; i++)
        {
            float t = i / (float)SR;
            float s = Mathf.Sign(Mathf.Sin(TAU * 100f * t)) * 0.15f + Mathf.Sin(TAU * 200f * t) * 0.3f + Mathf.Sin(TAU * 300f * t) * 0.1f;
            d[i] = lp.P(s + N() * 0.04f);
        }
        Normalize(d, 0.5f);
        return Make("buzz", d);
    }

    static AudioClip PickupSting()
    {
        int n = (int)(SR * 2.5f); var d = new float[n];
        float[] fr = { 98f, 103.8f, 146.8f, 207.6f, 1870f, 2911f };
        for (int i = 0; i < n; i++)
        {
            float t = i / (float)SR, s = 0;
            for (int k = 0; k < fr.Length; k++)
                s += Mathf.Sin(TAU * fr[k] * t) * Mathf.Exp(-t * (k < 4 ? 1.5f : 4f)) * (k < 4 ? 1f : 0.3f);
            d[i] = Tanh(s);
        }
        Normalize(d, 0.7f);
        return Make("pickup", d);
    }

    static AudioClip Whisper()
    {
        int n = SR * 3; var d = new float[n];
        var bp = Biquad.BandPass(1200, 6f);
        var bp2 = Biquad.BandPass(2800, 5f);
        float[] formants = { 700f, 1100f, 1500f, 2400f, 3100f };
        float sylEnd = 0, sylStart = 0;
        for (int i = 0; i < n; i++)
        {
            float t = i / (float)SR;
            if (t >= sylEnd)
            {
                sylStart = t; sylEnd = t + 0.1f + (float)rng.NextDouble() * 0.2f;
                float f = formants[rng.Next(formants.Length)];
                bp.SetBP(f, 6f); bp2.SetBP(f * 2.3f, 5f);
            }
            float st = (t - sylStart) / (sylEnd - sylStart);
            float env = Mathf.Sin(st * Mathf.PI) * Mathf.Sin(t / 3f * Mathf.PI);
            float x = N();
            d[i] = (bp.P(x) + bp2.P(x) * 0.6f) * env;
        }
        Normalize(d, 0.6f);
        return Make("whisper", d);
    }

    static AudioClip Bang()
    {
        int n = SR * 3; var d = new float[n];
        var lp = Biquad.LowPass(700, 1f);
        for (int i = 0; i < n; i++)
        {
            float t = i / (float)SR;
            d[i] = lp.P(N()) * 3f * Mathf.Exp(-t * 9f) + Mathf.Sin(TAU * 45f * t) * Mathf.Exp(-t * 3f);
        }
        int dl1 = (int)(0.083f * SR), dl2 = (int)(0.127f * SR);
        for (int i = 0; i < n; i++)
        {
            if (i >= dl1) d[i] += d[i - dl1] * 0.45f;
            if (i >= dl2) d[i] += d[i - dl2] * 0.35f;
        }
        Normalize(d, 0.9f);
        return Make("bang", d);
    }

    static AudioClip Creak()
    {
        int n = SR * 2; var d = new float[n];
        var bp = Biquad.BandPass(620, 18f);
        var bp2 = Biquad.BandPass(1450, 14f);
        float next = 0;
        for (int i = 0; i < n; i++)
        {
            float t = i / (float)SR;
            float x = 0;
            if (t >= next)
            {
                x = 1f;
                float rate = 25f + 25f * Mathf.Sin(TAU * 0.6f * t) + (float)rng.NextDouble() * 6f;
                next = t + 1f / rate;
            }
            float env = Mathf.Sin(t / 2f * Mathf.PI);
            d[i] = (bp.P(x) + bp2.P(x) * 0.5f) * env;
        }
        Normalize(d, 0.6f);
        return Make("creak", d);
    }

    static AudioClip Click()
    {
        int n = (int)(SR * 0.08f); var d = new float[n];
        var bp = Biquad.BandPass(3000, 2f);
        for (int i = 0; i < n; i++) { float t = i / (float)SR; d[i] = bp.P(N()) * Mathf.Exp(-t * 120f); }
        Normalize(d, 0.6f);
        return Make("click", d);
    }

    static AudioClip Siren()
    {
        int n = SR * 2; var d = new float[n];
        float ph = 0;
        for (int i = 0; i < n; i++)
        {
            float t = i / (float)SR;
            float f = 600f + 300f * (0.5f - 0.5f * Mathf.Cos(TAU * 0.5f * t));
            ph += f / SR; ph -= Mathf.Floor(ph);
            d[i] = Tanh(Mathf.Sin(ph * TAU) * 2f) * 0.6f;
        }
        Normalize(d, 0.6f);
        return Make("siren", d);
    }

    static float Smooth01(float x) { x = Mathf.Clamp01(x); return x * x * (3 - 2 * x); }
    static float Tanh(float x) { float e = Mathf.Exp(2f * Mathf.Clamp(x, -10f, 10f)); return (e - 1f) / (e + 1f); }
}
