using System.Collections.Generic;
using UnityEngine;

public class ClinicData
{
    public const float S = 3f;      // Zellgröße in Metern
    public const float CEIL = 3.2f; // Deckenhöhe
    public string[] Map;
    public int W, H;
    public bool[,] Walk;
    public Vector3 PlayerSpawn, MonsterSpawn;
    public float PlayerYaw = 90f;
    public readonly List<Vector2Int> WalkCells = new List<Vector2Int>();

    public Vector3 CellToWorld(int x, int y) => new Vector3(x * S, 0f, (H - 1 - y) * S);
    public Vector3 CellToWorld(Vector2Int c) => CellToWorld(c.x, c.y);
    public Vector2Int WorldToCell(Vector3 p) => new Vector2Int(Mathf.RoundToInt(p.x / S), H - 1 - Mathf.RoundToInt(p.z / S));
    public bool InBounds(int x, int y) => x >= 0 && y >= 0 && x < W && y < H;
    public bool IsWall(int x, int y) => !InBounds(x, y) || Map[y][x] == '#';
    public bool IsWalk(Vector2Int c) => InBounds(c.x, c.y) && Walk[c.x, c.y];

    public Vector2Int NearestWalk(Vector2Int c)
    {
        if (IsWalk(c)) return c;
        Vector2Int best = c; float bd = float.MaxValue;
        foreach (var w in WalkCells)
        {
            float d = (w - c).sqrMagnitude;
            if (d < bd) { bd = d; best = w; }
        }
        return best;
    }
}

/// <summary>
/// Baut die Klinik "St. Agnes" aus einer ASCII-Karte.
///  # Wand   . Boden   D Durchgang   B Bett   W Rollstuhl
///  F Sicherung   A Batterie   N Notiz   E Notstromtor   P Spieler   M Monster
/// </summary>
public static class ClinicBuilder
{
    public static readonly string[] Map =
    {
        "###############################",
        "#B..N#...........#B..A#..F...B#",
        "#....D...........D....D.......#",
        "#B...#.....#######B...#B.....B#",
        "######.....#.....######...#####",
        "#....#.....D.....#....#.......#",
        "#.F..D.....#..N..#.A..D...M...#",
        "#....#.....#.....#....#.......#",
        "###D##.....###D#####D##.......#",
        "#.............................#",
        "#.P..........................E#",
        "#.............................#",
        "###D######D#######D######D#####",
        "#B...#......#B...B..#.......F.#",
        "#..N.#..W...#.......#..N......#",
        "#B..A#......#B...B..#.........#",
        "###############################",
    };

    static readonly string[][] Notes =
    {
        new[] { "Tagebuch Dr. Weiss – 14.03.1987",
            "Patient 17 schläft nicht mehr. Er steht nur in der Ecke und starrt die Neonröhren an.\n\n" +
            "Wenn das Licht flackert, ist er näher als vorher. Ich habe es dreimal gemessen.\n\n" +
            "Die Schwestern weigern sich, den Ostflügel zu betreten." },
        new[] { "Zettel, mit zitternder Hand geschrieben",
            "Wer das hier liest: Das Notstromtor am Ende des Hauptflurs braucht DREI Sicherungen.\n\n" +
            "Ich habe sie in der Klinik versteckt, damit ER nicht rauskommt.\n\n" +
            "Gott vergib mir. – Schwester M." },
        new[] { "Kinderzeichnung",
            "Ein langer schwarzer Mann mit viel zu langen Armen. Die Augen sind zwei weiße Punkte.\n\n" +
            "Darunter, in Wachsmalstift:\n\nER HÖRT DICH WENN DU RENNST" },
        new[] { "Notiz an der Wand",
            "Mach die Lampe AUS wenn er kommt. Er sieht das Licht.\n\n" +
            "Duck dich [STRG]. Beweg dich langsam.\n\n" +
            "Und schau ihm nicht zu lange ins Gesicht." },
        new[] { "Patientenakte 17",
            "Größe: 2,61 m (?)   Gewicht: nicht messbar\n\n" +
            "Bemerkung: Messungen widersprüchlich. Pupillen reagieren nicht auf Licht.\n\n" +
            "Nachtrag, handschriftlich: Der Patient ist nicht mehr im Zimmer. Die Tür war nie offen." },
    };

