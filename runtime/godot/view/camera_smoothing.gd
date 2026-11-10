extends RefCounted
## Presentation-only analytic critically damped springs. No simulation references.
static func spring(value: Vector3, velocity: Vector3, target: Vector3, omega: float, dt: float) -> Array:
	var error := value-target
	var j := velocity+error*omega
	var decay := exp(-omega*dt)
	return [target+(error+j*dt)*decay,(velocity-j*omega*dt)*decay]
static func scalar(value: float, velocity: float, target: float, omega: float, dt: float) -> Vector2:
	var error := value-target
	var j := velocity+error*omega
	var decay := exp(-omega*dt)
	return Vector2(target+(error+j*dt)*decay,(velocity-j*omega*dt)*decay)
static func soft_error(error: Vector3, radius: float) -> Vector3:
	# Smooth at the origin and deadzone edge: no threshold/clamp catch-up.
	return error*(error.length_squared()/(error.length_squared()+radius*radius))
