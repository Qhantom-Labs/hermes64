extends RefCounted
## Godot JSON parses every number as float. Restore only INTEGER TOKENS to int.
## Preserve 1.0 / 1e0 as float: save tick type checks and opaque timestamps rely on it.
static func number_tokens(text: String) -> Array:
	var tokens := []
	var quoted := false
	var escaped := false
	var i := 0
	while i < text.length():
		var char := text.substr(i, 1)
		if quoted:
			if escaped: escaped = false
			elif char == "\\": escaped = true
			elif char == '"': quoted = false
			i += 1
			continue
		if char == '"':
			quoted = true
			i += 1
			continue
		if char == "-" or char in "0123456789":
			var start := i
			i += 1
			while i < text.length() and text.substr(i, 1) in "0123456789.eE+-": i += 1
			tokens.append(text.substr(start, i - start))
		else: i += 1
	return tokens

static func typed_numbers(value, tokens: Array, cursor: Array):
	if value is Dictionary:
		var out := {}
		for key in value: out[key] = typed_numbers(value[key], tokens, cursor)
		return out
	if value is Array:
		var out := []
		for entry in value: out.append(typed_numbers(entry, tokens, cursor))
		return out
	if typeof(value) in [TYPE_FLOAT, TYPE_INT]:
		if cursor[0] >= tokens.size() or not is_finite(value):
			cursor[1] = true
			return null
		var token: String = tokens[cursor[0]]
		cursor[0] += 1
		if not token.contains(".") and not token.to_lower().contains("e"):
			var integer := token.to_int()
			if str(integer) != token and token != "-0": cursor[1] = true
			return integer
	return value

static func read_json(path: String):
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null: return null
	var text := file.get_as_text()
	var parser := JSON.new()
	if parser.parse(text) != OK: return null
	var tokens := number_tokens(text)
	var cursor := [0, false]
	var result = typed_numbers(parser.data, tokens, cursor)
	if cursor[1] or cursor[0] != tokens.size(): return null
	return result
