-- Personen-Vorlagen für Fahrer, Kunden und Fußgänger
-- ModuleScript "Npc" in ServerScriptService
--
-- Erstellt beim Start einige R15-Figuren mit verschiedenen Haut-, Shirt- und
-- Hosenfarben und legt sie in ReplicatedStorage.Leute ab. Server und Clients
-- klonen daraus. Bewegt (Sitzen, Gehen, Umschauen) werden die Figuren vom
-- LifeClient über ihre Gelenke – ganz ohne Animations-Assets.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local CollectionService = game:GetService("CollectionService")

local Config = require(ReplicatedStorage:WaitForChild("Config"))

local Npc = {}
Npc.TAG = "Npc"

local SKIN = {
	Color3.fromRGB(255, 220, 190),
	Color3.fromRGB(234, 192, 160),
	Color3.fromRGB(198, 145, 110),
	Color3.fromRGB(160, 110, 75),
	Color3.fromRGB(110, 75, 50),
	Color3.fromRGB(245, 205, 170),
}
local SHIRTS = {
	Color3.fromRGB(30, 60, 120),
	Color3.fromRGB(180, 30, 40),
	Color3.fromRGB(240, 240, 240),
	Color3.fromRGB(40, 40, 45),
	Color3.fromRGB(60, 130, 70),
	Color3.fromRGB(255, 140, 0),
	Color3.fromRGB(120, 70, 150),
	Color3.fromRGB(90, 160, 210),
}
local PANTS = {
	Color3.fromRGB(35, 45, 80),
	Color3.fromRGB(30, 30, 32),
	Color3.fromRGB(110, 95, 75),
	Color3.fromRGB(70, 75, 85),
	Color3.fromRGB(50, 70, 110),
}
-- Kostenlose Roblox-Frisuren; falls eine nicht lädt, gibt es die Figur ohne Haare
local HAIR = { "62743701", "451220849", "376548738", "" , "" }

-- Einfache R15-ähnliche Figur aus Bausteinen (Ersatz, falls die Roblox-Funktion fehlt)
local function fallbackRig(skin, shirt, pants)
	local m = Instance.new("Model")
	local function bp(name, size, pos, color)
		local p = Instance.new("Part")
		p.Name = name
		p.Size = size
		p.CFrame = CFrame.new(pos)
		p.Color = color
		p.TopSurface = Enum.SurfaceType.Smooth
		p.BottomSurface = Enum.SurfaceType.Smooth
		p.Parent = m
		return p
	end
	local hrp = bp("HumanoidRootPart", Vector3.new(2, 2, 1), Vector3.new(0, 3, 0), skin)
	local lower = bp("LowerTorso", Vector3.new(2, 0.4, 1), Vector3.new(0, 2.6, 0), pants)
	local upper = bp("UpperTorso", Vector3.new(2, 1.6, 1), Vector3.new(0, 3.6, 0), shirt)
	local head = bp("Head", Vector3.new(1.2, 1.2, 1.2), Vector3.new(0, 5, 0), skin)
	local face = Instance.new("Decal")
	face.Name = "face"
	face.Texture = "rbxasset://textures/face.png"
	face.Face = Enum.NormalId.Front
	face.Parent = head
	local parts = {
		LeftUpperArm = bp("LeftUpperArm", Vector3.new(1, 1.2, 1), Vector3.new(-1.5, 3.8, 0), shirt),
		LeftLowerArm = bp("LeftLowerArm", Vector3.new(1, 1.2, 1), Vector3.new(-1.5, 2.6, 0), skin),
		RightUpperArm = bp("RightUpperArm", Vector3.new(1, 1.2, 1), Vector3.new(1.5, 3.8, 0), shirt),
		RightLowerArm = bp("RightLowerArm", Vector3.new(1, 1.2, 1), Vector3.new(1.5, 2.6, 0), skin),
		LeftUpperLeg = bp("LeftUpperLeg", Vector3.new(1, 1.2, 1), Vector3.new(-0.5, 1.8, 0), pants),
		LeftLowerLeg = bp("LeftLowerLeg", Vector3.new(1, 1.2, 1), Vector3.new(-0.5, 0.6, 0), pants),
		RightUpperLeg = bp("RightUpperLeg", Vector3.new(1, 1.2, 1), Vector3.new(0.5, 1.8, 0), pants),
		RightLowerLeg = bp("RightLowerLeg", Vector3.new(1, 1.2, 1), Vector3.new(0.5, 0.6, 0), pants),
	}
	local function joint(name, p0, p1, pivot)
		local j = Instance.new("Motor6D")
		j.Name = name
		j.Part0 = p0
		j.Part1 = p1
		j.C0 = p0.CFrame:Inverse() * CFrame.new(pivot)
		j.C1 = p1.CFrame:Inverse() * CFrame.new(pivot)
		j.Parent = p1
	end
	joint("Root", hrp, lower, Vector3.new(0, 2.6, 0))
	joint("Waist", lower, upper, Vector3.new(0, 2.8, 0))
	joint("Neck", upper, head, Vector3.new(0, 4.4, 0))
	joint("LeftShoulder", upper, parts.LeftUpperArm, Vector3.new(-1.5, 4.3, 0))
	joint("LeftElbow", parts.LeftUpperArm, parts.LeftLowerArm, Vector3.new(-1.5, 3.2, 0))
	joint("RightShoulder", upper, parts.RightUpperArm, Vector3.new(1.5, 4.3, 0))
	joint("RightElbow", parts.RightUpperArm, parts.RightLowerArm, Vector3.new(1.5, 3.2, 0))
	joint("LeftHip", lower, parts.LeftUpperLeg, Vector3.new(-0.5, 2.4, 0))
	joint("LeftKnee", parts.LeftUpperLeg, parts.LeftLowerLeg, Vector3.new(-0.5, 1.2, 0))
	joint("RightHip", lower, parts.RightUpperLeg, Vector3.new(0.5, 2.4, 0))
	joint("RightKnee", parts.RightUpperLeg, parts.RightLowerLeg, Vector3.new(0.5, 1.2, 0))
	local hum = Instance.new("Humanoid")
	hum.Parent = m
	m.PrimaryPart = hrp
	return m