    static System.Random rnd;
    static float R() => (float)rnd.NextDouble();
    static float R(float a, float b) => a + (b - a) * R();

    public static ClinicData Build(Transform root, System.Random random)
    {
        rnd = random;
        var d = new ClinicData { Map = Map, H = Map.Length, W = Map[0].Length };
        d.Walk = new bool[d.W, d.H];
        int noteIdx = 0;

        var geo = new GameObject("Geometry").transform; geo.SetParent(root);
        var props = new GameObject("Props").transform; props.SetParent(root);
        var lights = new GameObject("Lights").transform; lights.SetParent(root);

        var wallMat = ProcTex.Get("wall");
        var floorMat = ProcTex.Get("floor");
        var ceilMat = ProcTex.Get("ceiling");

        for (int y = 0; y < d.H; y++)
            for (int x = 0; x < d.W; x++)
            {
                char c = Map[y][x];
                Vector3 p = d.CellToWorld(x, y);
                if (c == '#')
                {
                    if (!HasFloorNeighbour(d, x, y)) continue;
                    Box(geo, p + Vector3.up * ClinicData.CEIL / 2f, new Vector3(ClinicData.S, ClinicData.CEIL, ClinicData.S), wallMat, true);
                    WallDecals(d, props, x, y, p);
                    continue;
                }

                d.Walk[x, y] = c != 'B' && c != 'W';
                if (d.Walk[x, y]) d.WalkCells.Add(new Vector2Int(x, y));

                Box(geo, p + Vector3.down * 0.1f, new Vector3(ClinicData.S, 0.2f, ClinicData.S), floorMat, true);
                Box(geo, p + Vector3.up * (ClinicData.CEIL + 0.1f), new Vector3(ClinicData.S, 0.2f, ClinicData.S), ceilMat, true);

                switch (c)
                {
                    case 'D': Doorway(d, geo, x, y, p, wallMat); break;
                    case 'B': Bed(d, props, x, y, p); break;
                    case 'W': Wheelchair(props, p); break;
                    case 'P': d.PlayerSpawn = p; break;
                    case 'M': d.MonsterSpawn = p; break;
                    case 'F': FusePickup(d, props, x, y, p); break;
                    case 'A': Battery(props, p); break;
                    case 'E': ExitGate.Build(props, p, WallDir(d, x, y)); break;
                    case 'N':
                        var n = Notes[noteIdx % Notes.Length]; noteIdx++;
                        Note(d, props, x, y, p, n[0], n[1]);
                        break;
                }
                if (c == '.') FloorClutter(d, props, x, y, p);
                if (x % 3 == 1 && y % 3 == 1 && c != 'D') CeilingLight(lights, p);
            }

        // die übrige Notiz (Akte) liegt im Spawnraum auf dem Boden
        if (noteIdx < Notes.Length)
        {
            var n = Notes[Notes.Length - 1];
            var paper = Box(props, d.PlayerSpawn + new Vector3(1.2f, 0.02f, 0.6f), new Vector3(0.3f, 0.01f, 0.4f), ProcTex.Get("paper"), true);
            paper.transform.rotation = Quaternion.Euler(0, R(0, 360), 0);
            var ni = paper.AddComponent<NoteItem>(); ni.Title = n[0]; ni.Body = n[1];
        }
        return d;
    }

    // ---------- Grundbausteine ----------
    public static GameObject Box(Transform parent, Vector3 pos, Vector3 scale, Material m, bool collider)
        => Prim(PrimitiveType.Cube, parent, pos, scale, m, collider);

