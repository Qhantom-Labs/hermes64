// N64-era surface (Godot 4.6.2). Theme-agnostic: every colour and strength comes from pack data
// (view.json "look": light rig, fog, grade, per-role material response) through global uniforms.
// Colour maths happens in sRGB/"display" space like the old hardware; the result is converted to linear
// only for renderers that expect linear ALBEDO (Mobile/Forward+). Compatibility writes ALBEDO as-is.
//
// Lighting is evaluated PER VERTEX (Gouraud, like fixed-function T&L): hemisphere ambient, key + fill
// directionals, a view-dependent rim term and up to four point lights. Static kit meshes keep their baked
// COLOR as form/AO light and are modulated by the room rig; characters (dynamic_light) use COLOR as albedo.
// Environment ("chrome") lookups use per-vertex sphere-map coordinates from the reflected view vector, so the
// reflection warps across large triangles exactly like hardware texgen did.
//
// surface_mode 0 = textured (baked_unlit / emissive / view_plane / card_alpha)
// surface_mode 1 = env-map chrome / glass
shader_type spatial;
render_mode unshaded, cull_back, depth_draw_opaque, fog_disabled;

uniform sampler2D tex_linear : filter_linear_mipmap, repeat_enable;
uniform sampler2D tex_nearest : filter_nearest, repeat_enable;
uniform sampler2D env_tex : filter_linear, repeat_disable;
uniform int surface_mode = 0;
uniform bool has_texture = true;
uniform bool has_env = false;
uniform bool vcolor_is_linear = false;   // glTF COLOR_0 is linear; procedural meshes store sRGB
uniform vec4 tint = vec4(1.0);
uniform vec2 uv_offset = vec2(0.0);
uniform vec2 uv_scroll = vec2(0.0);
uniform vec4 wobble = vec4(0.0);        // water vertex wobble (DUNGEONKIT lake kit): x amplitude m, y wavelength m, z speed
uniform float alpha_cut = 0.0;
uniform bool dynamic_light = false;      // COLOR is albedo (characters) instead of baked light
uniform float lit = 1.0;                 // 0 = ignores the room rig (emissive screens, window views)
uniform float gloss = 0.0;               // env highlight blend on baked surfaces (molded plastic, vinyl)
uniform float spec = 0.0;                // per-vertex specular glint strength
uniform float rim_amt = 1.0;             // scales the rig's rim term for this surface
uniform float fog_scale = 1.0;           // window views take less interior fog
uniform float emission = 0.0;            // adds unlit brightness (lamp shades, glow cards)
uniform vec4 point_light_pos = vec4(0.0);   // legacy per-material light (characters), w = radius
uniform vec4 point_light_col = vec4(0.0);
uniform int mask_id = 0;                 // gate/golden region id: 1 chrome/glass, 2 window view, 3 sky, 4 emissive, 5 ground
uniform vec2 horizon_fog = vec2(0.0);    // sky only: the painted gradient melts into the fog colour below this view
                                         // elevation band (sin, from x to y), so far geometry dissolves into the sky
uniform float tex_vblur = 0.0;           // sky only: vertical tent blur radius in texels, so the palette-exact gradient
                                         // bands of the sky card read as one smooth painted gradient
uniform float unlit_level = 1.0;         // unlit surfaces (screens, light panels, window views) are painted at this level
                                         // of their texture, below full white (convention lighting.unlit_level)

