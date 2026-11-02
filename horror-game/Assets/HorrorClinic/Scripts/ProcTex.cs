using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Erzeugt alle Texturen und Materialien zur Laufzeit (Fliesen, Wände, Blut, Haut ...).
/// Dadurch braucht das Projekt keine einzige Bilddatei.
/// </summary>
public static class ProcTex
{
    static readonly Dictionary<string, Material> cache = new Dictionary<string, Material>();
    static Shader lit;

    // ---------- Rauschen ----------
    static float Hash(int x, int y, int seed)
    {
        unchecked
        {
            int h = x * 374761393 + y * 668265263 + seed * 144269504;
            h = (h ^ (h >> 13)) * 1274126177;
            h ^= h >> 16;
            return (h & 0x7fffffff) / (float)0x7fffffff;
        }
    }

    static int Mod(int a, int m) { int r = a % m; return r < 0 ? r + m : r; }

    static float ValueNoise(float x, float y, int period, int seed)
    {
        int xi = Mathf.FloorToInt(x), yi = Mathf.FloorToInt(y);
        float xf = x - xi, yf = y - yi;
        float u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
        int x0 = Mod(xi, period), x1 = Mod(xi + 1, period), y0 = Mod(yi, period), y1 = Mod(yi + 1, period);
        float a = Hash(x0, y0, seed), b = Hash(x1, y0, seed), c = Hash(x0, y1, seed), d = Hash(x1, y1, seed);
        return Mathf.Lerp(Mathf.Lerp(a, b, u), Mathf.Lerp(c, d, u), v);
    }

    /// <summary>Kachelbares fBm-Rauschen, u/v in [0,1).</summary>
    public static float Fbm(float u, float v, int freq, int octaves, int seed)
    {
        float sum = 0, amp = 0.5f, norm = 0;
        int f = freq;
        for (int i = 0; i < octaves; i++)
        {
            sum += amp * ValueNoise(u * f, v * f, f, seed + i * 31);
            norm += amp; amp *= 0.5f; f *= 2;
        }
        return sum / norm;
    }

    static float Smooth(float a, float b, float x) { float t = Mathf.Clamp01((x - a) / (b - a)); return t * t * (3 - 2 * t); }

    // ---------- Textur-Helfer ----------
    static Texture2D NewTex(int s, bool linear, bool clamp = false)
    {
        var t = new Texture2D(s, s, TextureFormat.RGBA32, true, linear);
        t.wrapMode = clamp ? TextureWrapMode.Clamp : TextureWrapMode.Repeat;
        t.filterMode = FilterMode.Trilinear;
        t.anisoLevel = 8;
        return t;
    }

    static Texture2D Finish(Texture2D t, Color[] c) { t.SetPixels(c); t.Apply(true, false); return t; }

    static Texture2D NormalFromHeight(float[] h, int s, float strength)
    {
        var c = new Color[s * s];
        for (int y = 0; y < s; y++)
            for (int x = 0; x < s; x++)
            {
                float dx = h[y * s + (x + 1) % s] - h[y * s + (x - 1 + s) % s];
                float dy = h[((y + 1) % s) * s + x] - h[((y - 1 + s) % s) * s + x];
                var n = new Vector3(-dx * strength, -dy * strength, 1f).normalized;
                c[y * s + x] = new Color(n.x * 0.5f + 0.5f, n.y * 0.5f + 0.5f, n.z * 0.5f + 0.5f, 1f);
            }
        return Finish(NewTex(s, true), c);
    }

    // ---------- Materialien ----------
    public static Material Get(string key)
    {
        if (cache.TryGetValue(key, out var m) && m) return m;
        m = Create(key);
        cache[key] = m;
        return m;
    }