    public static GameObject Prim(PrimitiveType t, Transform parent, Vector3 pos, Vector3 scale, Material m, bool collider)
    {
        var g = GameObject.CreatePrimitive(t);
        g.transform.SetParent(parent, false);
        g.transform.position = pos;
        g.transform.localScale = scale;
        g.GetComponent<Renderer>().sharedMaterial = m;
        if (!collider) Object.Destroy(g.GetComponent<Collider>());
        return g;
    }

    /// <summary>Teil eines Objekts in lokalen Koordinaten (ohne Collider).</summary>
    public static GameObject Part(PrimitiveType t, Transform parent, Vector3 lpos, Vector3 lscale, Material m, Vector3 euler = default)
    {
        var g = GameObject.CreatePrimitive(t);
        Object.Destroy(g.GetComponent<Collider>());
        g.transform.SetParent(parent, false);
        g.transform.localPosition = lpos;
        g.transform.localRotation = Quaternion.Euler(euler);
        g.transform.localScale = lscale;
        g.GetComponent<Renderer>().sharedMaterial = m;
        return g;
    }

    static bool HasFloorNeighbour(ClinicData d, int x, int y)
    {
        for (int dy = -1; dy <= 1; dy++)
            for (int dx = -1; dx <= 1; dx++)
                if (d.InBounds(x + dx, y + dy) && Map[y + dy][x + dx] != '#') return true;
        return false;
    }

    static readonly Vector2Int[] Dirs = { new Vector2Int(1, 0), new Vector2Int(-1, 0), new Vector2Int(0, -1), new Vector2Int(0, 1) };
    static Vector3 GridToWorldDir(Vector2Int g) => new Vector3(g.x, 0, -g.y);

    /// <summary>Weltrichtung zu einer benachbarten Wand (oder zero).</summary>
    static Vector3 WallDir(ClinicData d, int x, int y)
    {
        foreach (var g in Dirs)
            if (d.IsWall(x + g.x, y + g.y)) return GridToWorldDir(g);
        return Vector3.zero;
    }

    static void WallDecals(ClinicData d, Transform parent, int x, int y, Vector3 p)
    {
        foreach (var g in Dirs)
        {
            int nx = x + g.x, ny = y + g.y;
            if (!d.InBounds(nx, ny) || Map[ny][nx] == '#') continue;
            if (R() > 0.18f) continue;
            Vector3 dir = GridToWorldDir(g);
            Vector3 side = Vector3.Cross(Vector3.up, dir);
            float sc = R(0.8f, 1.8f);
            var q = Prim(PrimitiveType.Quad, parent, p + dir * (ClinicData.S / 2f + 0.012f) + Vector3.up * R(0.4f, 2.2f) + side * R(-0.9f, 0.9f),
                new Vector3(sc, sc * R(0.8f, 1.6f), 1f), ProcTex.Get("blood"), false);
            q.transform.rotation = Quaternion.LookRotation(-dir) * Quaternion.Euler(0, 0, R(0, 360));
        }
    }

    static void Doorway(ClinicData d, Transform parent, int x, int y, Vector3 p, Material wall)
    {
        bool alongX = d.IsWall(x - 1, y) && d.IsWall(x + 1, y);
        Vector3 axis = alongX ? Vector3.right : Vector3.forward;
        float side = 0.85f, half = ClinicData.S / 2f;
        for (int s = -1; s <= 1; s += 2)
        {
            Vector3 c = p + axis * s * (half - side / 2f) + Vector3.up * ClinicData.CEIL / 2f;
            Vector3 sc = alongX ? new Vector3(side, ClinicData.CEIL, ClinicData.S) : new Vector3(ClinicData.S, ClinicData.CEIL, side);
            Box(parent, c, sc, wall, true);
        }
        float lintel = ClinicData.CEIL - 2.3f;
        Box(parent, p + Vector3.up * (2.3f + lintel / 2f), new Vector3(ClinicData.S, lintel, ClinicData.S), wall, true);
    }

