// Static particle field for covers (snow / fireflies / dust / embers / petals). Positions are explicit MultiMesh
// instance transforms written from a seeded generator (no TIME), so a cover frame is deterministic. Camera-facing
// round sprites, per-instance size from the transform scale; fireflies/embers add light, the others are opaque.
shader_type spatial;
render_mode unshaded, cull_disabled, blend_mix, depth_draw_never, fog_disabled;

uniform vec4 color = vec4(1.0);
uniform float size = 0.07;
uniform float glow = 0.0;

global uniform vec4 n64_debug;
global uniform vec4 n64_fog_color;
global uniform vec4 n64_fog;

varying float v_fog;

vec3 to_linear(vec3 c) {
	vec3 lo = c / 12.92;
	vec3 hi = pow((c + 0.055) / 1.055, vec3(2.4));
	return mix(hi, lo, vec3(1.0) - step(vec3(0.04045), c));
}

void vertex() {
	vec3 origin = (MODEL_MATRIX * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
	float s = length(MODEL_MATRIX[0].xyz) * size;
	vec3 right = INV_VIEW_MATRIX[0].xyz;
	vec3 up = INV_VIEW_MATRIX[1].xyz;
	vec3 world = origin + (right * VERTEX.x + up * VERTEX.y) * s;
	vec3 vp = (VIEW_MATRIX * vec4(world, 1.0)).xyz;
	POSITION = PROJECTION_MATRIX * vec4(vp, 1.0);
	v_fog = clamp((length(vp) - n64_fog.x) / max(n64_fog.y - n64_fog.x, 0.001), 0.0, 1.0) * n64_fog.z * n64_fog.w;
}

void fragment() {
	if (n64_debug.x > 0.5) {
		discard;
	}
	vec2 d = UV * 2.0 - 1.0;
	float r = dot(d, d);
	// soft round sprite: an opaque core with a 2-3 px feathered rim at cover resolution (no aliased discard edge)
	float a = 1.0 - smoothstep(0.35, 1.0, r);
	vec3 c = mix(color.rgb, n64_fog_color.rgb, v_fog * 0.65);
	c = mix(c, vec3(1.0), glow * (1.0 - smoothstep(0.0, 0.35, r)));
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	ALBEDO = c;
#else
	ALBEDO = to_linear(c);
#endif
	ALPHA = a;
}
