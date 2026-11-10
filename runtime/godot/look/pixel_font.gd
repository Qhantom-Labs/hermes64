extends RefCounted
# Original 5x7 proportional bitmap font for the 320x240 UI (authored for this spike).
# Cap height 7px, x-height 5px, descender 2px, line height 10px, 1px tracking.
# Glyph rows: '#' = ink. Rows 0-6 sit on the cap line..baseline, rows 7-8 are descenders.

const LINE_H := 10
const TRACK := 1
const SPACE_W := 3

const GLYPHS := """
A
.###.
#...#
#...#
#####
#...#
#...#
#...#

B
####.
#...#
#...#
####.
#...#
#...#
####.

C
.###.
#...#
#....
#....
#....
#...#
.###.

D
####.
#...#
#...#
#...#
#...#
#...#
####.

E
#####
#....
#....
####.
#....
#....
#####

F
#####
#....
#....
####.
#....
#....
#....

G
.###.
#...#
#....
#.###
#...#
#...#
.####

H
#...#
#...#
#...#
#####
#...#
#...#
#...#

I
###
.#.
.#.
.#.
.#.
.#.
###

J
....#
....#
....#
....#
#...#
#...#
.###.

K
#...#
#..#.
#.#..
##...
#.#..
#..#.
#...#

L
#....
#....
#....
#....
#....
#....
#####

M
#...#
##.##
#.#.#
#.#.#
#...#
#...#
#...#

N
#...#
#...#
##..#
#.#.#
#..##
#...#
#...#

O
.###.
#...#
#...#
#...#
#...#
#...#
.###.

P
####.
#...#
#...#
####.
#....
#....
#....

Q
.###.
#...#
#...#
#...#
#.#.#
#..#.
.##.#

R
####.
#...#
#...#
####.
#.#..
#..#.
#...#

S
.####
#....
#....
.###.
....#
....#
####.

T
#####
..#..
..#..
..#..
..#..
..#..
..#..

U
#...#
#...#
#...#
#...#
#...#
#...#
.###.

V
#...#
#...#
#...#
#...#
#...#
.#.#.
..#..

W
#...#
#...#
#...#
#.#.#
#.#.#
#.#.#
.#.#.

X
#...#
#...#
.#.#.
..#..
.#.#.
#...#
#...#

Y
#...#
#...#
.#.#.
..#..
..#..
..#..
..#..

Z
#####
....#
...#.
..#..
.#...
#....
#####

a
.....
.....
.###.
....#
.####
#...#
.####

b
#....
#....
####.
#...#
#...#
#...#
####.

c
....
....
.###
#...
#...
#...
.###

d
....#
....#
.####
#...#
#...#
#...#
.####

e
.....
.....
.###.
#...#
#####
#....
.###.

f
..##
.#..
####
.#..
.#..
.#..
.#..

g
.....
.....
.####
#...#
#...#
#...#
.####
....#
.###.

h
#....
#....
####.
#...#
#...#
#...#
#...#

i
#
.
#
#
#
#
#

j
..#
...
..#
..#
..#
..#
..#
#.#
.#.

k
#...
#...
#..#
#.#.
##..
#.#.
#..#

l
#.
#.
#.
#.
#.
#.
.#

m
.....
.....
##.#.
#.#.#
#.#.#
#.#.#
#.#.#

n
.....
.....
####.
#...#
#...#
#...#
#...#

o
.....
.....
.###.
#...#
#...#
#...#
.###.

p
.....
.....
####.
#...#
#...#
#...#
####.
#....
#....

q
.....
.....
.####
#...#
#...#
#...#
.####
....#
....#

r
....
....
#.##
##..
#...
#...
#...

s
.....
.....
.####
#....
.###.
....#
####.

t
.#..
.#..
####
.#..
.#..
.#..
..##

u
.....
.....
#...#
#...#
#...#
#...#
.####

v
.....
.....
#...#
#...#
#...#
.#.#.
..#..

w
.....
.....
#...#
#...#
#.#.#
#.#.#
.#.#.

x
.....
.....
#...#
.#.#.
..#..
.#.#.
#...#

y
.....
.....
#...#
#...#
#...#
#...#
.####
....#
.###.

z
.....
.....
#####
...#.
..#..
.#...
#####

0
.###.
#...#
#..##
#.#.#
##..#
#...#
.###.

1
.#.
##.
.#.
.#.
.#.
.#.
###

2
.###.
#...#
....#
...#.
..#..
.#...
#####

3
####.
....#
....#
.###.
....#
....#
####.

4
...#.
..##.
.#.#.
#..#.
#####
...#.
...#.

5
#####
#....
####.
....#
....#
#...#
.###.

6
.###.
#....
#....
####.
#...#
#...#
.###.

7
#####
....#
...#.
..#..
.#...
.#...
.#...

8
.###.
#...#
#...#
.###.
#...#
#...#
.###.

9
.###.
#...#
#...#
.####
....#
....#
.###.

.
.
.
.
.
.
.
#

,
..
..
..
..
..
.#
.#
#.

!
#
#
#
#
#
.
#

?
.###.
#...#
....#
...#.
..#..
.....
..#..

'
#
#
.

"
#.#
#.#
...

:
.
.
#
.
.
.
#

;
..
..
.#
..
..
.#
.#
#.

-
....
....
....
####
....
....
....

(
..#
.#.
#..
#..
#..
.#.
..#

)
#..
.#.
..#
..#
..#
.#.
#..

/
....#
...#.
...#.
..#..
.#...
.#...
#....

>
....
#...
.#..
..#.
.#..
#...
....

<
....
..#.
.#..
#...
.#..
..#.
....

&
.##..
#..#.
#.#..
.#...
#.#.#
#..#.
.##.#

+
.....
..#..
..#..
#####
..#..
..#..
.....

=
.....
.....
#####
.....
#####
.....
.....

*
.....
#.#.#
.###.
#####
.###.
#.#.#
.....

_
.....
.....
.....
.....
.....
.....
#####
"""

