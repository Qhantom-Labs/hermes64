// Falling particle field (snow / dust / fireflies) as one MultiMesh of camera-facing quads. Positions come from
// INSTANCE_ID hashes and TIME only (deterministic for a given time), colours from pack data.
shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_opaque, fog_disabled;

uniform vec4 color = vec4(1.0);          // display (sRGB) value
uniform vec3 area = vec3(30.0, 10.0, 30.0);
uniform float speed = 0.5;
uniform float drift = 0.2;
uniform float size = 0.07;
uniform float near_cull = 0.0;           // motes nearer the camera shrink away (COMBAT camera; 0 = off, unchanged)

global uniform vec4 n64_debug;
global uniform vec4 n64_fog_color;
global uniform vec4 n64_fog;

varying float v_fog;

float hash(float n) {
	return fract(sin(n) * 43758.5453);
}

vec3 to_linear(vec3 c) {
	vec3 lo = c / 12.92;
	vec3 hi = pow((c + 0.055) / 1.055, vec3(2.4));
	return mix(hi, lo, vec3(1.0) - step(vec3(0.04045), c));
}

void vertex() {
	float id = float(INSTANCE_ID);
	vec3 base = vec3(hash(id * 1.7 + 0.1), hash(id * 3.1 + 0.2), hash(id * 5.3 + 0.3)) * area;
	float y = mod(base.y - TIME * speed * (0.7 + 0.6 * hash(id * 7.9)), area.y);
	vec3 p = vec3(base.x - area.x * 0.5 + sin(TIME * 0.7 + id) * drift, y, base.z - area.z * 0.5 + cos(TIME * 0.5 + id * 1.3) * drift);
	vec3 right = INV_VIEW_MATRIX[0].xyz;
	vec3 up = INV_VIEW_MATRIX[1].xyz;
	vec3 centre = (MODEL_MATRIX * vec4(p, 1.0)).xyz;
	float keep = 1.0;
	if (near_cull > 0.0) {
		keep = smoothstep(near_cull * 0.6, near_cull, length((VIEW_MATRIX * vec4(centre, 1.0)).xyz));
	}
	vec3 world = centre + (right * VERTEX.x + up * VERTEX.y) * size * (0.6 + 0.8 * hash(id * 2.3)) * keep;
	vec3 vp = (VIEW_MATRIX * vec4(world, 1.0)).xyz;
	POSITION = PROJECTION_MATRIX * vec4(vp, 1.0);
	v_fog = clamp((length(vp) - n64_fog.x) / max(n64_fog.y - n64_fog.x, 0.001), 0.0, 1.0) * n64_fog.z * n64_fog.w;
}

void fragment() {
	if (n64_debug.x > 0.5) {
		discard;
	}
	vec2 d = UV * 2.0 - 1.0;
	if (dot(d, d) > 1.0) {
		discard;
	}
	vec3 c = mix(color.rgb, n64_fog_color.rgb, v_fog * 0.7);
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	ALBEDO = c;
#else
	ALBEDO = to_linear(c);
#endif
}
