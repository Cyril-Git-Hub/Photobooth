$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
$outDir = Join-Path (Split-Path $PSScriptRoot -Parent) "assets/masques"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

function New-Canvas([int]$width, [int]$height) {
    $bitmap = [System.Drawing.Bitmap]::new($width * 2, $height * 2,
        [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $graphics.ScaleTransform(2, 2)
    $graphics.Clear([System.Drawing.Color]::Transparent)
    return ,@($bitmap, $graphics)
}

function Brush([int]$a, [int]$r, [int]$g, [int]$b) {
    [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb($a, $r, $g, $b))
}

function Pen([int]$a, [int]$r, [int]$g, [int]$b, [single]$width) {
    $pen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb($a, $r, $g, $b), $width)
    $pen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
    $pen
}

function RoundedPath([single]$x, [single]$y, [single]$width, [single]$height, [single]$radius) {
    $path = [System.Drawing.Drawing2D.GraphicsPath]::new()
    $diameter = 2 * $radius
    $path.AddArc($x, $y, $diameter, $diameter, 180, 90)
    $path.AddArc($x + $width - $diameter, $y, $diameter, $diameter, 270, 90)
    $path.AddArc($x + $width - $diameter, $y + $height - $diameter, $diameter, $diameter, 0, 90)
    $path.AddArc($x, $y + $height - $diameter, $diameter, $diameter, 90, 90)
    $path.CloseFigure()
    $path
}

function SaveCanvas($bitmap, $graphics, [string]$name) {
    $graphics.Dispose()
    $bitmap.Save((Join-Path $outDir $name), [System.Drawing.Imaging.ImageFormat]::Png)
    $bitmap.Dispose()
}

# Lunettes rétro translucides.
$pair = New-Canvas 900 320; $bitmap = $pair[0]; $graphics = $pair[1]
$outline = Pen 255 35 23 48 18; $goldPen = Pen 255 255 193 105 6
$glass = Brush 105 78 190 236
$graphics.DrawLine($outline, 40, 120, 10, 92); $graphics.DrawLine($outline, 860, 120, 890, 92)
foreach ($x in @(55, 465)) {
    $shape = RoundedPath $x 70 380 180 55
    $graphics.FillPath($glass, $shape); $graphics.DrawPath($outline, $shape); $shape.Dispose()
}
$graphics.DrawLine($outline, 430, 145, 470, 145); $graphics.DrawLine($goldPen, 430, 139, 470, 139)
$shine = Pen 180 255 255 255 5
$graphics.DrawLine($shine, 88, 94, 360, 94); $graphics.DrawLine($shine, 512, 94, 784, 94)
SaveCanvas $bitmap $graphics "lunettes.png"

# Couronne dorée avec pierres colorées.
$pair = New-Canvas 720 440; $bitmap = $pair[0]; $graphics = $pair[1]
$gold = Brush 255 242 175 43; $outline = Pen 255 87 48 107 13; $band = Brush 255 221 132 39
$points = [System.Drawing.PointF[]]@(
    [System.Drawing.PointF]::new(70,350), [System.Drawing.PointF]::new(83,145),
    [System.Drawing.PointF]::new(220,260), [System.Drawing.PointF]::new(285,50),
    [System.Drawing.PointF]::new(360,235), [System.Drawing.PointF]::new(435,50),
    [System.Drawing.PointF]::new(500,260), [System.Drawing.PointF]::new(637,145),
    [System.Drawing.PointF]::new(650,350))
$graphics.FillPolygon($gold, $points); $graphics.DrawPolygon($outline, $points)
$graphics.FillRectangle($band, 84, 306, 552, 52); $graphics.DrawRectangle($outline, 84, 306, 552, 52)
foreach ($gem in @(@(205,278,225,55,85), @(360,255,95,110,245), @(515,278,170,70,220))) {
    $gemBrush = Brush 255 $gem[2] $gem[3] $gem[4]
    $graphics.FillEllipse($gemBrush, $gem[0]-26, $gem[1]-26, 52, 52)
    $graphics.DrawEllipse($outline, $gem[0]-26, $gem[1]-26, 52, 52)
    $graphics.FillEllipse((Brush 245 255 241 205), $gem[0]-12, $gem[1]-15, 13, 13)
}
SaveCanvas $bitmap $graphics "couronne.png"

# Moustache cartoon avec reflets.
$pair = New-Canvas 720 340; $bitmap = $pair[0]; $graphics = $pair[1]
$path = [System.Drawing.Drawing2D.GraphicsPath]::new()
$path.StartFigure()
$path.AddBezier(360,165,325,95,245,58,170,87); $path.AddBezier(170,87,95,118,105,205,166,239)
$path.AddBezier(166,239,225,270,305,216,360,178); $path.AddBezier(360,178,415,216,495,270,554,239)
$path.AddBezier(554,239,615,205,625,118,550,87); $path.AddBezier(550,87,475,58,395,95,360,165)
$path.CloseFigure()
$mustache = Brush 255 54 35 71; $outline = Pen 255 27 18 39 10; $shine = Pen 190 171 139 192 8
$graphics.FillPath($mustache, $path); $graphics.DrawPath($outline, $path)
$graphics.DrawBezier($shine, 155,132,205,103,258,102,300,122); $graphics.DrawBezier($shine, 565,132,515,103,462,102,420,122)
SaveCanvas $bitmap $graphics "moustache.png"

# Oreilles de lapin, intérieur rose et nœud papillon.
$pair = New-Canvas 720 760; $bitmap = $pair[0]; $graphics = $pair[1]
$white = Brush 255 247 241 250; $pink = Brush 255 238 128 183; $pinkLight = Brush 180 255 202 220
foreach ($ear in @(@(226,265,-13), @(494,265,13))) {
    $transform = $graphics.Save()
    $graphics.TranslateTransform($ear[0], $ear[1]); $graphics.RotateTransform($ear[2])
    $graphics.FillEllipse($white, -108, -250, 216, 500); $graphics.DrawEllipse((Pen 255 124 83 171 12), -108, -250, 216, 500)
    $graphics.FillEllipse($pink, -68, -208, 136, 410); $graphics.FillEllipse($pinkLight, -29, -158, 44, 235)
    $graphics.Restore($transform)
}
$graphics.FillEllipse($white, 213, 515, 294, 185); $graphics.DrawEllipse((Pen 255 124 83 171 10), 213, 515, 294, 185)
$bow = Brush 255 151 77 212; $bowPen = Pen 255 89 42 157 9
$left = [System.Drawing.PointF[]]@([System.Drawing.PointF]::new(356,595), [System.Drawing.PointF]::new(269,535), [System.Drawing.PointF]::new(276,665))
$right = [System.Drawing.PointF[]]@([System.Drawing.PointF]::new(364,595), [System.Drawing.PointF]::new(451,535), [System.Drawing.PointF]::new(444,665))
$graphics.FillPolygon($bow, $left); $graphics.DrawPolygon($bowPen, $left)
$graphics.FillPolygon($bow, $right); $graphics.DrawPolygon($bowPen, $right)
$graphics.FillEllipse((Brush 255 248 192 74), 337, 570, 46, 50); $graphics.DrawEllipse($bowPen, 337, 570, 46, 50)
SaveCanvas $bitmap $graphics "oreilles_lapin.png"

Get-ChildItem $outDir | Select-Object Name, Length