    static void CeilingLight(Transform parent, Vector3 p)
    {
        var go = new GameObject("CeilingLight");
        go.transform.SetParent(parent, false);
        go.transform.position = p + Vector3.up * (ClinicData.CEIL - 0.25f);
        var l = go.AddComponent<Light>();
        l.type = LightType.Point;
        l.range = 8f;
        l.color = new Color(0.72f, 0.95f, 0.82f);
        l.intensity = 1.8f;
        bool shadows = R() < 0.15f;
        l.shadows = shadows ? LightShadows.Soft : LightShadows.None;

        var panel = Box(parent, p + Vector3.up * (ClinicData.CEIL - 0.02f), new Vector3(1.3f, 0.05f, 0.35f), new Material(ProcTex.Get("panel")), false);

        var f = go.AddComponent<FlickerLight>();
        float r = R();
        f.Init(l, panel.GetComponent<Renderer>(), r < 0.22f ? FlickerLight.Mode.Dead : r < 0.55f ? FlickerLight.Mode.Flicker : FlickerLight.Mode.Steady);
    }

    static void FloorClutter(ClinicData d, Transform parent, int x, int y, Vector3 p)
    {
        float r = R();
        if (r < 0.12f)
        {
            float sc = R(1.2f, 2.6f);
            var q = Prim(PrimitiveType.Quad, parent, p + new Vector3(R(-0.8f, 0.8f), 0.006f + R() * 0.004f, R(-0.8f, 0.8f)), new Vector3(sc, sc, 1), ProcTex.Get("blood"), false);
            q.transform.rotation = Quaternion.Euler(90, R(0, 360), 0);
        }
        else if (r < 0.26f)
        {
            int count = rnd.Next(1, 5);
            for (int i = 0; i < count; i++)
            {
                var q = Prim(PrimitiveType.Quad, parent, p + new Vector3(R(-1.2f, 1.2f), 0.004f + i * 0.002f, R(-1.2f, 1.2f)), new Vector3(0.22f, 0.3f, 1), ProcTex.Get("decalPaper"), false);
                q.transform.rotation = Quaternion.Euler(90, R(0, 360), 0);
            }
        }
        else if (r < 0.31f)
        {
            Vector3 wd = WallDir(d, x, y);
            IVStand(parent, p + wd * 1.0f + new Vector3(R(-0.3f, 0.3f), 0, R(-0.3f, 0.3f)));
        }
        else if (r < 0.35f)
        {
            Vector3 wd = WallDir(d, x, y);
            Chair(parent, p + wd * 1.0f);
        }
    }