global uniform vec4 n64_fog_color;   // rgb sRGB
global uniform vec4 n64_fog;         // x begin, y end, z enabled, w max density
global uniform vec4 n64_mode;        // x filter 0 nearest/1 bilinear/2 three-point, y light on, z texture on, w room rig on
global uniform vec4 n64_sun_dir;     // xyz towards key light (world)
global uniform vec4 n64_sun_col;     // rgb key colour * strength
global uniform vec4 n64_ambient;     // rgb ambient * strength
global uniform vec4 n64_sky;         // rgb upper hemisphere * strength
global uniform vec4 n64_ground;      // rgb lower hemisphere * strength
global uniform vec4 n64_fill_dir;    // xyz towards fill light
global uniform vec4 n64_fill_col;    // rgb fill * strength
global uniform vec4 n64_rim;         // rgb rim * strength, a = exponent
global uniform vec4 n64_spec;        // rgb specular colour, a = exponent
global uniform vec4 n64_pl0_pos;     // point lights: xyz, w = radius (0 = off)
global uniform vec4 n64_pl0_col;     // rgb * intensity
global uniform vec4 n64_pl1_pos;
global uniform vec4 n64_pl1_col;
global uniform vec4 n64_pl2_pos;
global uniform vec4 n64_pl2_col;
global uniform vec4 n64_pl3_pos;
global uniform vec4 n64_pl3_col;
global uniform vec4 n64_grade;       // x contrast, y saturation, z gamma, w exposure
global uniform vec4 n64_lift;        // rgb added to darks
global uniform vec4 n64_gain;        // rgb multiplier on brights
global uniform vec4 n64_bake;        // x = desaturation of baked vertex light (rig supplies the hue)
global uniform vec4 n64_debug;       // capture passes only: x 1 = distance (y = metres at white), 2 = region mask
// ROOMLOOK r3 (all neutral by default, so legacy packs render exactly as before):
global uniform vec4 n64_room;        // value structure on static lit surfaces: x top darkening 0..1, y/z height (m)
                                     // where it starts/ends, w wall-base occlusion 0..1
global uniform vec4 n64_room2;       // x wall-base occlusion height (m), y floor-centre lift, z/w room centre (x, z)
global uniform vec4 n64_chrome;      // env-map metal response: x env gamma, y hot-spot threshold, z hot amount, w rim
global uniform vec4 n64_actor;       // character rim (dynamic_light only): rgb * strength, a = exponent
global uniform vec4 n64_kicker;      // character kicker from behind/above the subject: rgb * strength, a = up bias
global uniform vec4 n64_px;          // x 1 = point lights per pixel on static lit surfaces (round pools and smooth
                                     // specular glints instead of Gouraud wedges on large floor/wall triangles)
global uniform vec4 n64_classic;     // N64-FIDELITY gate on the non-N64 lighting features: x per-pixel point lights,
                                     // y specular glints, z fresnel rims, w per-pixel gloss reflection (1 = as the pack
                                     // data says / legacy, 0 = off; kits/core/n64_look.json switches them off)
global uniform vec4 n64_filter;      // N64 filter (n64_mode.x = 4): x = mip LOD bias when minified (negative keeps
                                     // distant texel detail without the sparkle of unmipmapped sampling)
global uniform vec4 n64_lattice;     // x > 0: point lights on static lit surfaces are evaluated on a virtual vertex
                                     // lattice of x metres and interpolated (what vertex lighting on a tessellated N64
                                     // floor shows: soft polygonal pools, no per-pixel circles, no wedges on big tris)

varying vec3 v_light;
varying vec3 v_albedo;
varying vec3 v_spec;
varying vec3 v_rim;
varying vec2 v_env;
varying float v_fog;
varying vec3 v_wpos;
varying float v_wny;
varying vec3 v_wn;
varying vec3 v_baked;
varying vec3 v_rigbase;
varying vec3 v_speckey;

vec3 to_linear(vec3 c) {
	vec3 lo = c / 12.92;
	vec3 hi = pow((c + 0.055) / 1.055, vec3(2.4));
	return mix(hi, lo, vec3(1.0) - step(vec3(0.04045), c));
}

vec3 to_srgb(vec3 c) {
	vec3 lo = c * 12.92;
	vec3 hi = 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055;
	return mix(hi, lo, vec3(1.0) - step(vec3(0.0031308), c));
}

vec3 point_light(vec4 pos, vec4 col, vec3 wp, vec3 wn, vec3 V, inout vec3 sp) {
	if (pos.w <= 0.0) {
		return vec3(0.0);
	}
	vec3 d = pos.xyz - wp;
	float k = clamp(1.0 - dot(d, d) / (pos.w * pos.w), 0.0, 1.0);
	k = k * k;
	vec3 L = normalize(d);
	float wrap = max(dot(wn, L) * 0.7 + 0.3, 0.0);
	vec3 H = normalize(L + V);
	sp += col.rgb * k * pow(max(dot(wn, H), 0.0), max(n64_spec.a * 0.5, 1.0));
	return col.rgb * k * wrap;
}

