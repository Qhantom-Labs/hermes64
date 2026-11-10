// Post pass at internal resolution (320x240):
//  - optional palette LUT (KITS layout: 256x16 = 16 slices of 16x16, x = b*16 + r, y = g, 4-bit
//    quantised sRGB -> nearest palette colour), forcing the final frame through the pack palette;
//  - optional 15-bit (RGB555) quantise with 4x4 ordered dither, per low-res pixel.
shader_type canvas_item;

uniform bool dither_on = false;
uniform bool lut_on = false;
uniform sampler2D lut : filter_nearest, repeat_disable;
uniform vec2 src_size = vec2(320.0, 240.0);

int m2(int x, int y) {
	return ((x ^ y) << 1) | y;
}

void fragment() {
	vec4 c = texture(TEXTURE, UV);
	if (lut_on) {
		vec3 q = floor(clamp(c.rgb, 0.0, 1.0) * 15.0 + 0.5);
		vec2 luv = vec2((q.b * 16.0 + q.r + 0.5) / 256.0, (q.g + 0.5) / 16.0);
		c.rgb = texture(lut, luv).rgb;
	}
	if (dither_on) {
		ivec2 p = ivec2(floor(UV * src_size));
		int x = p.x & 3;
		int y = p.y & 3;
		int m = 4 * m2(x & 1, y & 1) + m2(x >> 1, y >> 1);
		float t = (float(m) + 0.5) / 16.0 - 0.5;
		c.rgb = floor(c.rgb * 31.0 + 0.5 + t) / 31.0;
	}
	COLOR = vec4(c.rgb, 1.0);
}
