// Combat telegraph floor marker (COMBAT lane): a flat painted decal in the N64 manner (one tinted colour, soft
// edge, no texture, no glow). Shapes from UV: 0 disc (landing zone), 1 ring (shockwave reach / sweep), 2 lane
// (dash / projectile path, UV.y from the attacker 0 to the tip 1), 3 arc (melee reach wedge, half-angle `arc`).
// The outline is always drawn; the interior fills with `progress` (windup elapsed), so the decal also shows timing.
// `danger` (0..1) mixes toward danger_color in the last ticks before the hit. Presentation only.
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_disabled, fog_disabled;

uniform int shape = 0;
uniform vec4 color = vec4(0.85, 0.6, 0.28, 1.0);         // display (sRGB) value
uniform vec4 danger_color = vec4(0.85, 0.35, 0.23, 1.0);
uniform float alpha = 0.5;
uniform float progress = 0.0;
uniform float danger = 0.0;
uniform float inner = 0.8;     // ring: inner radius (fraction of the outer radius)
uniform float arc = 0.9;       // arc: half-angle (radians)
uniform float edge = 0.07;     // outline band (fraction of the radius / lane width)

global uniform vec4 n64_debug;

vec3 to_linear(vec3 c) {
	vec3 lo = c / 12.92;
	vec3 hi = pow((c + 0.055) / 1.055, vec3(2.4));
	return mix(hi, lo, vec3(1.0) - step(vec3(0.04045), c));
}

float band(float d, float w) {
	// 1 inside the band [-w, 0] of a signed distance d (d < 0 inside the shape), soft on both sides
	return smoothstep(-w - 0.03, -w, d) * (1.0 - smoothstep(-0.015, 0.015, d));
}

void fragment() {
	if (n64_debug.x > 0.5) {
		discard;
	}
	vec2 q = UV * 2.0 - 1.0;
	float outline = 0.0;
	float fill = 0.0;
	float p = clamp(progress, 0.0, 1.0);
	if (shape == 2) {
		// lane: x across (-1..1), y along (attacker at UV.y = 0)
		float d = max(abs(q.x) - 1.0, max(-UV.y, UV.y - 1.0) * 2.0);
		outline = band(d, edge * 2.0);
		fill = step(UV.y, p) * (1.0 - smoothstep(-0.02, 0.02, d));
	} else {
		float r = length(q);
		float d = r - 1.0;
		if (shape == 1) {
			float di = inner - r;
			outline = band(d, edge) + band(di, edge * 0.6);
			fill = step(r, 1.0) * step(inner, r) * step(r, inner + (1.0 - inner) * p + 0.001);
		} else if (shape == 3) {
			float ang = abs(atan(q.x, -q.y));
			float da = (ang - arc) * r;
			float dd = max(d, da);
			outline = band(dd, edge);
			fill = step(dd, 0.0) * step(r, p);
		} else {
			outline = band(d, edge);
			fill = step(r, p) * step(d, 0.0);
		}
	}
	float a = clamp(max(outline, fill * 0.5), 0.0, 1.0) * alpha;
	if (a <= 0.003) {
		discard;
	}
	vec3 c = mix(color.rgb, danger_color.rgb, clamp(danger, 0.0, 1.0));
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	ALBEDO = c;
#else
	ALBEDO = to_linear(c);
#endif
	ALPHA = a;
}
