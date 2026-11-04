-- Chiptuning-Firma: Benutzeroberfläche
-- LocalScript "ChiptuningClient" in StarterPlayer > StarterPlayerScripts

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")
local ContextActionService = game:GetService("ContextActionService")
local MarketplaceService = game:GetService("MarketplaceService")

local player = Players.LocalPlayer
local Config = require(ReplicatedStorage:WaitForChild("Config"))
local Remotes = ReplicatedStorage:WaitForChild("Remotes")
local OpenTuning = Remotes:WaitForChild("OpenTuning")
local FinishTuning = Remotes:WaitForChild("FinishTuning")
local CancelTuning = Remotes:WaitForChild("CancelTuning")
local TuneResult = Remotes:WaitForChild("TuneResult")
local OpenShop = Remotes:WaitForChild("OpenShop")
local BuyUpgrade = Remotes:WaitForChild("BuyUpgrade")
local Notify = Remotes:WaitForChild("Notify")
local RequestTestDrive = Remotes:WaitForChild("RequestTestDrive")
local RequestCompanyCar = Remotes:WaitForChild("RequestCompanyCar")
local AdminAction = Remotes:WaitForChild("AdminAction")

local C = {
	Bg = Color3.fromRGB(22, 24, 30),
	Panel = Color3.fromRGB(36, 39, 48),
	Accent = Color3.fromRGB(255, 140, 0),
	Text = Color3.fromRGB(240, 240, 245),
	Muted = Color3.fromRGB(160, 165, 175),
	Green = Color3.fromRGB(60, 200, 90),
	Yellow = Color3.fromRGB(240, 200, 40),
	Red = Color3.fromRGB(220, 60, 60),
	Gray = Color3.fromRGB(80, 84, 94),
}

local function make(class, props, children)
	local inst = Instance.new(class)
	for k, v in pairs(props or {}) do
		if k ~= "Parent" then
			inst[k] = v
		end
	end
	for _, child in ipairs(children or {}) do
		child.Parent = inst
	end
	if props and props.Parent then
		inst.Parent = props.Parent
	end
	return inst
end

local function corner(r)
	return make("UICorner", { CornerRadius = UDim.new(0, r or 10) })
end

local function stroke(color, thickness)
	return make("UIStroke", { Color = color, Thickness = thickness or 2, ApplyStrokeMode = Enum.ApplyStrokeMode.Border })
end

local function label(props)
	props.BackgroundTransparency = props.BackgroundTransparency or 1
	props.Font = props.Font or Enum.Font.GothamBold
	props.TextColor3 = props.TextColor3 or C.Text
	props.TextSize = props.TextSize or 18
	return make("TextLabel", props)
end

local function button(props)
	props.Font = props.Font or Enum.Font.GothamBlack
	props.TextColor3 = props.TextColor3 or Color3.new(1, 1, 1)
	props.TextSize = props.TextSize or 20
	props.BackgroundColor3 = props.BackgroundColor3 or C.Accent
	props.AutoButtonColor = true
	return make("TextButton", props, { corner(10) })
end

local gui = make("ScreenGui", {
	Name = "ChiptuningUI",
	ResetOnSpawn = false,
	ZIndexBehavior = Enum.ZIndexBehavior.Sibling,
	Parent = player:WaitForChild("PlayerGui"),
})

-- Fenster auf kleinen Bildschirmen (Handy) verkleinern
local scales = {}
local function updateScale()
	local cam = workspace.CurrentCamera
	if not cam then
		return
	end
	local v = cam.ViewportSize
	local s = math.clamp(math.min(v.X / 640, v.Y / 470), 0.55, 1)
	for _, sc in ipairs(scales) do
		sc.Scale = s
	end
end
local function scaled(frame)
	table.insert(scales, make("UIScale", { Parent = frame }))
	updateScale()
	return frame
end
task.defer(function()
	updateScale()
	if workspace.CurrentCamera then
		workspace.CurrentCamera:GetPropertyChangedSignal("ViewportSize"):Connect(updateScale)
	end
end)

------------------------------------------------------------------------
-- Meldungen (Toasts)
------------------------------------------------------------------------
local toastHolder = make("Frame", {
	Size = UDim2.fromOffset(340, 300),
	Position = UDim2.new(1, -12, 0, 70),
	AnchorPoint = Vector2.new(1, 0),
	BackgroundTransparency = 1,
	Parent = gui,
}, {
	make("UIListLayout", {
		Padding = UDim.new(0, 6),
		HorizontalAlignment = Enum.HorizontalAlignment.Right,
		SortOrder = Enum.SortOrder.LayoutOrder,
	}),
})
local toastCount = 0

local function toast(text, kind)
	toastCount += 1
	local col = (kind == "good" and C.Green) or (kind == "bad" and C.Red) or C.Accent
	local t = label({
		Size = UDim2.new(1, 0, 0, 44),
		BackgroundColor3 = C.Bg,
		BackgroundTransparency = 0.1,
		Font = Enum.Font.Gotham,
		TextSize = 16,
		TextWrapped = true,
		Text = text,
		LayoutOrder = toastCount,
		Parent = toastHolder,
	})
	corner(8).Parent = t
	stroke(col, 2).Parent = t
	make("UIPadding", { PaddingLeft = UDim.new(0, 10), PaddingRight = UDim.new(0, 10), Parent = t })
	task.delay(4, function()
		local tw = TweenService:Create(t, TweenInfo.new(0.4), { BackgroundTransparency = 1, TextTransparency = 1 })
		tw:Play()
		tw.Completed:Wait()
		t:Destroy()
	end)