// Diffuse part of the four room point lights at one position (no specular).
vec3 room_points(vec3 p, vec3 wn) {
	vec3 none = vec3(0.0);
	vec3 r = point_light(n64_pl0_pos, n64_pl0_col, p, wn, wn, none);
	r += point_light(n64_pl1_pos, n64_pl1_col, p, wn, wn, none);
	r += point_light(n64_pl2_pos, n64_pl2_col, p, wn, wn, none);
	r += point_light(n64_pl3_pos, n64_pl3_col, p, wn, wn, none);
	return r;
}

// Point lights sampled on a virtual vertex lattice (cell metres) and trilinearly interpolated: the look of vertex
// lighting on a tessellated floor/wall, independent of how big the real triangles are.
vec3 lattice_points(vec3 wp, vec3 wn, float cell) {
	vec3 g = wp / cell;
	vec3 i = floor(g);
	vec3 f = g - i;
	vec3 o = i * cell;
	vec3 c000 = room_points(o, wn);
	vec3 c100 = room_points(o + vec3(cell, 0.0, 0.0), wn);
	vec3 c010 = room_points(o + vec3(0.0, cell, 0.0), wn);
	vec3 c110 = room_points(o + vec3(cell, cell, 0.0), wn);
	vec3 c001 = room_points(o + vec3(0.0, 0.0, cell), wn);
	vec3 c101 = room_points(o + vec3(cell, 0.0, cell), wn);
	vec3 c011 = room_points(o + vec3(0.0, cell, cell), wn);
	vec3 c111 = room_points(o + vec3(cell, cell, cell), wn);
	vec3 x00 = mix(c000, c100, f.x);
	vec3 x10 = mix(c010, c110, f.x);
	vec3 x01 = mix(c001, c101, f.x);
	vec3 x11 = mix(c011, c111, f.x);
	return mix(mix(x00, x10, f.y), mix(x01, x11, f.y), f.z);
}