    // ---------- Requisiten ----------
    static void Bed(ClinicData d, Transform parent, int x, int y, Vector3 p)
    {
        float yRot = 0; Vector3 shift = Vector3.zero;
        if (d.IsWall(x - 1, y)) { yRot = 0; shift = Vector3.left * 0.4f; }
        else if (d.IsWall(x + 1, y)) { yRot = 180; shift = Vector3.right * 0.4f; }
        else if (d.IsWall(x, y - 1)) { yRot = 90; shift = Vector3.forward * 0.4f; }
        else if (d.IsWall(x, y + 1)) { yRot = -90; shift = Vector3.back * 0.4f; }

        var b = new GameObject("Bed").transform;
        b.SetParent(parent, false);
        b.position = p + shift;
        b.rotation = Quaternion.Euler(0, yRot + R(-6f, 6f), 0);
        var col = b.gameObject.AddComponent<BoxCollider>();
        col.center = new Vector3(0, 0.45f, 0); col.size = new Vector3(2.05f, 0.9f, 1f);

        var metal = ProcTex.Get("metal"); var sheet = ProcTex.Get("sheet"); var leather = ProcTex.Get("leather");
        Part(PrimitiveType.Cube, b, new Vector3(0, 0.42f, 0), new Vector3(2f, 0.06f, 0.95f), metal);
        for (int sx = -1; sx <= 1; sx += 2)
            for (int sz = -1; sz <= 1; sz += 2)
                Part(PrimitiveType.Cylinder, b, new Vector3(sx * 0.92f, 0.21f, sz * 0.42f), new Vector3(0.05f, 0.21f, 0.05f), metal);
        Part(PrimitiveType.Cube, b, new Vector3(-1f, 0.75f, 0), new Vector3(0.05f, 0.7f, 0.95f), metal);
        Part(PrimitiveType.Cube, b, new Vector3(1f, 0.6f, 0), new Vector3(0.05f, 0.4f, 0.95f), metal);
        Part(PrimitiveType.Cube, b, new Vector3(0, 0.53f, 0), new Vector3(1.9f, 0.16f, 0.88f), sheet);
        Part(PrimitiveType.Cube, b, new Vector3(-0.75f, 0.66f, 0), new Vector3(0.35f, 0.1f, 0.6f), sheet);
        // Fixiergurte
        Part(PrimitiveType.Cube, b, new Vector3(-0.2f, 0.56f, 0), new Vector3(0.09f, 0.18f, 0.92f), leather);
        Part(PrimitiveType.Cube, b, new Vector3(0.6f, 0.56f, 0), new Vector3(0.09f, 0.18f, 0.92f), leather);

        if (R() < 0.4f)
        {
            // Körper unter dem Laken
            Part(PrimitiveType.Capsule, b, new Vector3(0.05f, 0.72f, 0), new Vector3(0.42f, 0.85f, 0.3f), sheet, new Vector3(0, 0, 90));
            Part(PrimitiveType.Sphere, b, new Vector3(-0.78f, 0.76f, 0), new Vector3(0.28f, 0.24f, 0.28f), sheet);
            if (R() < 0.6f)
            {
                var q = Part(PrimitiveType.Quad, b, new Vector3(0.1f, 0.62f, 0), Vector3.one * 1.6f, ProcTex.Get("blood"), new Vector3(90, R(0, 360), 0));
                q.transform.position = new Vector3(q.transform.position.x, 0.006f, q.transform.position.z);
            }
        }
    }

    static void Wheelchair(Transform parent, Vector3 p)
    {
        var w = new GameObject("Wheelchair").transform;
        w.SetParent(parent, false);
        w.position = p + new Vector3(R(-0.4f, 0.4f), 0, R(-0.4f, 0.4f));
        w.rotation = Quaternion.Euler(0, R(0, 360), 0);
        var col = w.gameObject.AddComponent<BoxCollider>();
        col.center = new Vector3(0, 0.5f, 0); col.size = new Vector3(0.7f, 1f, 0.7f);
        var metal = ProcTex.Get("metal"); var black = ProcTex.Get("leather");
        Part(PrimitiveType.Cube, w, new Vector3(0, 0.5f, 0), new Vector3(0.5f, 0.06f, 0.5f), black);
        Part(PrimitiveType.Cube, w, new Vector3(-0.25f, 0.8f, 0), new Vector3(0.05f, 0.55f, 0.5f), black);
        for (int s = -1; s <= 1; s += 2)
        {
            Part(PrimitiveType.Cylinder, w, new Vector3(-0.05f, 0.32f, s * 0.31f), new Vector3(0.64f, 0.015f, 0.64f), metal, new Vector3(90, 0, 0));
            Part(PrimitiveType.Cylinder, w, new Vector3(0.28f, 0.08f, s * 0.2f), new Vector3(0.15f, 0.02f, 0.15f), black, new Vector3(90, 0, 0));
        }
    }