end

Notify.OnClientEvent:Connect(toast)

------------------------------------------------------------------------
-- Shop
------------------------------------------------------------------------
local shopWin = make("Frame", {
	Name = "Shop",
	Size = UDim2.fromOffset(540, 470),
	Position = UDim2.fromScale(0.5, 0.5),
	AnchorPoint = Vector2.new(0.5, 0.5),
	BackgroundColor3 = C.Bg,
	Visible = false,
	Parent = gui,
}, { corner(14), stroke(C.Accent, 2) })
scaled(shopWin)

label({
	Size = UDim2.new(1, -70, 0, 50),
	Position = UDim2.fromOffset(18, 4),
	Text = "🛠️ Shop",
	TextSize = 24,
	TextXAlignment = Enum.TextXAlignment.Left,
	Parent = shopWin,
})
local shopClose = button({
	Size = UDim2.fromOffset(40, 40),
	Position = UDim2.new(1, -50, 0, 10),
	Text = "X",
	BackgroundColor3 = C.Gray,
	Parent = shopWin,
})
shopClose.Activated:Connect(function()
	shopWin.Visible = false
end)

local function scrollList(visible)
	return make("ScrollingFrame", {
		Size = UDim2.new(1, -24, 1, -122),
		Position = UDim2.fromOffset(12, 110),
		BackgroundTransparency = 1,
		BorderSizePixel = 0,
		CanvasSize = UDim2.new(),
		AutomaticCanvasSize = Enum.AutomaticSize.Y,
		ScrollBarThickness = 6,
		Visible = visible,
		Parent = shopWin,
	}, {
		make("UIListLayout", { Padding = UDim.new(0, 8), SortOrder = Enum.SortOrder.LayoutOrder }),
	})
end

local list = scrollList(true) -- Werkstatt-Upgrades (Spielgeld)
local robuxList = scrollList(false) -- Robux-Artikel

local tabUpgrades = button({
	Size = UDim2.new(0.5, -18, 0, 40),
	Position = UDim2.fromOffset(12, 58),
	Text = "🔧 Werkstatt",
	TextSize = 18,
	Parent = shopWin,
})
local tabRobux = button({
	Size = UDim2.new(0.5, -18, 0, 40),
	Position = UDim2.new(0.5, 6, 0, 58),
	Text = "💎 Robux-Shop",
	TextSize = 18,
	Parent = shopWin,
})

local function showTab(name)
	local robux = name == "robux"
	list.Visible = not robux
	robuxList.Visible = robux
	tabUpgrades.BackgroundColor3 = robux and C.Gray or C.Accent
	tabRobux.BackgroundColor3 = robux and C.Accent or C.Gray
end
tabUpgrades.Activated:Connect(function()
	showTab("upgrades")
end)
tabRobux.Activated:Connect(function()
	showTab("robux")
end)
showTab("upgrades")

local function shopRow(parent, order, title, desc)
	local row = make("Frame", {
		Size = UDim2.new(1, -10, 0, 70),
		BackgroundColor3 = C.Panel,
		LayoutOrder = order,
		Parent = parent,
	}, { corner(10) })
	label({
		Size = UDim2.new(1, -160, 0, 26),
		Position = UDim2.fromOffset(12, 6),
		Text = title,
		TextSize = 18,
		TextXAlignment = Enum.TextXAlignment.Left,
		Parent = row,
	})
	label({
		Size = UDim2.new(1, -160, 0, 34),
		Position = UDim2.fromOffset(12, 30),
		Text = desc,
		Font = Enum.Font.Gotham,
		TextSize = 14,
		TextColor3 = C.Muted,
		TextWrapped = true,
		TextXAlignment = Enum.TextXAlignment.Left,
		TextYAlignment = Enum.TextYAlignment.Top,
		Parent = row,
	})
	return button({
		Size = UDim2.fromOffset(130, 44),
		Position = UDim2.new(1, -142, 0.5, 0),
		AnchorPoint = Vector2.new(0, 0.5),
		Text = "",
		TextSize = 18,
		Parent = row,
	})
end

local function sectionTitle(parent, order, text)
	label({
		Size = UDim2.new(1, -10, 0, 28),
		Text = text,
		TextSize = 17,
		TextColor3 = C.Yellow,
		TextXAlignment = Enum.TextXAlignment.Left,
		LayoutOrder = order,
		Parent = parent,
	})
end

local rows = {}
for i, up in ipairs(Config.Upgrades) do
	local btn = shopRow(list, i, up.Name, up.Desc)
	btn.Text = Config.Format(up.Price) .. " €"
	btn.Activated:Connect(function()
		if not player:GetAttribute("Upg_" .. up.Id) then
			BuyUpgrade:FireServer(up.Id)
		end
	end)
	rows[up.Id] = btn
end

------------------------------------------------------------------------
-- Robux-Artikel
------------------------------------------------------------------------
local robuxItems = {} -- { Kind, Def, Btn, Price }

local function robuxPriceText(item)
	return "R$ " .. tostring(item.Price or item.Def.PriceHint)
end

