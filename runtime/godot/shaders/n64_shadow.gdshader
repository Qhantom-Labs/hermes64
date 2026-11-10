// Blob shadow card (N64-era contact shadow under props and furniture): a soft dark disc blended over the floor.
// Colour and strength come from pack data (look.shadows); hidden in the capture debug passes.
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_disabled, fog_disabled;

uniform vec4 color = vec4(0.02, 0.02, 0.05, 1.0);   // display (sRGB) value
uniform float strength = 0.5;
uniform float softness = 1.4;

global uniform vec4 n64_debug;

vec3 to_linear(vec3 c) {
	vec3 lo = c / 12.92;
	vec3 hi = pow((c + 0.055) / 1.055, vec3(2.4));
	return mix(hi, lo, vec3(1.0) - step(vec3(0.04045), c));
}

void fragment() {
	if (n64_debug.x > 0.5) {
		discard;
	}
	vec2 d = UV * 2.0 - 1.0;
	float r = clamp(1.0 - length(d), 0.0, 1.0);
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	ALBEDO = color.rgb;
#else
	ALBEDO = to_linear(color.rgb);
#endif
	ALPHA = pow(r, softness) * strength;
}