    static void IVStand(Transform parent, Vector3 p)
    {
        var t = new GameObject("IVStand").transform;
        t.SetParent(parent, false); t.position = p;
        var metal = ProcTex.Get("metal");
        Part(PrimitiveType.Cylinder, t, new Vector3(0, 0.95f, 0), new Vector3(0.03f, 0.95f, 0.03f), metal);
        Part(PrimitiveType.Cube, t, new Vector3(0, 0.03f, 0), new Vector3(0.5f, 0.03f, 0.05f), metal);
        Part(PrimitiveType.Cube, t, new Vector3(0, 0.03f, 0), new Vector3(0.05f, 0.03f, 0.5f), metal);
        Part(PrimitiveType.Cube, t, new Vector3(0, 1.85f, 0), new Vector3(0.3f, 0.02f, 0.02f), metal);
        Part(PrimitiveType.Cube, t, new Vector3(0.12f, 1.65f, 0), new Vector3(0.12f, 0.25f, 0.05f), ProcTex.Get("bloodbag"));
    }

    static void Chair(Transform parent, Vector3 p)
    {
        var t = new GameObject("Chair").transform;
        t.SetParent(parent, false); t.position = p + Vector3.up * 0.22f;
        t.rotation = Quaternion.Euler(R() < 0.5f ? 0 : 85, R(0, 360), 0);
        var metal = ProcTex.Get("metal");
        Part(PrimitiveType.Cube, t, new Vector3(0, 0.25f, 0), new Vector3(0.45f, 0.04f, 0.45f), ProcTex.Get("leather"));
        Part(PrimitiveType.Cube, t, new Vector3(-0.21f, 0.55f, 0), new Vector3(0.04f, 0.55f, 0.45f), metal);
        for (int sx = -1; sx <= 1; sx += 2)
            for (int sz = -1; sz <= 1; sz += 2)
                Part(PrimitiveType.Cube, t, new Vector3(sx * 0.2f, 0f, sz * 0.2f), new Vector3(0.03f, 0.48f, 0.03f), metal);
    }

    static void FusePickup(ClinicData d, Transform parent, int x, int y, Vector3 p)
    {
        Vector3 wd = WallDir(d, x, y);
        Vector3 pos = p + wd * 1.1f;
        if (wd == Vector3.zero) d.Walk[x, y] = false;
        var cab = Box(parent, pos + Vector3.up * 0.45f, new Vector3(0.6f, 0.9f, 0.5f), ProcTex.Get("metal"), true);
        if (wd != Vector3.zero) cab.transform.rotation = Quaternion.LookRotation(-wd);

        var fuse = new GameObject("Fuse");
        fuse.transform.SetParent(parent, false);
        fuse.transform.position = pos + Vector3.up * 1.0f;
        var trig = fuse.AddComponent<BoxCollider>(); trig.isTrigger = true; trig.size = new Vector3(0.45f, 0.35f, 0.45f);
        var vis = Part(PrimitiveType.Cylinder, fuse.transform, Vector3.zero, new Vector3(0.07f, 0.07f, 0.07f), ProcTex.Get("fuse"), new Vector3(0, 0, 90));
        Part(PrimitiveType.Cylinder, vis.transform, new Vector3(0, 1.1f, 0), new Vector3(1.1f, 0.15f, 1.1f), ProcTex.Get("metal"));
        Part(PrimitiveType.Cylinder, vis.transform, new Vector3(0, -1.1f, 0), new Vector3(1.1f, 0.15f, 1.1f), ProcTex.Get("metal"));
        var l = new GameObject("Glow").AddComponent<Light>();
        l.transform.SetParent(fuse.transform, false); l.transform.localPosition = Vector3.up * 0.3f;
        l.type = LightType.Point; l.color = new Color(1f, 0.55f, 0.15f); l.range = 2.5f; l.intensity = 1.4f;
        var pk = fuse.AddComponent<Pickup>(); pk.kind = Pickup.Kind.Fuse; pk.visual = vis.transform;
    }

