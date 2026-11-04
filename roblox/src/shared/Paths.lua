-- Wege für Straßenverkehr und Fußgänger
-- ModuleScript "Paths" in ReplicatedStorage
--
-- Die Koordinaten passen zu World.lua (Werkstattstraße z = 50, Landstraße
-- als Rechteck x = ±700, z = 260 / -780). Es gilt Rechtsverkehr.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Config = require(ReplicatedStorage:WaitForChild("Config"))

local Paths = {}

local function rightOf(d)
	return Vector3.new(-d.Z, 0, d.X)
end

local function finish(pts, closed)
	local cum = { 0 }
	local total = 0
	local n = #pts
	local last = closed and n or n - 1
	for i = 1, last do
		local j = (i % n) + 1
		total += (pts[j] - pts[i]).Magnitude
		cum[i + 1] = total
	end
	return { Points = pts, Cum = cum, Length = total, Closed = closed }
end

-- Geschlossene Fahrspur durch Eckpunkte: nach rechts versetzt, Ecken gerundet
function Paths.Loop(corners, lane, radius)
	local n = #corners
	local pts = {}
	for i = 1, n do
		local prev = corners[(i - 2) % n + 1]
		local cur = corners[i]
		local nxt = corners[i % n + 1]
		local dIn = (cur - prev).Unit
		local dOut = (nxt - cur).Unit
		local c = cur + (rightOf(dIn) + rightOf(dOut)) * lane
		local a = c - dIn * radius
		local b = c + dOut * radius
		for k = 0, 6 do
			local t = k / 6
			table.insert(pts, a * ((1 - t) ^ 2) + c * (2 * (1 - t) * t) + b * (t ^ 2))
		end
	end
	return finish(pts, true)
end

-- Offene Strecke (für Fußgänger, die hin und her gehen)
function Paths.Line(a, b)
	return finish({ a, b }, false)
end

-- Punkt und Richtung bei Weg-Position s
function Paths.Sample(path, s)
	local L = path.Length
	if path.Closed then
		s = s % L
	else
		s = math.clamp(s, 0, L)
	end
	local cum = path.Cum
	local lo, hi = 1, #cum - 1
	while lo < hi do
		local mid = math.floor((lo + hi + 1) / 2)
		if cum[mid] <= s then
			lo = mid
		else
			hi = mid - 1
		end
	end
	local pts = path.Points
	local p0 = pts[lo]
	local p1 = pts[(lo % #pts) + 1]
	local segLen = cum[lo + 1] - cum[lo]
	local t = segLen > 0 and (s - cum[lo]) / segLen or 0
	local dir = p1 - p0
	if dir.Magnitude < 1e-4 then
		dir = Vector3.new(1, 0, 0)
	end
	return p0:Lerp(p1, t), dir.Unit
end

-- Straßenverkehr: drei Rundkurse, die zusammen beide Fahrtrichtungen abdecken
local ROAD_Z = 50
local LANE = 5
Paths.TrafficLoops = {
	Paths.Loop({ Vector3.new(-700, 0, ROAD_Z), Vector3.new(700, 0, ROAD_Z), Vector3.new(700, 0, 260), Vector3.new(-700, 0, 260) }, LANE, 12),
	Paths.Loop({ Vector3.new(-700, 0, 260), Vector3.new(700, 0, 260), Vector3.new(700, 0, -780), Vector3.new(-700, 0, -780) }, LANE, 12),
	Paths.Loop({ Vector3.new(700, 0, ROAD_Z), Vector3.new(-700, 0, ROAD_Z), Vector3.new(-700, 0, -780), Vector3.new(700, 0, -780) }, LANE, 12),
}

-- Fußgängerwege: { Weg, Bodenhöhe, Schleife? }
local T = Config.Track
local SOUTH_Z = T.CenterZ + T.Radius
local paddockZ = SOUTH_Z + T.Width / 2 - 1 + 50
Paths.Walkways = {
	{ Path = Paths.Line(Vector3.new(-880, 0, ROAD_Z + 15), Vector3.new(880, 0, ROAD_Z + 15)), Ground = 0.3 },
	{ Path = Paths.Line(Vector3.new(880, 0, ROAD_Z + 17.5), Vector3.new(-880, 0, ROAD_Z + 17.5)), Ground = 0.3 },
	{ Path = Paths.Line(Vector3.new(-170, 0, paddockZ), Vector3.new(170, 0, paddockZ)), Ground = 0.1 },
	{ Path = Paths.Loop({ Vector3.new(512, 0, 322), Vector3.new(788, 0, 322), Vector3.new(788, 0, 538), Vector3.new(512, 0, 538) }, 0, 8), Ground = 0.2 },
}

-- Zuschauer auf der Tribüne: Positionen (Boden) mit Blick zur Strecke
function Paths.Spectators()
	local list = {}
	local standZ = SOUTH_Z - T.Width / 2 - 22
	local rng = Random.new(5)
	for _, tier in ipairs({ 1, 2, 3, 4, 5 }) do
		for _ = 1, 3 do
			local x = rng:NextNumber(-55, 55)
			local pos = Vector3.new(x, 1.5 + tier * 1.5, standZ - tier * 4)
			table.insert(list, CFrame.lookAt(pos, pos + Vector3.zAxis))
		end
	end
	return list
end

return Paths