var atlas: ImageTexture
var rects := {}    # char -> Rect2 in atlas
var widths := {}   # char -> int

static var _inst = null

static func get_font():
	if _inst == null:
		_inst = load("res://look/pixel_font.gd").new()
	return _inst

func _init() -> void:
	var glyphs := {}
	var lines := GLYPHS.split("\n")
	var i := 0
	while i < lines.size():
		var key := lines[i]
		if key.length() == 1:
			var rows: Array[String] = []
			i += 1
			while i < lines.size() and lines[i] != "":
				rows.append(lines[i])
				i += 1
			glyphs[key] = rows
		else:
			i += 1
	var total_w := 0
	for k in glyphs:
		var w := 0
		for r in glyphs[k]:
			w = max(w, r.length())
		widths[k] = w
		total_w += w + 1
	var img := Image.create(max(total_w, 1), 9, false, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0, 0, 0))
	var x := 0
	for k in glyphs:
		var rows: Array = glyphs[k]
		for y in rows.size():
			var r: String = rows[y]
			for cx in r.length():
				if r[cx] == "#":
					img.set_pixel(x + cx, y, Color(1, 1, 1, 1))
		rects[k] = Rect2(x, 0, widths[k], 9)
		x += widths[k] + 1
	atlas = ImageTexture.create_from_image(img)

func glyph_w(ch: String) -> int:
	if ch == " ":
		return SPACE_W
	return widths.get(ch, 4)

func measure(text: String) -> int:
	var w := 0
	for ch in text:
		w += glyph_w(ch) + TRACK
	return max(w - TRACK, 0)

func wrap(text: String, max_w: int) -> PackedStringArray:
	var out := PackedStringArray()
	for para in text.split("\n"):
		var line := ""
		for word in para.split(" "):
			var cand := word if line == "" else line + " " + word
			if measure(cand) <= max_w or line == "":
				line = cand
			else:
				out.append(line)
				line = word
		out.append(line)
	return out

func draw(ci: CanvasItem, pos: Vector2, text: String, color: Color, shadow := Color(0, 0, 0, 0.8)) -> void:
	if shadow.a > 0.0:
		_draw_run(ci, pos + Vector2(1, 1), text, shadow)
	_draw_run(ci, pos, text, color)

func _draw_run(ci: CanvasItem, pos: Vector2, text: String, color: Color) -> void:
	var x := int(pos.x)
	var y := int(pos.y)
	for ch in text:
		if rects.has(ch):
			var r: Rect2 = rects[ch]
			ci.draw_texture_rect_region(atlas, Rect2(x, y, r.size.x, r.size.y), r, color)
		x += glyph_w(ch) + TRACK
