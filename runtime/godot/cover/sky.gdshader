// Painted cover sky (hermes64 cover 1.0.0): a zenith->horizon gradient in soft painted bands, a sun/moon glow,
// optional stars, aurora curtain and low cloud streaks. Colours are display (sRGB) values from the style palette;
// everything is a pure function of the view direction and the seed (no TIME), so frames are deterministic.
// The world grade (n64_grade/lift/gain) is applied like n64_world so sky and scenery share one look; below
// horizon_y the dome is the horizon/fog colour, so fogged distance and sky melt together (N64 convention).
shader_type spatial;
render_mode unshaded, cull_front, depth_draw_never, fog_disabled;

uniform vec4 zenith = vec4(0.05, 0.07, 0.2, 1.0);
uniform vec4 horizon = vec4(0.25, 0.35, 0.7, 1.0);
uniform vec4 glow = vec4(1.0, 0.85, 0.55, 1.0);
uniform float glow_strength = 0.3;
uniform vec3 glow_dir = vec3(0.0, 0.2, -1.0);
uniform float stars = 0.0;
uniform vec4 aurora = vec4(0.3, 0.8, 1.0, 1.0);
uniform float aurora_strength = 0.0;
uniform float clouds = 0.0;
uniform vec4 cloud_color = vec4(1.0);
uniform float horizon_y = 0.0;
// elevation span (sin) over which the gradient reaches the zenith colour; covers frame low skies, so it is short
uniform float sky_span = 0.8;
uniform float seed = 0.0;
uniform float bands = 12.0;

global uniform vec4 n64_debug;
global uniform vec4 n64_grade;
global uniform vec4 n64_lift;
global uniform vec4 n64_gain;

varying vec3 v_dir;

vec3 to_linear(vec3 c) {
	vec3 lo = c / 12.92;
	vec3 hi = pow((c + 0.055) / 1.055, vec3(2.4));
	return mix(hi, lo, vec3(1.0) - step(vec3(0.04045), c));
}

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7)) + seed * 0.731) * 43758.5453);
}

float vnoise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	float a = hash(i);
	float b = hash(i + vec2(1.0, 0.0));
	float c = hash(i + vec2(0.0, 1.0));
	float d = hash(i + vec2(1.0, 1.0));
	return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

vec3 grade(vec3 c) {
	c *= n64_grade.w;
	c = n64_lift.rgb + c * (n64_gain.rgb - n64_lift.rgb);
	c = clamp(c, 0.0, 1.0);
	c = pow(c, vec3(1.0 / max(n64_grade.z, 0.01)));
	float l = dot(c, vec3(0.299, 0.587, 0.114));
	c = mix(vec3(l), c, n64_grade.y);
	c = (c - 0.5) * n64_grade.x + 0.5;
	return clamp(c, 0.0, 1.0);
}

void vertex() {
	v_dir = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz - INV_VIEW_MATRIX[3].xyz;
}

void fragment() {
	vec3 d = normalize(v_dir);
	float e = d.y;
	float az = atan(d.x, d.z);
	float h = e - horizon_y;
	float t = clamp(h / sky_span, 0.0, 1.0);
	t = pow(t, 0.85);
	// painted bands: a few soft steps, the way N64 sky cards quantised their gradients
	float q = floor(t * bands) / bands;
	float fr = fract(t * bands);
	t = mix(q, q + 1.0 / bands, smoothstep(0.3, 0.7, fr));
	vec3 c = mix(horizon.rgb, zenith.rgb, t);
	float above = smoothstep(-0.01, 0.025, h);
	// sun / moon glow: a broad wash plus a tight core
	float g = max(dot(d, normalize(glow_dir)), 0.0);
	c = mix(c, glow.rgb, clamp(glow_strength * (pow(g, 6.0) * 0.55 + pow(g, 48.0) * 0.6), 0.0, 1.0) * mix(0.35, 1.0, above));
	// low cloud streaks: noise on a horizontal cloud plane (continuous all round, no azimuth seam)
	float band = smoothstep(0.01, 0.07, h) * (1.0 - smoothstep(0.16, 0.38, h));
	vec2 cp = d.xz / max(d.y + 0.12, 0.04);
	float n = vnoise(cp * vec2(1.1, 4.2) + seed) * 0.6 + vnoise(cp * vec2(2.7, 9.0) - seed * 1.3) * 0.4;
	c = mix(c, cloud_color.rgb, clamp(clouds * band * smoothstep(0.42, 0.72, n), 0.0, 1.0));
	// aurora curtain
	float mid = 0.34 + 0.07 * sin(az * 2.0 + seed * 0.37);
	float curtain = exp(-pow((h - mid) / 0.085, 2.0)) * (0.55 + 0.45 * sin(az * 7.0 + seed * 1.7));
	curtain *= smoothstep(-0.6, 0.4, sin(az + seed));
	c = mix(c, aurora.rgb, clamp(aurora_strength * curtain, 0.0, 1.0));
	// stars: hashed cells on the direction cube (continuous, no seam), more visible higher up
	if (stars > 0.0) {
		vec3 g3 = d * 46.0;
		vec3 cell3 = floor(g3);
		vec2 cell = cell3.xy + cell3.z * vec2(17.0, 31.0);
		float pick = hash(cell);
		if (pick < stars / 1400.0) {
			vec3 centre = cell3 + vec3(hash(cell + 3.1), hash(cell + 7.7), hash(cell + 9.4)) * 0.7 + 0.15;
			float r = length(g3 - centre);
			float size = 0.09 + 0.09 * hash(cell + 11.3);
			float st = (1.0 - smoothstep(size * 0.4, size, r)) * smoothstep(0.04, 0.22, h);
			c = mix(c, vec3(1.0), st * (0.55 + 0.45 * hash(cell + 5.9)));
		}
	}
	c = mix(horizon.rgb, c, above);
	c = grade(c);
	if (n64_debug.x > 0.5) {
		c = n64_debug.x < 1.5 ? vec3(1.0) : vec3(0.0, 0.0, 1.0);
	}
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	ALBEDO = c;
#else
	ALBEDO = to_linear(c);
#endif
}