    public static Material Lit(Texture2D albedo, Texture2D normal, Color tint, float smooth, float metallic = 0f, bool smoothFromAlpha = false)
    {
        if (!lit) lit = Shader.Find("Universal Render Pipeline/Lit");
        if (!lit) Debug.LogError("URP Lit Shader nicht gefunden! Projekt muss mit dem 'Universal 3D' Template erstellt sein.");
        var m = new Material(lit);
        if (albedo) m.SetTexture("_BaseMap", albedo);
        m.SetColor("_BaseColor", tint);
        if (normal)
        {
            m.SetTexture("_BumpMap", normal);
            m.SetFloat("_BumpScale", 1f);
            m.EnableKeyword("_NORMALMAP");
        }
        m.SetFloat("_Smoothness", smooth);
        m.SetFloat("_Metallic", metallic);
        if (smoothFromAlpha)
        {
            m.SetFloat("_SmoothnessTextureChannel", 1f);
            m.EnableKeyword("_SMOOTHNESS_TEXTURE_ALBEDO_CHANNEL_A");
        }
        return m;
    }

    public static void SetEmission(Material m, Color c)
    {
        m.EnableKeyword("_EMISSION");
        m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.RealtimeEmissive;
        m.SetColor("_EmissionColor", c);
    }

    static void AlphaClip(Material m, float cutoff)
    {
        m.SetFloat("_AlphaClip", 1f);
        m.SetFloat("_Cutoff", cutoff);
        m.EnableKeyword("_ALPHATEST_ON");
        m.renderQueue = 2450;
    }

    static Material Create(string key)
    {
        Texture2D a, n;
        Material m;
        switch (key)
        {
            case "floor": FloorTex(out a, out n); return Lit(a, n, Color.white, 0.75f, 0f, true);
            case "wall": WallTex(out a, out n); return Lit(a, n, Color.white, 0.35f, 0f, true);
            case "ceiling": CeilingTex(out a, out n); return Lit(a, n, Color.white, 0.1f);
            case "metal": MetalTex(out a, out n); return Lit(a, n, Color.white, 0.55f, 0.75f, true);
            case "gate": MetalTex(out a, out n); return Lit(a, n, new Color(0.45f, 0.42f, 0.38f), 0.5f, 0.8f, true);
            case "sheet": SheetTex(out a, out n); return Lit(a, n, Color.white, 0.15f);
            case "skin": SkinTex(out a, out n); return Lit(a, n, Color.white, 0.8f, 0f, true);
            case "paper":
                m = Lit(PaperTex(), null, Color.white, 0.05f);
                SetEmission(m, new Color(0.07f, 0.065f, 0.05f));
                return m;
            case "blood":
                m = Lit(BloodTex(), null, Color.white, 0.85f);
                AlphaClip(m, 0.5f);
                return m;
            case "decalPaper":
                m = Lit(PaperTex(), null, new Color(0.7f, 0.68f, 0.6f), 0.05f);
                return m;
            case "leather": return Lit(null, null, new Color(0.06f, 0.05f, 0.04f), 0.45f);
            case "black": return Lit(null, null, new Color(0.01f, 0.01f, 0.01f), 0.2f);
            case "bloodbag": return Lit(null, null, new Color(0.25f, 0.0f, 0.0f), 0.95f);
            case "eye":
                m = Lit(null, null, Color.white, 0.9f);
                SetEmission(m, new Color(6f, 5.5f, 4.5f));
                return m;
            case "mouth":
                m = Lit(null, null, new Color(0.05f, 0f, 0f), 0.9f);
                SetEmission(m, new Color(0.6f, 0.02f, 0.01f));
                return m;
            case "fuse":
                m = Lit(null, null, new Color(0.9f, 0.5f, 0.1f), 0.6f, 0.5f);
                SetEmission(m, new Color(2.5f, 0.9f, 0.1f));
                return m;
            case "battery":
                m = Lit(null, null, new Color(0.2f, 0.5f, 0.6f), 0.6f, 0.5f);
                SetEmission(m, new Color(0.2f, 1.2f, 1.6f));
                return m;
            case "panel":
                m = Lit(null, null, new Color(0.8f, 0.85f, 0.8f), 0.3f);
                SetEmission(m, Color.black);
                return m;
            case "exitglow":
                m = Lit(null, null, Color.white, 0f);
                SetEmission(m, new Color(8f, 8f, 7f));
                return m;
            case "hazard":
                m = Lit(null, null, new Color(0.8f, 0.6f, 0.05f), 0.4f);
                return m;
        }
        Debug.LogWarning("Unbekanntes Material: " + key);
        return Lit(null, null, Color.magenta, 0.5f);
    }