void vertex() {
	if (wobble.x > 0.0) {
		// N64-style per-vertex swell in world space (tiles stay continuous); amplitude bounded by the lake gate
		vec3 w0 = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
		float k = 6.2831853 / max(wobble.y, 0.5);
		VERTEX.y += wobble.x * 0.5 * (sin(w0.x * k + TIME * wobble.z) + sin(w0.z * k * 0.71 + TIME * wobble.z * 1.37));
	}
	vec3 col = COLOR.rgb;
	if (vcolor_is_linear) {
		col = to_srgb(col);
	}
	vec3 wn = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
	vec3 wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec3 cam = INV_VIEW_MATRIX[3].xyz;
	vec3 V = normalize(cam - wp);
	vec3 K = normalize(n64_sun_dir.xyz);
	vec3 F = normalize(n64_fill_dir.xyz + vec3(0.0, 0.0001, 0.0));
	vec3 rig = n64_ambient.rgb;
	rig += n64_sky.rgb * max(wn.y, 0.0) + n64_ground.rgb * max(-wn.y, 0.0);
	rig += n64_sun_col.rgb * max(dot(wn, K), 0.0);
	rig += n64_fill_col.rgb * max(dot(wn, F), 0.0);
	vec3 sp = n64_spec.rgb * pow(max(dot(wn, normalize(K + V)), 0.0), max(n64_spec.a, 1.0)) * length(n64_sun_col.rgb);
	v_rigbase = rig;
	v_speckey = sp * spec * lit * n64_classic.y;
	rig += point_light(n64_pl0_pos, n64_pl0_col, wp, wn, V, sp);
	rig += point_light(n64_pl1_pos, n64_pl1_col, wp, wn, V, sp);
	rig += point_light(n64_pl2_pos, n64_pl2_col, wp, wn, V, sp);
	rig += point_light(n64_pl3_pos, n64_pl3_col, wp, wn, V, sp);
	if (point_light_pos.w > 0.0) {
		rig += point_light(point_light_pos, point_light_col, wp, wn, V, sp);
	}
	float fres = pow(clamp(1.0 - max(dot(wn, V), 0.0), 0.0, 1.0), max(n64_rim.a, 0.5));
	v_rim = n64_rim.rgb * fres * rim_amt * lit * n64_classic.z;
	if (dynamic_light) {
		// characters: a kicker from behind/above the subject (relative to the fixed camera) and a stronger rim, so
		// silhouettes separate from walls; pure lighting data, actor meshes untouched
		vec3 cf = -normalize(INV_VIEW_MATRIX[2].xyz);
		vec3 kd = normalize(cf + vec3(0.0, n64_kicker.a, 0.0));
		rig += n64_kicker.rgb * max(dot(wn, kd), 0.0);
		v_rim += n64_actor.rgb * pow(clamp(1.0 - max(dot(wn, V), 0.0), 0.0, 1.0), max(n64_actor.a, 0.5)) * n64_classic.z;
	}
	v_spec = sp * spec * lit * n64_classic.y;
	// n64_mode.w = 1 when the pack supplies a room rig; legacy packs keep baked-only static light.
	if (dynamic_light) {
		v_albedo = col;
		v_light = min(rig, vec3(1.6));
	} else {
		v_albedo = vec3(1.0);
		float bl = dot(col, vec3(0.299, 0.587, 0.114));
		vec3 baked = mix(col, vec3(bl), n64_bake.x * lit);
		v_light = baked * mix(vec3(1.0), min(rig, vec3(1.8)), lit * n64_mode.w);
		v_baked = baked;
	}
	v_wn = wn;
	// sphere-map texgen from the reflected view vector (view space), per vertex
	vec3 vn = normalize((MODELVIEW_MATRIX * vec4(NORMAL, 0.0)).xyz);
	vec3 vp = (MODELVIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec3 r = reflect(normalize(vp), vn);
	float m = 2.0 * sqrt(r.x * r.x + r.y * r.y + (r.z + 1.0) * (r.z + 1.0));
	v_env = vec2(r.x / max(m, 0.0001) + 0.5, 0.5 - r.y / max(m, 0.0001));
	float f = clamp((length(vp) - n64_fog.x) / max(n64_fog.y - n64_fog.x, 0.001), 0.0, 1.0);
	v_fog = f * n64_fog.z * n64_fog.w * fog_scale;
	v_wpos = wp;
	v_wny = wn.y;
	UV = UV + uv_offset + uv_scroll * TIME;
}

// N64-style 3-point (triangle) texture filter: blends 3 texels instead of bilinear's 4.
vec4 three_point(sampler2D t, vec2 uv) {
	vec2 size = vec2(textureSize(t, 0));
	vec2 st = uv * size - 0.5;
	vec2 i = floor(st);
	vec2 f = st - i;
	vec2 inv = 1.0 / size;
	vec2 base = (i + 0.5) * inv;
	vec4 a = texture(t, base);
	vec4 b = texture(t, base + vec2(inv.x, 0.0));
	vec4 c = texture(t, base + vec2(0.0, inv.y));
	if (f.x + f.y < 1.0) {
		return a + f.x * (b - a) + f.y * (c - a);
	}
	vec4 d = texture(t, base + inv);
	return d + (1.0 - f.x) * (c - d) + (1.0 - f.y) * (b - d);
}

// Bilinear on the un-mipmapped texture: keeps distant texel detail (no mip averaging into flat colour) and stays
// smooth when magnified near the lens (no 3-point triangle spikes on high-contrast dithered texels).
vec4 bilinear_nomip(sampler2D t, vec2 uv) {
	vec2 size = vec2(textureSize(t, 0));
	vec2 st = uv * size - 0.5;
	vec2 i = floor(st);
	vec2 f = st - i;
	vec2 inv = 1.0 / size;
	vec2 base = (i + 0.5) * inv;
	vec4 a = texture(t, base);
	vec4 b = texture(t, base + vec2(inv.x, 0.0));
	vec4 c = texture(t, base + vec2(0.0, inv.y));
	vec4 d = texture(t, base + inv);
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

void fragment() {
	vec4 tc = vec4(1.0);
	vec3 env = vec3(0.0);
	if (surface_mode == 1) {
		env = texture(env_tex, v_env).rgb;   // chrome: per-vertex texgen (authentic warping on small parts)
	} else if (has_env) {
		if (n64_classic.w > 0.5) {
			// legacy gloss on large surfaces: per-fragment reflection so highlights stay crisp streaks instead of
			// per-vertex wedges smeared across 10 m triangles
			vec3 r = reflect(normalize(VERTEX), normalize(NORMAL));
			float m = 2.0 * sqrt(r.x * r.x + r.y * r.y + (r.z + 1.0) * (r.z + 1.0));
			env = texture(env_tex, vec2(r.x / max(m, 0.0001) + 0.5, 0.5 - r.y / max(m, 0.0001))).rgb;
		} else {
			env = texture(env_tex, v_env).rgb;   // N64 convention: hardware-style per-vertex texgen
		}
	}
	vec3 c;
	if (surface_mode == 1) {
		// chrome/glass: the env map IS the lighting; the rig only tints it (warm lamps on chrome) and
		// the rim adds hard edge highlights. tint keeps per-role colour (blue glass, pale chrome).
		vec3 lum = mix(vec3(1.0), clamp(v_light, 0.0, 1.6), 0.45 * lit);
		// metal response (pack look.chrome): gamma deepens the reflected mids so the dark horizon band and the
		// floor reflection read; white-hot spots and the rim catch stay on top
		float el = dot(env, vec3(0.299, 0.587, 0.114));
		vec3 envc = pow(env, vec3(max(n64_chrome.x, 0.05)));
		c = envc * tint.rgb * lum;
		// white-hot glints survive the tint (blue glass keeps white highlights)
		c += vec3(smoothstep(min(n64_chrome.y, 0.999), 1.0, el)) * n64_chrome.z;
		c += v_rim * n64_chrome.w + v_spec;
	} else {
		// texel footprint (texels per pixel) for the N64 filter: three-point when magnified, the mip chain when
		// minified (no distant sparkle). Derivatives are taken outside the branches.
		vec2 tsz = vec2(textureSize(tex_nearest, 0));
		float rho = max(length(dFdx(UV * tsz)), length(dFdy(UV * tsz)));
		vec2 suv = UV;
		if (has_texture && n64_mode.z > 0.5) {
			if (n64_mode.x < 0.5) {
				tc = texture(tex_nearest, suv);
			} else if (n64_mode.x < 1.5) {
				tc = texture(tex_linear, suv);
			} else if (n64_mode.x < 2.5) {
				tc = three_point(tex_nearest, suv);
			} else if (n64_mode.x < 3.5) {
				tc = bilinear_nomip(tex_nearest, suv);
			} else {
				tc = rho > 1.0 ? textureLod(tex_linear, suv, max(log2(rho) + n64_filter.x, 0.0)) : three_point(tex_nearest, suv);
			}
			if (tex_vblur > 0.0) {
				// 5-tap vertical tent over +-tex_vblur texels (bilinear taps): smooth painted sky gradient
				float s = tex_vblur / tsz.y;
				tc = (textureLod(tex_linear, suv + vec2(0.0, -s), 0.0) + 2.0 * textureLod(tex_linear, suv + vec2(0.0, -0.5 * s), 0.0)
					+ 3.0 * tc + 2.0 * textureLod(tex_linear, suv + vec2(0.0, 0.5 * s), 0.0) + textureLod(tex_linear, suv + vec2(0.0, s), 0.0)) / 9.0;
			}
		}
		if (alpha_cut > 0.0 && tc.a < alpha_cut) {
			discard;
		}
		vec3 lc = mix(vec3(1.0), v_light, n64_mode.y);
		vec3 spc = v_spec;
		if (!dynamic_light && lit > 0.0 && n64_mode.w > 0.5 && n64_px.x > 0.5 && n64_classic.x > 0.5) {
			vec3 pwn = normalize(v_wn);
			vec3 pV = normalize(INV_VIEW_MATRIX[3].xyz - v_wpos);
			vec3 psp = vec3(0.0);
			vec3 prig = v_rigbase;
			prig += point_light(n64_pl0_pos, n64_pl0_col, v_wpos, pwn, pV, psp);
			prig += point_light(n64_pl1_pos, n64_pl1_col, v_wpos, pwn, pV, psp);
			prig += point_light(n64_pl2_pos, n64_pl2_col, v_wpos, pwn, pV, psp);
			prig += point_light(n64_pl3_pos, n64_pl3_col, v_wpos, pwn, pV, psp);
			lc = mix(vec3(1.0), v_baked * mix(vec3(1.0), min(prig, vec3(1.8)), lit * n64_mode.w), n64_mode.y);
			spc = v_speckey + psp * spec * lit * n64_classic.y;
		} else if (!dynamic_light && lit > 0.0 && n64_mode.w > 0.5 && n64_lattice.x > 0.0) {
			vec3 lrig = v_rigbase + lattice_points(v_wpos, normalize(v_wn), n64_lattice.x);
			lc = mix(vec3(1.0), v_baked * mix(vec3(1.0), min(lrig, vec3(1.8)), lit * n64_mode.w), n64_mode.y);
			spc = v_speckey;
		}
		if (!dynamic_light && lit > 0.0 && n64_mode.w > 0.5) {
			// room value structure (pack look profile "room"): light falls off toward the ceiling, wall bases sit
			// in contact shadow, the floor centre carries the lamp pool; evaluated per pixel like a baked lightmap
			float top = 1.0 - n64_room.x * smoothstep(n64_room.y, max(n64_room.z, n64_room.y + 0.01), v_wpos.y);
			float vert = 1.0 - smoothstep(0.45, 0.75, abs(v_wny));
			float base = 1.0 - n64_room.w * vert * (1.0 - smoothstep(0.0, max(n64_room2.x, 0.01), v_wpos.y));
			float up = smoothstep(0.75, 0.95, v_wny);
			float centre = up * n64_room2.y * (1.0 - smoothstep(1.5, 7.0, length(v_wpos.xz - n64_room2.zw))) * (1.0 - smoothstep(0.3, 1.2, v_wpos.y));
			lc *= mix(1.0, top * base * (1.0 + centre), lit);
		}
		c = tc.rgb * v_albedo * lc * tint.rgb;
		// glossy plastic/vinyl: only the white features of the env map (glints, light panels, horizon
		// line) are added, so a floor gets moving highlights instead of a uniform wash.
		float el = dot(env, vec3(0.299, 0.587, 0.114));
		c += vec3(smoothstep(0.955, 0.995, el)) * gloss * lit;
		c += spc + v_rim;
		c += tc.rgb * tint.rgb * emission;
		c *= mix(unlit_level, 1.0, clamp(lit, 0.0, 1.0));
	}
	c = clamp(c, 0.0, 1.0);
	float vf = v_fog;
	if (horizon_fog.y > 0.0) {
		float elev = normalize(v_wpos - INV_VIEW_MATRIX[3].xyz).y;
		vf = max(vf, (1.0 - smoothstep(horizon_fog.x, horizon_fog.y, elev)) * n64_fog.z * n64_fog.w);
	}
	c = mix(c, n64_fog_color.rgb, vf);
	c = grade(c);
	if (n64_debug.x > 0.5) {
		if (n64_debug.x < 1.5) {
			c = vec3(clamp(length(VERTEX) / max(n64_debug.y, 1.0), 0.0, 1.0));
		} else {
			c = vec3(float(mask_id == 1 || mask_id == 4 || mask_id == 6), float(mask_id == 2 || mask_id == 4 || mask_id == 5),
				float(mask_id == 3 || mask_id == 5 || mask_id == 6));
		}
	}
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	ALBEDO = c;
#else
	ALBEDO = to_linear(c);
#endif
}