sectionTitle(robuxList, 0, "Game Passes – einmal kaufen, für immer behalten")
for i, pass in ipairs(Config.GamePasses) do
	local btn = shopRow(robuxList, i, pass.Name, pass.Desc)
	table.insert(robuxItems, { Kind = "pass", Def = pass, Btn = btn })
end
sectionTitle(robuxList, 100, "Geldpakete – beliebig oft kaufbar")
for i, prod in ipairs(Config.Products) do
	local btn = shopRow(robuxList, 100 + i, prod.Name, prod.Desc)
	table.insert(robuxItems, { Kind = "product", Def = prod, Btn = btn })
end

local function refreshRobux()
	for _, item in ipairs(robuxItems) do
		local btn = item.Btn
		if item.Def.Id == 0 then
			btn.Text = "Bald verfügbar"
			btn.TextSize = 15
			btn.BackgroundColor3 = C.Gray
			btn.AutoButtonColor = false
		elseif item.Kind == "pass" and player:GetAttribute("Pass_" .. item.Def.Key) then
			btn.Text = "✔ Aktiv"
			btn.TextSize = 18
			btn.BackgroundColor3 = C.Gray
			btn.AutoButtonColor = false
		else
			btn.Text = robuxPriceText(item)
			btn.TextSize = 18
			btn.BackgroundColor3 = C.Green
			btn.AutoButtonColor = true
		end
	end
end

for _, item in ipairs(robuxItems) do
	item.Btn.Activated:Connect(function()
		local id = item.Def.Id
		if id == 0 then
			toast("Dieser Artikel ist noch nicht eingerichtet.", "info")
			return
		end
		if item.Kind == "pass" then
			if not player:GetAttribute("Pass_" .. item.Def.Key) then
				MarketplaceService:PromptGamePassPurchase(player, id)
			end
		else
			MarketplaceService:PromptProductPurchase(player, id)
		end
	end)
	-- Echten Preis aus dem Creator Hub holen
	if item.Def.Id ~= 0 then
		task.spawn(function()
			local infoType = item.Kind == "pass" and Enum.InfoType.GamePass or Enum.InfoType.Product
			local ok, info = pcall(function()
				return MarketplaceService:GetProductInfo(item.Def.Id, infoType)
			end)
			if ok and info and info.PriceInRobux then
				item.Price = info.PriceInRobux
				refreshRobux()
			end
		end)
	end
end
refreshRobux()
player.AttributeChanged:Connect(refreshRobux)

local function currentMoney()
	local ls = player:FindFirstChild("leaderstats")
	local geld = ls and ls:FindFirstChild("Geld")
	return geld and geld.Value or 0
end

local function refreshShop()
	local money = currentMoney()
	for _, up in ipairs(Config.Upgrades) do
		local btn = rows[up.Id]
		if player:GetAttribute("Upg_" .. up.Id) then
			btn.Text = "✔ Gekauft"
			btn.BackgroundColor3 = C.Gray
			btn.AutoButtonColor = false
		elseif up.Requires and not player:GetAttribute("Upg_" .. up.Requires) then
			btn.Text = "🔒 " .. Config.Format(up.Price) .. " €"
			btn.BackgroundColor3 = C.Gray
			btn.AutoButtonColor = false
		elseif money >= up.Price then
			btn.Text = Config.Format(up.Price) .. " €"
			btn.BackgroundColor3 = C.Green
			btn.AutoButtonColor = true
		else
			btn.Text = Config.Format(up.Price) .. " €"
			btn.BackgroundColor3 = C.Red
			btn.AutoButtonColor = true
		end
	end
end
player.AttributeChanged:Connect(refreshShop)

local tuneWin -- vorwärts deklariert

local function openShop(tab)
	refreshShop()
	refreshRobux()
	if tuneWin and tuneWin.Visible then
		return
	end
	showTab(tab or "upgrades")
	shopWin.Visible = true
end
OpenShop.OnClientEvent:Connect(function()
	openShop("upgrades")
end)

------------------------------------------------------------------------
-- HUD (Geld, Ruf, Shop-Knopf, Hinweis)
------------------------------------------------------------------------
local hud = make("Frame", {
	Size = UDim2.fromOffset(330, 46),
	Position = UDim2.new(0.5, 0, 0, 8),
	AnchorPoint = Vector2.new(0.5, 0),
	BackgroundColor3 = C.Bg,
	BackgroundTransparency = 0.15,
	Parent = gui,
}, { corner(12) })
local moneyLabel = label({ Size = UDim2.new(0.55, 0, 1, 0), Text = "💰 0 €", TextSize = 22, TextColor3 = C.Green, Parent = hud })
local repLabel = label({ Size = UDim2.new(0.45, 0, 1, 0), Position = UDim2.fromScale(0.55, 0), Text = "⭐ Ruf 0", TextSize = 20, TextColor3 = C.Yellow, Parent = hud })
local wrenchLabel = label({
	Size = UDim2.fromOffset(150, 26),
	Position = UDim2.new(0.5, 0, 0, 58),
	AnchorPoint = Vector2.new(0.5, 0),
	BackgroundColor3 = C.Bg,
	BackgroundTransparency = 0.3,
	Text = "🔧 0/12",
	TextSize = 16,
	TextColor3 = Color3.fromRGB(255, 200, 40),
	Parent = gui,
})
corner(8).Parent = wrenchLabel
local function updateWrenchLabel()
	local found = player:GetAttribute("Found") or ""
	local n = 0
	for _ in found:gmatch("%d+") do
		n += 1
	end
	wrenchLabel.Text = ("🔧 %d/12 Schlüssel"):format(n)