    // ---------- Einzelne Texturen ----------
    static void FloorTex(out Texture2D alb, out Texture2D nrm)
    {
        int s = 512; var c = new Color[s * s]; var h = new float[s * s];
        int tiles = 4; float tsz = s / (float)tiles;
        for (int y = 0; y < s; y++)
            for (int x = 0; x < s; x++)
            {
                float u = x / (float)s, v = y / (float)s;
                int tx = (int)(x / tsz), ty = (int)(y / tsz);
                float lx = x - tx * tsz, ly = y - ty * tsz;
                bool grout = lx < 3 || ly < 3 || lx > tsz - 3 || ly > tsz - 3;
                float tv = Hash(tx, ty, 7);
                float fine = Fbm(u, v, 32, 3, 12);
                float dirt = Fbm(u, v, 4, 5, 11);
                Color col = Color.Lerp(new Color(0.62f, 0.66f, 0.62f), new Color(0.48f, 0.53f, 0.5f), tv) * (0.85f + 0.3f * fine);
                if (Hash(tx, ty, 9) > 0.88f) col *= 0.65f;
                if (grout) col = new Color(0.16f, 0.15f, 0.13f);
                float grime = Smooth(0.45f, 0.75f, dirt);
                col = Color.Lerp(col, new Color(0.14f, 0.11f, 0.08f), grime * 0.8f);
                float stain = Fbm(u, v, 3, 4, 99);
                float blood = Mathf.Clamp01((stain - 0.63f) * 8f);
                col = Color.Lerp(col, new Color(0.2f, 0.02f, 0.015f), blood * 0.85f);
                col.a = Mathf.Clamp01(0.85f - grime * 0.6f + blood * 0.3f) * (grout ? 0.2f : 1f);
                c[y * s + x] = col;
                h[y * s + x] = grout ? 0f : 1f - fine * 0.15f;
            }
        alb = Finish(NewTex(s, false), c);
        nrm = NormalFromHeight(h, s, 3f);
    }

    static void WallTex(out Texture2D alb, out Texture2D nrm)
    {
        int s = 512; var c = new Color[s * s]; var h = new float[s * s];
        const float line = 0.38f;
        for (int y = 0; y < s; y++)
            for (int x = 0; x < s; x++)
            {
                float u = x / (float)s, v = y / (float)s;
                float n = Fbm(u, v, 8, 4, 21);
                Color col = v < line ? new Color(0.28f, 0.38f, 0.32f) : new Color(0.64f, 0.62f, 0.54f);
                if (Mathf.Abs(v - line) < 0.012f) col = new Color(0.12f, 0.17f, 0.14f);
                col *= 0.85f + 0.3f * n;
                float height = 1f - n * 0.1f;
                float peel = Fbm(u, v, 5, 4, 33);
                if (peel > 0.64f)
                {
                    col = new Color(0.4f, 0.39f, 0.37f) * (0.75f + 0.45f * Fbm(u, v, 32, 2, 34));
                    height = 0.6f;
                }
                else if (peel > 0.62f) { col *= 0.5f; height = 0.8f; }
                float drip = Fbm(u, v * 0.08f, 16, 3, 44);
                float dm = Smooth(0.55f, 0.8f, drip) * Smooth(0.1f, 1f, v);
                col = Color.Lerp(col, new Color(0.18f, 0.13f, 0.08f), dm * 0.75f);
                col = Color.Lerp(col, new Color(0.08f, 0.07f, 0.05f), Mathf.Pow(1f - v, 6f) * 0.85f);
                col = Color.Lerp(col, new Color(0.09f, 0.11f, 0.06f), Smooth(0.82f, 1f, v) * Fbm(u, v, 6, 4, 55) * 1.3f);
                col.a = 0.25f + dm * 0.5f;
                c[y * s + x] = col; h[y * s + x] = height;
            }
        alb = Finish(NewTex(s, false), c);
        nrm = NormalFromHeight(h, s, 2.5f);
    }

