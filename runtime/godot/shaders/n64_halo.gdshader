// Warm halo billboard blended over the frame (not added): an additive glow over a cool room drifts toward
// magenta, a mixed one keeps the lamp's hue. Colour and strength come from pack emitter data (halo_mode "mix").
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_disabled, fog_disabled;

uniform vec4 color = vec4(1.0, 0.7, 0.3, 1.0);   // display (sRGB) value
uniform float strength = 0.6;
uniform float softness = 1.3;
uniform float core = 0.35;                         // hot centre mixed toward white-gold
uniform float pull = 0.0;                          // metres toward the camera, so the halo is not hidden inside its own emitter

global uniform vec4 n64_fog;
global uniform vec4 n64_debug;

varying float v_fog;

vec3 to_linear(vec3 c) {
	vec3 lo = c / 12.92;
	vec3 hi = pow((c + 0.055) / 1.055, vec3(2.4));
	return mix(hi, lo, vec3(1.0) - step(vec3(0.04045), c));
}

void vertex() {
	MODELVIEW_MATRIX = VIEW_MATRIX * mat4(INV_VIEW_MATRIX[0] * length(MODEL_MATRIX[0].xyz), INV_VIEW_MATRIX[1] * length(MODEL_MATRIX[1].xyz),
		INV_VIEW_MATRIX[2], MODEL_MATRIX[3]);
	vec3 vp = (MODELVIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vp += normalize(-vp) * pull;
	POSITION = PROJECTION_MATRIX * vec4(vp, 1.0);
	float f = clamp((length(vp) - n64_fog.x) / max(n64_fog.y - n64_fog.x, 0.001), 0.0, 1.0);
	v_fog = f * n64_fog.z * n64_fog.w;
}

void fragment() {
	if (n64_debug.x > 0.5) {
		discard;
	}
	vec2 d = UV * 2.0 - 1.0;
	float r = clamp(1.0 - length(d), 0.0, 1.0);
	vec3 c = mix(color.rgb, vec3(1.0, 0.93, 0.78), smoothstep(1.0 - core, 1.0, r));
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	ALBEDO = c;
#else
	ALBEDO = to_linear(c);
#endif
	ALPHA = clamp(pow(r, softness) * strength * (1.0 - v_fog), 0.0, 1.0);
}