end
player:GetAttributeChangedSignal("Found"):Connect(updateWrenchLabel)
updateWrenchLabel()

local shopButton = button({
	Size = UDim2.fromOffset(120, 46),
	Position = UDim2.new(0, 12, 0.5, 0),
	AnchorPoint = Vector2.new(0, 0.5),
	Text = "🛠️ Shop",
	Parent = gui,
})
shopButton.Activated:Connect(function()
	if shopWin.Visible then
		shopWin.Visible = false
	else
		openShop("upgrades")
	end
end)

local robuxButton = button({
	Size = UDim2.fromOffset(120, 46),
	Position = UDim2.new(0, 12, 0.5, 56),
	AnchorPoint = Vector2.new(0, 0.5),
	Text = "💎 Robux",
	BackgroundColor3 = Color3.fromRGB(0, 170, 90),
	Parent = gui,
})
robuxButton.Activated:Connect(function()
	openShop("robux")
end)

local carButton = button({
	Size = UDim2.fromOffset(120, 46),
	Position = UDim2.new(0, 12, 0.5, 112),
	AnchorPoint = Vector2.new(0, 0.5),
	Text = "🚗 Auto",
	BackgroundColor3 = Color3.fromRGB(40, 110, 220),
	Parent = gui,
})
carButton.Activated:Connect(function()
	RequestCompanyCar:FireServer()
end)

-- Test-Knöpfe (nur für Admins: Studio, Besitzer des Spiels)
local adminFrame = make("Frame", {
	Size = UDim2.fromOffset(120, 100),
	Position = UDim2.new(0, 12, 0.5, 145),
	BackgroundTransparency = 1,
	Visible = false,
	Parent = gui,
}, { make("UIListLayout", { Padding = UDim.new(0, 6), SortOrder = Enum.SortOrder.LayoutOrder }) })
local moneyBtn = button({ Size = UDim2.fromOffset(120, 38), Text = "🧪 +100.000 €", TextSize = 15, BackgroundColor3 = Color3.fromRGB(120, 60, 170), LayoutOrder = 1, Parent = adminFrame })
local repBtn = button({ Size = UDim2.fromOffset(120, 38), Text = "🧪 +50 Ruf", TextSize = 15, BackgroundColor3 = Color3.fromRGB(120, 60, 170), LayoutOrder = 2, Parent = adminFrame })
moneyBtn.Activated:Connect(function()
	AdminAction:FireServer("money")
end)
repBtn.Activated:Connect(function()
	AdminAction:FireServer("rep")
end)
local function updateAdmin()
	adminFrame.Visible = player:GetAttribute("Admin") == true
end
player:GetAttributeChangedSignal("Admin"):Connect(updateAdmin)
updateAdmin()

local hint = label({
	Size = UDim2.new(0, 560, 0, 34),
	Position = UDim2.new(0.5, 0, 1, -70),
	AnchorPoint = Vector2.new(0.5, 1),
	BackgroundColor3 = C.Bg,
	BackgroundTransparency = 0.25,
	Font = Enum.Font.Gotham,
	TextSize = 16,
	Text = "Kunden kommen zu deinen Hebebühnen: hingehen und [E] drücken. Mit „🚗 Auto“ fährst du los!",
	Parent = gui,
})
corner(8).Parent = hint
task.delay(25, function()
	TweenService:Create(hint, TweenInfo.new(1), { BackgroundTransparency = 1, TextTransparency = 1 }):Play()
end)

task.spawn(function()
	local ls = player:WaitForChild("leaderstats")
	local geld = ls:WaitForChild("Geld")
	local ruf = ls:WaitForChild("Ruf")
	local function update()
		moneyLabel.Text = "💰 " .. Config.Format(geld.Value) .. " €"
		repLabel.Text = "⭐ Ruf " .. ruf.Value
		refreshShop()
	end
	geld.Changed:Connect(update)
	ruf.Changed:Connect(update)
	update()
end)

------------------------------------------------------------------------
-- Tuning-Fenster
------------------------------------------------------------------------
tuneWin = make("Frame", {
	Name = "Tuning",
	Size = UDim2.fromOffset(580, 400),
	Position = UDim2.fromScale(0.5, 0.5),
	AnchorPoint = Vector2.new(0.5, 0.5),
	BackgroundColor3 = C.Bg,
	Visible = false,
	Parent = gui,
}, { corner(14), stroke(C.Accent, 2) })
scaled(tuneWin)