end

local function prepare(model)
	for _, d in ipairs(model:GetDescendants()) do
		if d:IsA("BasePart") then
			d.CanCollide = false
			d.CanTouch = false
			d.CanQuery = false
			d.Massless = true
			d.Anchored = false
		elseif d:IsA("Script") or d:IsA("LocalScript") then
			d:Destroy()
		end
	end
	local hrp = model:FindFirstChild("HumanoidRootPart")
	hrp.Anchored = true
	hrp.Transparency = 1
	model.PrimaryPart = hrp
	local hum = model:FindFirstChildOfClass("Humanoid")
	if hum then
		hum.DisplayDistanceType = Enum.HumanoidDisplayDistanceType.None
		hum.HealthDisplayType = Enum.HumanoidHealthDisplayType.AlwaysOff
		hum.BreakJointsOnDeath = false
		hum.RequiresNeck = false
	end
	pcall(function()
		model:ScaleTo(Config.NpcScale)
	end)
	-- Maße merken: Fußsohle und Scheitel relativ zur Hüfte
	local cf, size = model:GetBoundingBox()
	model:SetAttribute("FootOffset", hrp.Position.Y - (cf.Position.Y - size.Y / 2))
	model:SetAttribute("HeadTop", (cf.Position.Y + size.Y / 2) - hrp.Position.Y)
	CollectionService:AddTag(model, Npc.TAG)
end

function Npc.BuildTemplates(count)
	local folder = Instance.new("Folder")
	folder.Name = "Leute"
	local rng = Random.new(11)
	for i = 1, count do
		local skin = SKIN[rng:NextInteger(1, #SKIN)]
		local shirt = SHIRTS[rng:NextInteger(1, #SHIRTS)]
		local pants = PANTS[rng:NextInteger(1, #PANTS)]
		local short = rng:NextNumber() < 0.4
		local model
		local ok = pcall(function()
			local desc = Instance.new("HumanoidDescription")
			desc.HeadColor = skin
			desc.TorsoColor = shirt
			desc.LeftArmColor = short and skin or shirt
			desc.RightArmColor = short and skin or shirt
			desc.LeftLegColor = pants
			desc.RightLegColor = pants
			desc.HairAccessory = HAIR[rng:NextInteger(1, #HAIR)]
			model = Players:CreateHumanoidModelFromDescription(desc, Enum.HumanoidRigType.R15)
		end)
		if not ok or not model then
			ok = pcall(function()
				local desc = Instance.new("HumanoidDescription")
				desc.HeadColor = skin
				desc.TorsoColor = shirt
				desc.LeftArmColor = shirt
				desc.RightArmColor = shirt
				desc.LeftLegColor = pants
				desc.RightLegColor = pants
				model = Players:CreateHumanoidModelFromDescription(desc, Enum.HumanoidRigType.R15)
			end)
		end
		if not ok or not model then
			model = fallbackRig(skin, shirt, pants)
		end
		model.Name = "Person" .. i
		prepare(model)
		model.Parent = folder
	end
	folder.Parent = ReplicatedStorage
	return folder
end

-- Klont eine zufällige Person
function Npc.Random(rng)
	local folder = ReplicatedStorage:FindFirstChild("Leute")
	local list = folder and folder:GetChildren() or {}
	if #list == 0 then
		return nil
	end
	local r = rng and rng:NextInteger(1, #list) or math.random(1, #list)
	return list[r]:Clone()
end

-- Setzt eine Person auf den Fahrersitz eines Ausstellungsautos (verschweißt)
function Npc.SeatInCar(person, car)
	local root = car.PrimaryPart
	local hrp = person.PrimaryPart
	local headTop = person:GetAttribute("HeadTop") or 2
	local roof = car:GetAttribute("RoofInner") or 2
	local y = roof - headTop - 0.08
	for _, w in ipairs(hrp:GetChildren()) do
		if w:IsA("WeldConstraint") then
			w:Destroy()
		end
	end
	hrp.Anchored = false
	hrp.CFrame = root.CFrame * CFrame.new(car:GetAttribute("SeatX") or -1.3, y, (car:GetAttribute("SeatZ") or 0) + 0.35)
	local w = Instance.new("WeldConstraint")
	w.Part0 = root
	w.Part1 = hrp
	w.Parent = hrp
	person.Name = "Fahrer"
	person:SetAttribute("Pose", "sit")
	person.Parent = car
end

-- Lässt die Person neben dem Auto stehen (verankert)
function Npc.StandAt(person, groundCF, parent)
	local hrp = person.PrimaryPart
	for _, w in ipairs(hrp:GetChildren()) do
		if w:IsA("WeldConstraint") then
			w:Destroy()
		end
	end
	hrp.Anchored = true
	hrp.CFrame = groundCF * CFrame.new(0, person:GetAttribute("FootOffset") or 2.5, 0)
	person:SetAttribute("Pose", "stand")
	person.Parent = parent
end

return Npc