    static void CeilingTex(out Texture2D alb, out Texture2D nrm)
    {
        int s = 512; var c = new Color[s * s]; var h = new float[s * s];
        int panels = 2; float psz = s / (float)panels;
        for (int y = 0; y < s; y++)
            for (int x = 0; x < s; x++)
            {
                float u = x / (float)s, v = y / (float)s;
                int px = (int)(x / psz), py = (int)(y / psz);
                float lx = x - px * psz, ly = y - py * psz;
                bool grid = lx < 4 || ly < 4 || lx > psz - 4 || ly > psz - 4;
                float pores = Fbm(u, v, 64, 2, 70);
                Color col = new Color(0.55f, 0.55f, 0.52f) * (0.85f + 0.25f * pores);
                float stain = Fbm(u, v, 3, 4, 61);
                if (stain > 0.58f) col = Color.Lerp(col, new Color(0.35f, 0.27f, 0.15f), Mathf.Clamp01((stain - 0.58f) * 6f));
                if (Mathf.Abs(stain - 0.58f) < 0.01f) col *= 0.55f;
                if (Hash(px, py, 5) > 0.8f) col = new Color(0.01f, 0.01f, 0.01f);
                if (grid) col = new Color(0.25f, 0.25f, 0.24f);
                c[y * s + x] = col;
                h[y * s + x] = grid ? 0f : 0.9f + pores * 0.1f;
            }
        alb = Finish(NewTex(s, false), c);
        nrm = NormalFromHeight(h, s, 2f);
    }

    static void MetalTex(out Texture2D alb, out Texture2D nrm)
    {
        int s = 256; var c = new Color[s * s]; var h = new float[s * s];
        for (int y = 0; y < s; y++)
            for (int x = 0; x < s; x++)
            {
                float u = x / (float)s, v = y / (float)s;
                float brushed = Fbm(u, v * 0.05f, 64, 2, 80);
                float rust = Smooth(0.5f, 0.75f, Fbm(u, v, 4, 5, 81));
                Color col = new Color(0.5f, 0.5f, 0.5f) * (0.8f + 0.3f * brushed);
                col = Color.Lerp(col, new Color(0.3f, 0.14f, 0.06f) * (0.7f + 0.6f * Fbm(u, v, 32, 2, 82)), rust);
                col.a = 0.8f - rust * 0.7f;
                c[y * s + x] = col; h[y * s + x] = rust * 0.5f + brushed * 0.1f;
            }
        alb = Finish(NewTex(s, false), c);
        nrm = NormalFromHeight(h, s, 2f);
    }

    static void SheetTex(out Texture2D alb, out Texture2D nrm)
    {
        int s = 256; var c = new Color[s * s]; var h = new float[s * s];
        for (int y = 0; y < s; y++)
            for (int x = 0; x < s; x++)
            {
                float u = x / (float)s, v = y / (float)s;
                float fold = Fbm(u, v, 3, 4, 90);
                Color col = new Color(0.72f, 0.71f, 0.66f) * (0.8f + 0.3f * fold);
                float y1 = Fbm(u, v, 4, 4, 91);
                col = Color.Lerp(col, new Color(0.55f, 0.48f, 0.3f), Smooth(0.55f, 0.7f, y1) * 0.6f);
                float b = Fbm(u, v, 5, 4, 92);
                col = Color.Lerp(col, new Color(0.3f, 0.02f, 0.02f), Smooth(0.68f, 0.72f, b));
                c[y * s + x] = col; h[y * s + x] = fold;
            }
        alb = Finish(NewTex(s, false), c);
        nrm = NormalFromHeight(h, s, 6f);
    }