-- Spielansicht
local playFrame = make("Frame", { Size = UDim2.fromScale(1, 1), BackgroundTransparency = 1, Parent = tuneWin })
local titleLabel = label({
	Size = UDim2.new(1, -80, 0, 40),
	Position = UDim2.fromOffset(20, 10),
	TextSize = 24,
	TextXAlignment = Enum.TextXAlignment.Left,
	Text = "",
	Parent = playFrame,
})
local infoLabel = label({
	Size = UDim2.new(1, -40, 0, 50),
	Position = UDim2.fromOffset(20, 50),
	Font = Enum.Font.Gotham,
	TextSize = 17,
	TextColor3 = C.Muted,
	TextWrapped = true,
	TextXAlignment = Enum.TextXAlignment.Left,
	Text = "",
	Parent = playFrame,
})
local cancelBtn = button({
	Size = UDim2.fromOffset(40, 40),
	Position = UDim2.new(1, -50, 0, 10),
	Text = "X",
	BackgroundColor3 = C.Gray,
	Parent = playFrame,
})
local mapLabel = label({
	Size = UDim2.new(1, -40, 0, 30),
	Position = UDim2.fromOffset(20, 112),
	TextSize = 20,
	TextColor3 = C.Accent,
	Text = "",
	Parent = playFrame,
})
local bar = make("Frame", {
	Size = UDim2.new(1, -60, 0, 44),
	Position = UDim2.fromOffset(30, 160),
	BackgroundColor3 = Color3.fromRGB(90, 30, 30),
	ClipsDescendants = true,
	Parent = playFrame,
}, { corner(8) })
local yellowZone = make("Frame", { BackgroundColor3 = C.Yellow, BorderSizePixel = 0, Parent = bar })
local greenZone = make("Frame", { BackgroundColor3 = C.Green, BorderSizePixel = 0, Parent = bar })
local flashFill = make("Frame", { BackgroundColor3 = Color3.fromRGB(80, 170, 255), BorderSizePixel = 0, Visible = false, Size = UDim2.fromScale(0, 1), Parent = bar })
-- Die Nadel liegt in einem eigenen Rahmen über dem Balken, damit sie nicht abgeschnitten wird
local needleTrack = make("Frame", {
	Size = UDim2.new(1, -60, 0, 44),
	Position = UDim2.fromOffset(30, 160),
	BackgroundTransparency = 1,
	ZIndex = 3,
	Parent = playFrame,
})
local needle = make("Frame", {
	Size = UDim2.new(0, 6, 1, 16),
	AnchorPoint = Vector2.new(0.5, 0.5),
	Position = UDim2.fromScale(0, 0.5),
	BackgroundColor3 = Color3.new(1, 1, 1),
	BorderSizePixel = 0,
	ZIndex = 3,
	Parent = needleTrack,
}, { stroke(Color3.new(0, 0, 0), 1) })
local feedback = label({
	Size = UDim2.new(1, -40, 0, 36),
	Position = UDim2.fromOffset(20, 214),
	TextSize = 26,
	Text = "",
	Parent = playFrame,
})
local stopBtn = button({
	Size = UDim2.fromOffset(280, 64),
	Position = UDim2.new(0.5, 0, 0, 268),
	AnchorPoint = Vector2.new(0.5, 0),
	Text = "STOPP  [Leertaste]",
	TextSize = 24,
	Parent = playFrame,
})
local helpLabel = label({
	Size = UDim2.new(1, -40, 0, 30),
	Position = UDim2.fromOffset(20, 348),
	Font = Enum.Font.Gotham,
	TextSize = 14,
	TextColor3 = C.Muted,
	TextWrapped = true,
	Text = "",
	Parent = playFrame,
})

-- Memory: vier Steuergeräte-Felder
local PAD_COLORS = { Color3.fromRGB(220, 60, 60), Color3.fromRGB(60, 160, 230), Color3.fromRGB(60, 200, 100), Color3.fromRGB(240, 190, 40) }
local PAD_CODES = { "P0300", "P0171", "P0234", "P0420" }
local padFrame = make("Frame", {
	Size = UDim2.new(1, -60, 0, 70),
	Position = UDim2.fromOffset(30, 152),
	BackgroundTransparency = 1,
	Visible = false,
	Parent = playFrame,
}, { make("UIListLayout", { FillDirection = Enum.FillDirection.Horizontal, Padding = UDim.new(0, 10), HorizontalAlignment = Enum.HorizontalAlignment.Center }) })
local pads = {}
for i = 1, 4 do
	local pad = button({
		Size = UDim2.new(0.25, -8, 1, 0),
		Text = PAD_CODES[i] .. "\n[" .. i .. "]",
		TextSize = 17,
		BackgroundColor3 = PAD_COLORS[i]:Lerp(Color3.new(0, 0, 0), 0.6),
		LayoutOrder = i,
		Parent = padFrame,
	})
	pads[i] = pad
end

-- Schaltblitze für den Prüfstandslauf
local ledFrame = make("Frame", {
	Size = UDim2.fromOffset(200, 14),
	Position = UDim2.new(0.5, 0, 0, 142),
	AnchorPoint = Vector2.new(0.5, 0),
	BackgroundTransparency = 1,
	Visible = false,
	Parent = playFrame,
}, { make("UIListLayout", { FillDirection = Enum.FillDirection.Horizontal, Padding = UDim.new(0, 8), HorizontalAlignment = Enum.HorizontalAlignment.Center }) })
local leds = {}
for i = 1, 6 do
	leds[i] = make("Frame", { Size = UDim2.fromOffset(24, 12), BackgroundColor3 = C.Gray, LayoutOrder = i, Parent = ledFrame }, { corner(6) })
end

