// Additive light pool / halo card (N64-era glow sprite). Colours come from pack emitter data.
// mode 0 = flat pool on a surface (radial falloff), mode 1 = camera-facing halo billboard.
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, fog_disabled;

uniform vec4 color = vec4(1.0, 0.85, 0.6, 1.0);   // display (sRGB) value, no hint: raw like n64_world
uniform float strength = 0.5;
uniform int mode = 0;
uniform float softness = 1.6;

global uniform vec4 n64_fog;
global uniform vec4 n64_debug;

varying float v_fog;

vec3 to_linear(vec3 c) {
	vec3 lo = c / 12.92;
	vec3 hi = pow((c + 0.055) / 1.055, vec3(2.4));
	return mix(hi, lo, vec3(1.0) - step(vec3(0.04045), c));
}

void vertex() {
	if (mode == 1) {
		MODELVIEW_MATRIX = VIEW_MATRIX * mat4(INV_VIEW_MATRIX[0] * length(MODEL_MATRIX[0].xyz), INV_VIEW_MATRIX[1] * length(MODEL_MATRIX[1].xyz),
			INV_VIEW_MATRIX[2], MODEL_MATRIX[3]);
	}
	vec3 vp = (MODELVIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float f = clamp((length(vp) - n64_fog.x) / max(n64_fog.y - n64_fog.x, 0.001), 0.0, 1.0);
	v_fog = f * n64_fog.z * n64_fog.w;
}

void fragment() {
	if (n64_debug.x > 0.5) {
		discard;
	}
	vec2 d = UV * 2.0 - 1.0;
	float r = clamp(1.0 - length(d), 0.0, 1.0);
	float a = pow(r, softness) * strength * (1.0 - v_fog);
	vec3 c = clamp(color.rgb * a, 0.0, 1.0);
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	ALBEDO = c;
#else
	ALBEDO = to_linear(c);
#endif
}
