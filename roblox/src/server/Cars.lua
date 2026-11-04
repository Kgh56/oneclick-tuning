-- Automodelle: Ausstellungsautos (verankert) und fahrbare Autos
-- ModuleScript "Cars" in ServerScriptService
--
-- Koordinaten relativ zur Karosseriemitte. Die Karosseriemitte liegt 1.7 Studs
-- über dem Boden, die Front zeigt nach -Z.

local Util = require(script.Parent:WaitForChild("Util"))
local part, wedge = Util.part, Util.wedge

local Cars = {}

Cars.BODY_HEIGHT = 1.7 -- Karosseriemitte über Boden
Cars.CHASSIS_HEIGHT = 0.9 -- Mitte des Fahrgestells (fahrbares Auto) über Boden

local TIRE = Color3.fromRGB(25, 25, 27)
local TRIM = Color3.fromRGB(30, 30, 34)
local CHROME = Color3.fromRGB(200, 202, 210)
local GLASS = Color3.fromRGB(20, 28, 40)

local function buildVisual(def, m, convertible)
	local paint = def.Color
	local function lack(name, size, cf)
		return part({
			Name = name,
			Size = size,
			CFrame = cf,
			Color = paint,
			Material = Enum.Material.SmoothPlastic,
			Reflectance = 0.12,
			CanCollide = false,
			Parent = m,
		})
	end
	local function trim(name, size, cf, color, material)
		return part({
			Name = name,
			Size = size,
			CFrame = cf,
			Color = color or TRIM,
			Material = material or Enum.Material.SmoothPlastic,
			CanCollide = false,
			Parent = m,
		})
	end

	-- Karosserie
	lack("Karosserie", Vector3.new(6, 1.0, 12), CFrame.new(0, -0.3, 0))
	lack("Schulter", Vector3.new(5.8, 0.6, 11.6), CFrame.new(0, 0.5, 0))
	local hood = wedge({
		Name = "Haube",
		Size = Vector3.new(5.6, 0.35, 2.6),
		CFrame = CFrame.new(0, 0.97, -4.4),
		Color = paint,
		Material = Enum.Material.SmoothPlastic,
		Reflectance = 0.12,
		CanCollide = false,
		Parent = m,
	})
	hood.Name = "Haube"

	-- Fahrgastzelle
	if convertible then
		part({
			Name = "Frontscheibe",
			Size = Vector3.new(5.0, 1.2, 0.15),
			CFrame = CFrame.new(0, 1.3, -1.9) * CFrame.Angles(math.rad(30), 0, 0),
			Color = GLASS,
			Material = Enum.Material.Glass,
			Transparency = 0.45,
			CanCollide = false,
			Parent = m,
		})
		for _, x in ipairs({ -1.3, 1.3 }) do
			trim("Sitz", Vector3.new(1.6, 1.5, 0.4), CFrame.new(x, 1.35, 1.6), Color3.fromRGB(20, 20, 22), Enum.Material.Fabric)
		end
		part({
			Name = "Lenkrad",
			Shape = Enum.PartType.Cylinder,
			Size = Vector3.new(0.15, 1.0, 1.0),
			CFrame = CFrame.new(-1.3, 1.25, -0.9) * CFrame.Angles(0, math.rad(90), 0) * CFrame.Angles(0, 0, math.rad(-25)),
			Color = Color3.fromRGB(15, 15, 15),
			CanCollide = false,
			Parent = m,
		})
	else
		part({
			Name = "Scheiben",
			Size = Vector3.new(5.0, 1.3, 5.4),
			CFrame = CFrame.new(0, 1.45, 0.9),
			Color = GLASS,
			Material = Enum.Material.Glass,
			Transparency = 0.25,
			Reflectance = 0.2,
			CanCollide = false,
			Parent = m,
		})
		lack("Dach", Vector3.new(4.8, 0.2, 4.2), CFrame.new(0, 2.15, 1.1))
	end

	-- Stoßstangen, Grill, Schweller, Spiegel
	trim("FrontStoss", Vector3.new(6.1, 0.55, 0.5), CFrame.new(0, -0.55, -6.1))
	trim("HeckStoss", Vector3.new(6.1, 0.55, 0.5), CFrame.new(0, -0.55, 6.1))
	trim("Grill", Vector3.new(3.4, 0.45, 0.1), CFrame.new(0, 0.05, -6.03), Color3.fromRGB(12, 12, 14))
	for _, x in ipairs({ -3.05, 3.05 }) do
		trim("Schweller", Vector3.new(0.15, 0.3, 6.4), CFrame.new(x, -0.7, 0))
		lack("Spiegel", Vector3.new(0.5, 0.3, 0.4), CFrame.new(x * 1.02, 1.0, -1.6))
	end

	-- Lichter
	local lights = {}
	for _, x in ipairs({ -2.15, 2.15 }) do
		local hl = part({
			Name = "Scheinwerfer",
			Size = Vector3.new(1.3, 0.35, 0.15),
			CFrame = CFrame.new(x, 0.35, -6.0),
			Color = Color3.fromRGB(255, 248, 225),
			Material = Enum.Material.Neon,
			CanCollide = false,
			Parent = m,
		})
		table.insert(lights, hl)
		part({
			Name = "Ruecklicht",
			Size = Vector3.new(1.4, 0.3, 0.15),
			CFrame = CFrame.new(x, 0.4, 6.0),
			Color = Color3.fromRGB(220, 20, 25),
			Material = Enum.Material.Neon,
			CanCollide = false,
			Parent = m,
		})
	end

	-- Räder mit Felgen
	for _, w in ipairs({ { -3.05, -3.8 }, { 3.05, -3.8 }, { -3.05, 3.8 }, { 3.05, 3.8 } }) do
		local cf = CFrame.new(w[1], -0.5, w[2])
		part({ Name = "Reifen", Shape = Enum.PartType.Cylinder, Size = Vector3.new(1.0, 2.4, 2.4), CFrame = cf, Color = TIRE, CanCollide = false, Parent = m })
		part({
			Name = "Felge",
			Shape = Enum.PartType.Cylinder,
			Size = Vector3.new(1.06, 1.6, 1.6),
			CFrame = cf,
			Color = def.Hp >= 400 and Color3.fromRGB(40, 40, 44) or CHROME,
			Material = Enum.Material.Metal,
			Reflectance = 0.25,
			CanCollide = false,
			Parent = m,
		})
		part({ Name = "Nabe", Shape = Enum.PartType.Cylinder, Size = Vector3.new(1.1, 0.5, 0.5), CFrame = cf, Color = Color3.fromRGB(70, 70, 75), CanCollide = false, Parent = m })
	end

	-- Auspuff
	for _, x in ipairs({ -1.6, 1.6 }) do
		part({
			Name = "Auspuff",
			Shape = Enum.PartType.Cylinder,
			Size = Vector3.new(0.8, 0.45, 0.45),
			CFrame = CFrame.new(x, -0.7, 6.3) * CFrame.Angles(0, math.rad(90), 0),
			Color = CHROME,
			Material = Enum.Material.Metal,
			CanCollide = false,
			Parent = m,
		})
	end

	-- Heckflügel für starke Autos
	if def.Hp >= 400 then
		trim("Fluegel", Vector3.new(6.0, 0.15, 1.2), CFrame.new(0, 1.55, 5.5))
		for _, x in ipairs({ -2, 2 }) do
			trim("FluegelStuetze", Vector3.new(0.2, 0.7, 0.3), CFrame.new(x, 1.15, 5.5))
		end
	end

	return lights