-- Ergebnisansicht
local resultFrame = make("Frame", { Size = UDim2.fromScale(1, 1), BackgroundTransparency = 1, Visible = false, Parent = tuneWin })
local resTitle = label({ Size = UDim2.new(1, -40, 0, 50), Position = UDim2.fromOffset(20, 20), TextSize = 28, Text = "", Parent = resultFrame })
local resCar = label({ Size = UDim2.new(1, -40, 0, 28), Position = UDim2.fromOffset(20, 70), Font = Enum.Font.Gotham, TextSize = 18, TextColor3 = C.Muted, Text = "", Parent = resultFrame })
local resPower = label({ Size = UDim2.new(1, -40, 0, 34), Position = UDim2.fromOffset(20, 115), TextSize = 24, Text = "", Parent = resultFrame })
local resTorque = label({ Size = UDim2.new(1, -40, 0, 30), Position = UDim2.fromOffset(20, 152), TextSize = 20, TextColor3 = C.Muted, Text = "", Parent = resultFrame })
local resPay = label({ Size = UDim2.new(1, -40, 0, 40), Position = UDim2.fromOffset(20, 200), TextSize = 32, TextColor3 = C.Green, Text = "", Parent = resultFrame })
local resRep = label({ Size = UDim2.new(1, -40, 0, 30), Position = UDim2.fromOffset(20, 242), TextSize = 20, Text = "", Parent = resultFrame })
local doneBtn = button({
	Size = UDim2.fromOffset(200, 56),
	Position = UDim2.new(0.5, -8, 0, 300),
	AnchorPoint = Vector2.new(1, 0),
	Text = "Weiter",
	BackgroundColor3 = C.Gray,
	Parent = resultFrame,
})
local testDriveBtn = button({
	Size = UDim2.fromOffset(250, 56),
	Position = UDim2.new(0.5, 8, 0, 300),
	AnchorPoint = Vector2.new(0, 0),
	Text = "🏁 Probefahrt",
	TextSize = 18,
	BackgroundColor3 = C.Green,
	Parent = resultFrame,
})

------------------------------------------------------------------------
-- Tuning-Ablauf: drei Minispiele pro Auftrag
------------------------------------------------------------------------
local current = nil -- { Job, Round, Results, Phase, Game, S }
local holding = false

local function pingpong(x)
	return 1 - math.abs((x % 2) - 1)
end

local function placeNeedle(pos)
	needle.Position = UDim2.fromScale(math.clamp(pos, 0, 1), 0.5)
end

local function setZones(center, width)
	yellowZone.Position = UDim2.fromScale(center - width, 0)
	yellowZone.Size = UDim2.fromScale(width * 2, 1)
	greenZone.Position = UDim2.fromScale(center - width / 2, 0)
	greenZone.Size = UDim2.fromScale(width, 1)
end

local function unbindStop()
	ContextActionService:UnbindAction("ChiptuningStopp")
	ContextActionService:UnbindAction("ChiptuningPads")
	holding = false
end

local function closeTuning()
	current = nil
	tuneWin.Visible = false
	unbindStop()
end

local finishRound -- vorwärts

local GAMES = {}

-- 1) Nadel im grünen Bereich stoppen
GAMES.needle = {
	Help = "Stoppe die Nadel im grünen Bereich. Gelb ist okay, Rot lässt den Motor klopfen.",
	Button = "STOPP  [Leertaste]",
	Start = function(g, st)
		setZones(g.Zone, g.Width)
		st.T = math.random() * 2
		st.Pos = pingpong(st.T)
	end,
	Update = function(g, st, dt)
		st.T += dt * g.Speed
		st.Pos = pingpong(st.T)
		placeNeedle(st.Pos)
	end,
	Press = function(g, st)
		finishRound(Config.Score[Config.Rate(st.Pos, g.Zone, g.Width)])
	end,
}

-- 2) Ladedruck halten: gedrückt halten, Druck in der wandernden Zone halten
GAMES.hold = {
	Help = "Halte die Taste gedrückt, um Ladedruck aufzubauen. Bleib in der grünen Zone, bis die Zeit abläuft!",
	Button = "GAS HALTEN  [Leertaste]",
	Start = function(_g, st)
		st.T = 0
		st.P = 0.15
		st.Good = 0
		flashFill.Visible = true
		flashFill.Size = UDim2.fromScale(st.P, 1)
	end,
	Update = function(g, st, dt)
		st.T += dt
		local c = 0.5 + 0.28 * math.sin(st.T * g.Speed * 1.3) + 0.08 * math.sin(st.T * g.Speed * 3.1)
		local w = g.Width * 1.3
		setZones(c, w)
		st.P = math.clamp(st.P + (holding and 0.95 or -0.75) * dt, 0, 1)
		flashFill.Size = UDim2.fromScale(st.P, 1)
		placeNeedle(st.P)
		local d = math.abs(st.P - c)
		if d <= w / 2 then
			st.Good += dt
		elseif d <= w then
			st.Good += dt * 0.5
		end
		feedback.TextColor3 = C.Text
		feedback.Text = ("⏱ %.1f s"):format(math.max(0, g.Duration - st.T))
		if st.T >= g.Duration then
			finishRound(math.min(1, st.Good / (g.Duration * 0.75)))
		end
	end,
}

