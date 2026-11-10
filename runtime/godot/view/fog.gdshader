shader_type spatial;
render_mode unshaded;
uniform vec4 tint : source_color = vec4(0.6,0.6,0.6,1.0);
uniform vec4 fog_color : source_color = vec4(0.13,0.13,0.13,1.0);
uniform float fog_near = 6.0;
uniform float fog_far = 28.0;
varying float shade;
void vertex() {
	shade = 0.55 + 0.45 * max(0.0, dot(normalize(NORMAL), normalize(vec3(-0.5,1.0,0.4))));
}
void fragment() {
	float fog = smoothstep(fog_near, fog_far, length(VERTEX));
	ALBEDO = mix(tint.rgb * shade, fog_color.rgb, fog);
}