    static void Battery(Transform parent, Vector3 p)
    {
        var b = new GameObject("Battery");
        b.transform.SetParent(parent, false);
        b.transform.position = p + new Vector3(R(-0.6f, 0.6f), 0.12f, R(-0.6f, 0.6f));
        var trig = b.AddComponent<BoxCollider>(); trig.isTrigger = true; trig.size = new Vector3(0.35f, 0.3f, 0.35f);
        var vis = Part(PrimitiveType.Cylinder, b.transform, Vector3.zero, new Vector3(0.06f, 0.07f, 0.06f), ProcTex.Get("battery"));
        var l = new GameObject("Glow").AddComponent<Light>();
        l.transform.SetParent(b.transform, false); l.transform.localPosition = Vector3.up * 0.25f;
        l.type = LightType.Point; l.color = new Color(0.3f, 0.8f, 1f); l.range = 1.6f; l.intensity = 0.9f;
        var pk = b.AddComponent<Pickup>(); pk.kind = Pickup.Kind.Battery; pk.visual = vis.transform;
    }

    static void Note(ClinicData d, Transform parent, int x, int y, Vector3 p, string title, string body)
    {
        Vector3 wd = WallDir(d, x, y);
        GameObject paper;
        if (wd != Vector3.zero)
        {
            paper = Box(parent, p + wd * (ClinicData.S / 2f - 0.01f) + Vector3.up * 1.5f, new Vector3(0.3f, 0.4f, 0.01f), ProcTex.Get("paper"), true);
            paper.transform.rotation = Quaternion.LookRotation(-wd) * Quaternion.Euler(0, 0, R(-8f, 8f));
        }
        else
        {
            paper = Box(parent, p + Vector3.up * 0.01f, new Vector3(0.3f, 0.01f, 0.4f), ProcTex.Get("paper"), true);
            paper.transform.rotation = Quaternion.Euler(0, R(0, 360), 0);
        }
        var n = paper.AddComponent<NoteItem>(); n.Title = title; n.Body = body;
    }
}

/// <summary>A*-Pfadsuche auf dem Zellraster.</summary>
public static class GridPath
{
    static readonly Vector2Int[] Dirs = { new Vector2Int(1, 0), new Vector2Int(-1, 0), new Vector2Int(0, 1), new Vector2Int(0, -1) };

    public static List<Vector2Int> Find(ClinicData d, Vector2Int s, Vector2Int g)
    {
        var res = new List<Vector2Int>();
        s = d.NearestWalk(s); g = d.NearestWalk(g);
        if (s == g) { res.Add(g); return res; }
        var gs = new float[d.W, d.H];
        var came = new Vector2Int[d.W, d.H];
        var closed = new bool[d.W, d.H];
        var inOpen = new bool[d.W, d.H];
        for (int x = 0; x < d.W; x++) for (int y = 0; y < d.H; y++) gs[x, y] = float.MaxValue;
        var open = new List<Vector2Int> { s };
        gs[s.x, s.y] = 0; inOpen[s.x, s.y] = true;
        while (open.Count > 0)
        {
            int bi = 0; float bf = float.MaxValue;
            for (int i = 0; i < open.Count; i++)
            {
                var o = open[i];
                float f = gs[o.x, o.y] + Mathf.Abs(o.x - g.x) + Mathf.Abs(o.y - g.y);
                if (f < bf) { bf = f; bi = i; }
            }
            var cur = open[bi];
            if (cur == g)
            {
                while (cur != s) { res.Add(cur); cur = came[cur.x, cur.y]; }
                res.Reverse();
                return res;
            }
            open.RemoveAt(bi); inOpen[cur.x, cur.y] = false; closed[cur.x, cur.y] = true;
            foreach (var dir in Dirs)
            {
                var n = cur + dir;
                if (!d.IsWalk(n) || closed[n.x, n.y]) continue;
                float ng = gs[cur.x, cur.y] + 1f;
                if (ng < gs[n.x, n.y])
                {
                    gs[n.x, n.y] = ng; came[n.x, n.y] = cur;
                    if (!inOpen[n.x, n.y]) { open.Add(n); inOpen[n.x, n.y] = true; }
                }
            }
        }
        return res;
    }
}