-- 3) Fehlercodes: Reihenfolge merken und nachdrücken
GAMES.memory = {
	Help = "Merke dir die Reihenfolge der aufleuchtenden Fehlercodes und drücke sie nach (Klick oder Tasten 1–4).",
	Start = function(_g, st)
		st.T = 0
		st.Showing = true
		st.Input = 0
		for i, pad in ipairs(pads) do
			pad.BackgroundColor3 = PAD_COLORS[i]:Lerp(Color3.new(0, 0, 0), 0.6)
		end
		feedback.TextColor3 = C.Text
		feedback.Text = "👀 Merken …"
	end,
	Update = function(g, st, dt)
		if not st.Showing then
			return
		end
		st.T += dt
		local step = 0.65
		local idx = math.floor(st.T / step) + 1
		local lit = (st.T % step) < 0.45 and g.Seq[idx] or nil
		for i, pad in ipairs(pads) do
			pad.BackgroundColor3 = (i == lit) and PAD_COLORS[i] or PAD_COLORS[i]:Lerp(Color3.new(0, 0, 0), 0.6)
		end
		if idx > #g.Seq then
			st.Showing = false
			feedback.Text = "👉 Jetzt du!"
		end
	end,
	Pad = function(g, st, i)
		if st.Showing then
			return
		end
		local pad = pads[i]
		pad.BackgroundColor3 = PAD_COLORS[i]
		task.delay(0.15, function()
			pad.BackgroundColor3 = PAD_COLORS[i]:Lerp(Color3.new(0, 0, 0), 0.6)
		end)
		if g.Seq[st.Input + 1] == i then
			st.Input += 1
			if st.Input >= #g.Seq then
				finishRound(1)
			end
		else
			finishRound(st.Input / #g.Seq * 0.9)
		end
	end,
}

-- 4) Prüfstandslauf: im grünen Drehzahlbereich hochschalten
GAMES.shift = {
	Help = "Die Drehzahl steigt: Schalte hoch, wenn die Schaltblitze grün sind! Zu spät = Begrenzer.",
	Button = "SCHALTEN  [Leertaste]",
	Start = function(_g, st)
		st.Pos = 0.05
		st.Gear = 1
		st.Scores = {}
		setZones(0.875, 0.1)
		ledFrame.Visible = true
	end,
	Update = function(g, st, dt)
		st.Pos += dt * (0.25 + st.Pos * 0.85) * g.Speed * (1 + st.Gear * 0.12)
		placeNeedle(st.Pos)
		local litCount = math.clamp(math.floor((st.Pos - 0.55) / 0.05), 0, 6)
		for i, led in ipairs(leds) do
			local on = i <= litCount
			local col = (i <= 2 and C.Green) or (i <= 4 and C.Yellow) or C.Red
			if st.Pos >= 0.825 and st.Pos <= 0.925 then
				col = C.Green -- Schaltpunkt: alle grün
			end
			led.BackgroundColor3 = on and col or C.Gray
		end
		feedback.TextColor3 = C.Text
		feedback.Text = ("Gang %d"):format(st.Gear)
		if st.Pos >= 1 then
			st.Scores[#st.Scores + 1] = 0
			feedback.Text = "💥 Begrenzer!"
			GAMES.shift.Next(g, st)
		end
	end,
	Press = function(g, st)
		local pos = st.Pos
		local sc = (math.abs(pos - 0.875) <= 0.05 and 1) or (math.abs(pos - 0.875) <= 0.1 and 0.6) or 0.2
		st.Scores[#st.Scores + 1] = sc
		GAMES.shift.Next(g, st)
	end,
	Next = function(_g, st)
		if #st.Scores >= 3 then
			local sum = 0
			for _, v in ipairs(st.Scores) do
				sum += v
			end
			finishRound(sum / #st.Scores)
		else
			st.Gear += 1
			st.Pos = 0.35 -- Drehzahl fällt nach dem Schalten
		end
	end,
}

local function setupRound()
	local job = current.Job
	local r = current.Round
	local g = job.Games[r]
	local game = GAMES[g.Type]
	current.Game = g
	current.S = {}
	current.Stopped = false
	mapLabel.Text = ("Schritt %d/%d: %s"):format(r, #job.Games, g.Name)
	helpLabel.Text = game.Help
	feedback.Text = ""
	local usesBar = g.Type ~= "memory"
	bar.Visible = usesBar
	needleTrack.Visible = usesBar
	needle.Visible = usesBar
	yellowZone.Visible = true
	greenZone.Visible = true
	flashFill.Visible = false
	padFrame.Visible = g.Type == "memory"
	ledFrame.Visible = false
	stopBtn.Visible = game.Button ~= nil
	stopBtn.Text = game.Button or ""
	holding = false
	game.Start(g, current.S)
end

finishRound = function(score)
	if not current or current.Stopped then
		return
	end
	current.Stopped = true
	local job, r = current.Job, current.Round
	current.Results[r] = score
	if score >= 0.8 then
		feedback.Text = "PERFEKT! 🔥"
		feedback.TextColor3 = C.Green
	elseif score >= 0.45 then
		feedback.Text = "Okay 👍"
		feedback.TextColor3 = C.Yellow
	else
		feedback.Text = "Daneben – Motor klopft! 💥"
		feedback.TextColor3 = C.Red
	end

	task.delay(0.9, function()
		if not current or current.Job ~= job then
			return
		end
		if r < #job.Games then
			current.Round = r + 1
			setupRound()
			return
		end
		-- Alles fertig: "Software aufspielen"
		current.Phase = "flash"
		stopBtn.Visible = false
		padFrame.Visible = false
		ledFrame.Visible = false
		bar.Visible = true
		needleTrack.Visible = false
		feedback.Text = ""
		helpLabel.Text = ""
		mapLabel.Text = "Software wird aufs Steuergerät geschrieben …"
		yellowZone.Visible = false
		greenZone.Visible = false
		flashFill.Size = UDim2.fromScale(0, 1)
		flashFill.Visible = true
		TweenService:Create(flashFill, TweenInfo.new(1.3, Enum.EasingStyle.Linear), { Size = UDim2.fromScale(1, 1) }):Play()
		task.wait(1.4)
		if current and current.Job == job then
			current.Phase = "wait"
			FinishTuning:FireServer(job.Id, current.Results)
		end
	end)
end

local function press()
	if not current or current.Phase ~= "play" or current.Stopped then
		return
	end
	local game = GAMES[current.Game.Type]
	if game.Press then
		game.Press(current.Game, current.S)
	end
end

local function padPressed(i)
	if not current or current.Phase ~= "play" or current.Stopped then
		return
	end
	local game = GAMES[current.Game.Type]
	if game.Pad then
		game.Pad(current.Game, current.S, i)
	end
end

stopBtn.Activated:Connect(press)
stopBtn.InputBegan:Connect(function(input)
	if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
		holding = true
	end
end)
stopBtn.InputEnded:Connect(function(input)
	if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
		holding = false
	end
end)
for i, pad in ipairs(pads) do
	pad.Activated:Connect(function()
		padPressed(i)
	end)
end

cancelBtn.Activated:Connect(function()
	if current and current.Phase == "play" then
		CancelTuning:FireServer(current.Job.Id)
		closeTuning()
	end
end)

doneBtn.Activated:Connect(closeTuning)
testDriveBtn.Activated:Connect(function()
	closeTuning()
	RequestTestDrive:FireServer()
end)

RunService.RenderStepped:Connect(function(dt)
	if current and current.Phase == "play" and not current.Stopped and current.Game then
		GAMES[current.Game.Type].Update(current.Game, current.S, dt)
	end
end)

OpenTuning.OnClientEvent:Connect(function(job)
	shopWin.Visible = false
	current = { Job = job, Round = 1, Results = {}, Phase = "play" }
	titleLabel.Text = "💻 ECU-Tuning · " .. job.StageName
	infoLabel.Text = ("%s – Serie: %d PS / %d Nm  →  Ziel: bis %d PS / %d Nm"):format(
		job.CarName,
		job.Hp,
		job.Nm,
		job.TargetHp,
		job.TargetNm
	)
	playFrame.Visible = true
	resultFrame.Visible = false
	tuneWin.Visible = true
	ContextActionService:BindActionAtPriority("ChiptuningStopp", function(_, state)
		if state == Enum.UserInputState.Begin then
			holding = true
			press()
		elseif state == Enum.UserInputState.End then
			holding = false
		end
		return Enum.ContextActionResult.Sink
	end, false, 3000, Enum.KeyCode.Space, Enum.KeyCode.ButtonA)
	ContextActionService:BindActionAtPriority("ChiptuningPads", function(_, state, input)
		if state == Enum.UserInputState.Begin then
			local map = { [Enum.KeyCode.One] = 1, [Enum.KeyCode.Two] = 2, [Enum.KeyCode.Three] = 3, [Enum.KeyCode.Four] = 4 }
			local i = map[input.KeyCode]
			if i then
				padPressed(i)
			end
		end
		return Enum.ContextActionResult.Sink
	end, false, 3000, Enum.KeyCode.One, Enum.KeyCode.Two, Enum.KeyCode.Three, Enum.KeyCode.Four)
	setupRound()
end)

TuneResult.OnClientEvent:Connect(function(res)
	unbindStop()
	current = { Phase = "result" }
	if res.Score >= 0.95 then
		resTitle.Text = "🔥 Perfekte Abstimmung!"
		resTitle.TextColor3 = C.Green
	elseif res.Score >= 0.55 then
		resTitle.Text = "👍 Gutes Ergebnis"
		resTitle.TextColor3 = C.Yellow
	else
		resTitle.Text = "⚠️ Motor läuft unrund …"
		resTitle.TextColor3 = C.Red
	end
	resCar.Text = res.CarName .. " · " .. res.StageName
	resPower.Text = ("Leistung: %d PS → %d PS"):format(res.Hp, res.NewHp)
	resTorque.Text = ("Drehmoment: %d Nm → %d Nm"):format(res.Nm, res.NewNm)
	resPay.Text = "+" .. Config.Format(res.Pay) .. " €"
	testDriveBtn.Visible = res.CanTestDrive == true
	testDriveBtn.Text = ("🏁 Probefahrt (+%s € Trinkgeld)"):format(Config.Format(res.Tip or 0))
	doneBtn.Position = res.CanTestDrive and UDim2.new(0.5, -8, 0, 300) or UDim2.new(0.5, 100, 0, 300)
	if res.RepDelta >= 0 then
		resRep.Text = "⭐ Ruf +" .. res.RepDelta
		resRep.TextColor3 = C.Yellow
	else
		resRep.Text = "⭐ Ruf " .. res.RepDelta .. " (Kunde unzufrieden)"
		resRep.TextColor3 = C.Red
	end
	playFrame.Visible = false
	resultFrame.Visible = true
	shopWin.Visible = false
	tuneWin.Visible = true
end)
