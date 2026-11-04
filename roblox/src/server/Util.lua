-- Bau-Helfer für Teile, Schilder und Bewegungen
-- ModuleScript "Util" in ServerScriptService

local RunService = game:GetService("RunService")

local Util = {}

-- Erstellt ein verankertes Part. Alle Felder in props werden gesetzt.
function Util.part(props)
	local p = Instance.new("Part")
	p.Anchored = true
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	if props.Shape then
		p.Shape = props.Shape
	end
	for k, v in pairs(props) do
		if k ~= "Parent" and k ~= "Shape" then
			p[k] = v
		end
	end
	p.Parent = props.Parent
	return p
end

function Util.wedge(props)
	local p = Instance.new("WedgePart")
	p.Anchored = true
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	for k, v in pairs(props) do
		if k ~= "Parent" then
			p[k] = v
		end
	end
	p.Parent = props.Parent
	return p
end

-- Text auf einer Fläche eines Parts
function Util.textGui(parentPart, face, text, color, bg, font)
	local sg = Instance.new("SurfaceGui")
	sg.Face = face
	sg.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
	sg.PixelsPerStud = 25
	sg.LightInfluence = 0
	sg.Parent = parentPart
	local tl = Instance.new("TextLabel")
	tl.Size = UDim2.fromScale(1, 1)
	tl.BackgroundTransparency = bg and 0 or 1
	tl.BackgroundColor3 = bg or Color3.new(0, 0, 0)
	tl.Font = font or Enum.Font.GothamBlack
	tl.TextScaled = true
	tl.TextColor3 = color
	tl.Text = text
	tl.Parent = sg
	local pad = Instance.new("UIPadding")
	pad.PaddingLeft = UDim.new(0.03, 0)
	pad.PaddingRight = UDim.new(0.03, 0)
	pad.PaddingTop = UDim.new(0.08, 0)
	pad.PaddingBottom = UDim.new(0.08, 0)
	pad.Parent = tl
	return tl
end

-- Schwebendes Info-Schild
function Util.billboard(adornee, text, offsetY)
	local bb = Instance.new("BillboardGui")
	bb.Name = "Info"
	bb.Size = UDim2.fromOffset(260, 64)
	bb.StudsOffset = Vector3.new(0, offsetY or 5, 0)
	bb.AlwaysOnTop = true
	bb.MaxDistance = 90
	bb.Adornee = adornee
	local tl = Instance.new("TextLabel")
	tl.Size = UDim2.fromScale(1, 1)
	tl.BackgroundColor3 = Color3.fromRGB(20, 22, 28)
	tl.BackgroundTransparency = 0.25
	tl.TextColor3 = Color3.new(1, 1, 1)
	tl.Font = Enum.Font.GothamBold
	tl.TextScaled = true
	tl.Text = text
	tl.Parent = bb
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, 10)
	c.Parent = tl
	local pad = Instance.new("UIPadding")
	pad.PaddingLeft = UDim.new(0, 8)
	pad.PaddingRight = UDim.new(0, 8)
	pad.PaddingTop = UDim.new(0, 4)
	pad.PaddingBottom = UDim.new(0, 4)
	pad.Parent = tl
	bb.Parent = adornee
	return tl
end

function Util.light(parentPart, kind, props)
	local l = Instance.new(kind or "PointLight")
	for k, v in pairs(props or {}) do
		l[k] = v
	end
	l.Parent = parentPart
	return l
end

function Util.lookCF(pos, dir)
	return CFrame.lookAt(pos, pos + dir)
end

-- Bewegt ein Modell weich von A nach B (blockiert, bis fertig)
function Util.moveModel(model, fromCF, toCF, duration)
	local t0 = os.clock()
	while model.Parent do
		local a = math.clamp((os.clock() - t0) / duration, 0, 1)
		local e = a < 0.5 and 2 * a * a or 1 - ((-2 * a + 2) ^ 2) / 2
		model:PivotTo(fromCF:Lerp(toCF, e))
		if a >= 1 then
			break
		end
		RunService.Heartbeat:Wait()
	end
end

return Util