end

-- Verankertes Auto für die Werkstatt. Pivot = Karosseriemitte.
function Cars.MakeShowCar(def)
	local m = Instance.new("Model")
	m.Name = def.Name
	buildVisual(def, m, false)
	local root = part({
		Name = "Wurzel",
		Size = Vector3.new(1, 1, 1),
		CFrame = CFrame.new(),
		Transparency = 1,
		CanCollide = false,
		Parent = m,
	})
	-- Unsichtbarer Block, damit niemand durch das geparkte Auto läuft.
	-- Wird vom Server nur eingeschaltet, solange das Auto steht.
	part({
		Name = "Kollision",
		Size = Vector3.new(6, 2.2, 12),
		CFrame = CFrame.new(0, 0, 0),
		Transparency = 1,
		CanCollide = false,
		Parent = m,
	})
	m.PrimaryPart = root
	return m
end

-- Fahrbares Auto. Pivot = Fahrgestell (CHASSIS_HEIGHT über Boden).
-- Gelenkt wird vom Client (DriveClient) über "Antrieb" und "Lenkung".
function Cars.MakeDrivable(def)
	local m = Instance.new("Model")
	m.Name = def.Name
	local lights = buildVisual(def, m, true)

	local slippery = PhysicalProperties.new(0.7, 0, 0, 100, 1)
	local chassis = part({
		Name = "Fahrgestell",
		Size = Vector3.new(5.6, 1, 11.4),
		CFrame = CFrame.new(0, Cars.CHASSIS_HEIGHT - Cars.BODY_HEIGHT, 0),
		Transparency = 1,
		CanCollide = true,
		CustomPhysicalProperties = slippery,
		Parent = m,
	})
	-- Kugeln als Kontakt zum Boden: rollen über kleine Kanten
	for _, w in ipairs({ { -2.4, -3.8 }, { 2.4, -3.8 }, { -2.4, 3.8 }, { 2.4, 3.8 } }) do
		part({
			Name = "Kontakt",
			Shape = Enum.PartType.Ball,
			Size = Vector3.new(1.2, 1.2, 1.2),
			CFrame = CFrame.new(w[1], 0.6 - Cars.BODY_HEIGHT, w[2]),
			Transparency = 1,
			CanCollide = true,
			CustomPhysicalProperties = slippery,
			Parent = m,
		})
	end

	local seat = Instance.new("VehicleSeat")
	seat.Name = "Fahrersitz"
	seat.Size = Vector3.new(1.6, 0.4, 1.6)
	seat.CFrame = CFrame.new(-1.3, 0.9 - Cars.BODY_HEIGHT + 0.6, 1.2)
	seat.Transparency = 1
	seat.CanCollide = false
	seat.HeadsUpDisplay = false
	seat.MaxSpeed = 0
	seat.Torque = 0
	seat.TurnSpeed = 0
	seat.Anchored = true
	seat.Parent = m

	for _, hl in ipairs(lights) do
		Util.light(hl, "SpotLight", { Face = Enum.NormalId.Front, Range = 60, Brightness = 2, Angle = 70, Color = Color3.fromRGB(255, 245, 225) })
	end

	-- Alles ans Fahrgestell schweißen
	for _, d in ipairs(m:GetDescendants()) do
		if d:IsA("BasePart") and d ~= chassis then
			d.Anchored = false
			d.Massless = true
			local w = Instance.new("WeldConstraint")
			w.Part0 = chassis
			w.Part1 = d
			w.Parent = d
		end
	end
	chassis.Anchored = false

	local att = Instance.new("Attachment")
	att.Name = "Mitte"
	att.Parent = chassis

	local lv = Instance.new("LinearVelocity")
	lv.Name = "Antrieb"
	lv.Attachment0 = att
	lv.RelativeTo = Enum.ActuatorRelativeTo.World
	lv.VelocityConstraintMode = Enum.VelocityConstraintMode.Plane
	lv.PrimaryTangentAxis = Vector3.xAxis
	lv.SecondaryTangentAxis = Vector3.zAxis
	lv.PlaneVelocity = Vector2.zero
	lv.MaxForce = 12000
	lv.Parent = chassis

	local av = Instance.new("AngularVelocity")
	av.Name = "Lenkung"
	av.Attachment0 = att
	av.RelativeTo = Enum.ActuatorRelativeTo.World
	av.AngularVelocity = Vector3.zero
	av.MaxTorque = 60000
	av.Parent = chassis

	m.PrimaryPart = chassis
	return m, seat
end

return Cars