    static void SkinTex(out Texture2D alb, out Texture2D nrm)
    {
        int s = 256; var c = new Color[s * s]; var h = new float[s * s];
        for (int y = 0; y < s; y++)
            for (int x = 0; x < s; x++)
            {
                float u = x / (float)s, v = y / (float)s;
                float vein = 1f - Mathf.Abs(Fbm(u, v, 6, 4, 100) - 0.5f) * 2f;
                vein = Mathf.Pow(vein, 14f);
                float blotch = Fbm(u, v, 8, 3, 101);
                Color col = new Color(0.06f, 0.055f, 0.055f) * (0.7f + 0.6f * blotch);
                col = Color.Lerp(col, new Color(0.22f, 0.02f, 0.03f), vein);
                col.a = 0.6f + blotch * 0.35f;
                c[y * s + x] = col; h[y * s + x] = vein * 0.6f + blotch * 0.4f;
            }
        alb = Finish(NewTex(s, false), c);
        nrm = NormalFromHeight(h, s, 5f);
    }

    static Texture2D PaperTex()
    {
        int s = 256; var c = new Color[s * s];
        for (int y = 0; y < s; y++)
            for (int x = 0; x < s; x++)
            {
                float u = x / (float)s, v = y / (float)s;
                Color col = new Color(0.82f, 0.78f, 0.64f) * (0.85f + 0.2f * Fbm(u, v, 16, 3, 110));
                int row = y / 14;
                float ly = y % 14;
                bool inText = row > 1 && row < 16 && x > 20 && x < 236;
                if (inText && ly > 5 && ly < 9 && Hash(x / 6, row, 111) > 0.25f && Hash(row, 0, 112) * 236 > x - 20)
                    col = Color.Lerp(col, new Color(0.08f, 0.08f, 0.15f), 0.85f);
                col = Color.Lerp(col, new Color(0.4f, 0.3f, 0.15f), Smooth(0.6f, 0.75f, Fbm(u, v, 3, 3, 113)) * 0.6f);
                c[y * s + x] = col;
            }
        return Finish(NewTex(s, false, true), c);
    }

    static Texture2D BloodTex()
    {
        int s = 256; var c = new Color[s * s];
        var rnd = new System.Random(7);
        var drops = new Vector3[40];
        for (int i = 0; i < drops.Length; i++)
        {
            float ang = (float)rnd.NextDouble() * Mathf.PI * 2f;
            float dist = 0.18f + (float)rnd.NextDouble() * 0.3f;
            drops[i] = new Vector3(0.5f + Mathf.Cos(ang) * dist, 0.5f + Mathf.Sin(ang) * dist, 0.005f + (float)rnd.NextDouble() * 0.025f);
        }
        for (int y = 0; y < s; y++)
            for (int x = 0; x < s; x++)
            {
                float u = x / (float)s, v = y / (float)s;
                float n = Fbm(u, v, 4, 4, 120);
                float r = Vector2.Distance(new Vector2(u, v), new Vector2(0.5f, 0.5f));
                bool inside = r < 0.18f + (n - 0.5f) * 0.35f;
                foreach (var d in drops)
                    if (!inside && Vector2.Distance(new Vector2(u, v), new Vector2(d.x, d.y)) < d.z) inside = true;
                Color col = new Color(0.28f, 0.01f, 0.01f) * (0.55f + 0.6f * Fbm(u, v, 16, 3, 121));
                col.a = inside ? 1f : 0f;
                c[y * s + x] = col;
            }
        return Finish(NewTex(s, false, true), c);
    }

    public static Texture2D FlashlightCookie()
    {
        int s = 256; var c = new Color[s * s];
        for (int y = 0; y < s; y++)
            for (int x = 0; x < s; x++)
            {
                float u = x / (float)(s - 1), v = y / (float)(s - 1);
                float d = Vector2.Distance(new Vector2(u, v), new Vector2(0.5f, 0.5f)) * 2f;
                float k = Smooth(1f, 0.7f, d) * (0.7f + 0.15f * Mathf.Sin(d * 45f) + 0.15f * Fbm(u, v, 8, 3, 130));
                k += (1f - Smooth(0f, 0.3f, d)) * 0.35f;
                k = Mathf.Clamp01(k);
                if (x == 0 || y == 0 || x == s - 1 || y == s - 1) k = 0f;
                c[y * s + x] = new Color(k, k, k, k);
            }
        return Finish(NewTex(s, false, true), c);
    }
}
