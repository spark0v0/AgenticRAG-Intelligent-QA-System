/** A decorative knowledge-flow sculpture. It does not represent a live agent run. */
export interface KnowledgeFieldRenderer {
  setExpanded(value: boolean): void
  setPaused(value: boolean): void
  pointAt(x: number, y: number): void
  dispose(): void
}

const vertexSource = `
precision highp float;
attribute vec2 aSample;
uniform float uTime;
uniform float uSpread;
uniform float uAspect;
uniform float uPixelRatio;
uniform vec2 uPointer;
varying float vLight;
varying float vBlue;
varying float vPulse;
varying float vSheen;
const float TAU = 6.28318530718;
void main() {
  float t = aSample.x;
  float u = t * 2.0 - 1.0;
  float group = floor(aSample.y * 5.0);
  float lane = fract(aSample.y * 5.0) - 0.5;
  float seed = fract(sin((aSample.y + 0.01) * 127.1) * 43758.5453);
  float phase = group * TAU / 5.0;
  float breath = uTime * 0.24;
  float fan = 0.30 + 0.72 * pow(abs(u), 1.4) + uSpread * 0.65;
  float weave = phase + u * 3.4 + breath * (0.65 + group * 0.06);
  float ripple = sin(u * 7.0 - breath * 1.4 + phase) * 0.10;
  float width = 0.38 + 0.22 * sin(u * 3.0 + phase + breath);
  vec3 p = vec3(
    u * 3.15,
    0.48 * u + 0.75 * sin(u * 2.65 - 0.15 + 0.12 * sin(breath))
      + sin(weave) * fan + lane * width + ripple * (0.25 + abs(u)),
    cos(weave) * fan * 0.75 + lane * 0.20
      + 0.15 * sin(u * 4.4 + phase - breath)
  );
  // A soft local bend follows the pointer; the form never spins as a rigid object.
  float influence = exp(-pow(u - uPointer.x * 0.8, 2.0) * 3.0);
  p.y += uPointer.y * -0.22 * influence;
  p.z += uPointer.x * 0.12;
  p.xy = mat2(0.985, -0.174, 0.174, 0.985) * p.xy;
  float perspective = 4.8 / (4.8 + p.z);
  gl_Position = vec4(p.xy * vec2(1.0 / uAspect, 1.0) * 0.53 * perspective, 0.0, 1.0);
  float fade = smoothstep(0.0, 0.15, t) * (1.0 - smoothstep(0.82, 1.0, t));
  float front = 1.0 - smoothstep(-0.65, 0.85, p.z);
  vLight = fade * (0.12 + 0.35 * front) * (0.45 + seed * 0.55);
  vBlue = clamp(t * 0.88 + group * 0.055 + 0.06 * sin(breath), 0.0, 1.0);
  vSheen = pow(0.5 + 0.5 * sin(u * 3.0 + phase - breath), 6.0) * front;
  float travel = fract(t * 0.8 - uTime * (0.04 + seed * 0.035) + seed);
  float head = exp(-pow((travel - 0.5) / 0.009, 2.0));
  float tail = exp(-abs(travel - 0.48) * 45.0) * step(travel, 0.5);
  vPulse = (head + 0.2 * tail) * step(0.76, seed) * fade;
  gl_PointSize = (3.0 + 4.0 * front) * uPixelRatio;
}`

const fragmentSource = `
precision mediump float;
varying float vLight;
varying float vBlue;
varying float vPulse;
varying float vSheen;
uniform float uPass;
void main() {
  // A continuous ice-blue / cobalt / soft periwinkle spectrum, with silver crests.
  vec3 color = mix(vec3(0.12, 0.74, 1.0), vec3(0.24, 0.39, 1.0), smoothstep(0.12, 0.68, vBlue));
  color = mix(color, vec3(0.64, 0.52, 1.0), smoothstep(0.58, 1.0, vBlue) * 0.85);
  color = mix(color, vec3(0.70, 0.86, 1.0), vSheen * 0.28);
  if (uPass > 0.5) {
    vec2 point = gl_PointCoord * 2.0 - 1.0;
    float radius = dot(point, point);
    float glow = exp(-radius * 5.0) * 0.36 + exp(-radius * 28.0);
    gl_FragColor = vec4(mix(color, vec3(0.92, 0.97, 1.0), 0.5), glow * vPulse);
  } else {
    gl_FragColor = vec4(color, vLight);
  }
}`

export function createKnowledgeField(
  canvas: HTMLCanvasElement,
  paused: boolean,
  onUnavailable: () => void,
): KnowledgeFieldRenderer | null {
  const gl = canvas.getContext('webgl', {
    alpha: true,
    antialias: true,
    depth: false,
    powerPreference: 'low-power',
  })
  if (!gl) return null

  const shaders: WebGLShader[] = []
  let program: WebGLProgram | null = null
  let buffer: WebGLBuffer | null = null
  const release = () => {
    if (buffer) gl.deleteBuffer(buffer)
    if (program) gl.deleteProgram(program)
    shaders.forEach((shader) => gl.deleteShader(shader))
  }
  const compile = (type: number, source: string) => {
    const shader = gl.createShader(type)
    if (!shader) throw new Error('Shader unavailable')
    shaders.push(shader)
    gl.shaderSource(shader, source)
    gl.compileShader(shader)
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS))
      throw new Error('Shader compilation failed')
    return shader
  }
  try {
    program = gl.createProgram()
    if (!program) throw new Error('Program unavailable')
    gl.attachShader(program, compile(gl.VERTEX_SHADER, vertexSource))
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, fragmentSource))
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error('Program linking failed')
    buffer = gl.createBuffer()
    if (!buffer) throw new Error('Buffer unavailable')
  } catch {
    release()
    return null
  }

  // Reuse one mesh for flowing filaments and sparse travelling light particles.
  const strands = canvas.clientWidth < 600 ? 80 : 125
  const segments = 260
  const samples = new Float32Array(strands * segments * 4)
  let offset = 0
  for (let strand = 0; strand < strands; strand++) {
    for (let step = 0; step < segments; step++) {
      samples[offset++] = step / segments
      samples[offset++] = strand / strands
      samples[offset++] = (step + 1) / segments
      samples[offset++] = strand / strands
    }
  }
  gl.useProgram(program)
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
  gl.bufferData(gl.ARRAY_BUFFER, samples, gl.STATIC_DRAW)
  const attribute = gl.getAttribLocation(program, 'aSample')
  gl.enableVertexAttribArray(attribute)
  gl.vertexAttribPointer(attribute, 2, gl.FLOAT, false, 0, 0)
  gl.enable(gl.BLEND)
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE)
  const uniforms = {
    time: gl.getUniformLocation(program, 'uTime'),
    spread: gl.getUniformLocation(program, 'uSpread'),
    aspect: gl.getUniformLocation(program, 'uAspect'),
    pointer: gl.getUniformLocation(program, 'uPointer'),
    pixelRatio: gl.getUniformLocation(program, 'uPixelRatio'),
    pass: gl.getUniformLocation(program, 'uPass'),
  }
  let frame = 0
  let last = 0
  let time = 0
  let spread = 0
  let targetSpread = 0
  let pointerX = 0
  let pointerY = 0
  let targetX = 0
  let targetY = 0
  let visible = true
  let disposed = false
  let lost = false

  const draw = () => {
    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.uniform1f(uniforms.time, time)
    gl.uniform1f(uniforms.spread, spread)
    gl.uniform1f(uniforms.aspect, canvas.width / Math.max(canvas.height, 1))
    gl.uniform2f(uniforms.pointer, pointerX, pointerY)
    gl.uniform1f(uniforms.pass, 0)
    gl.drawArrays(gl.LINES, 0, samples.length / 2)
    gl.uniform1f(uniforms.pass, 1)
    gl.drawArrays(gl.POINTS, 0, samples.length / 2)
  }
  const canAnimate = () => !disposed && !lost && !paused && visible && !document.hidden
  const tick = (now: number) => {
    frame = 0
    if (!canAnimate()) return
    if (!last || now - last >= 1000 / 30) {
      const dt = last ? Math.min((now - last) / 1000, 0.08) : 0
      last = now
      time += dt
      const blend = 1 - Math.exp(-5 * dt)
      spread += (targetSpread - spread) * blend
      pointerX += (targetX - pointerX) * blend
      pointerY += (targetY - pointerY) * blend
      draw()
    }
    frame = requestAnimationFrame(tick)
  }
  const sync = () => {
    cancelAnimationFrame(frame)
    frame = 0
    last = 0
    if (disposed || lost) return
    if (!canAnimate()) {
      spread = targetSpread
      pointerX = targetX
      pointerY = targetY
      if (visible && !document.hidden) draw()
    } else frame = requestAnimationFrame(tick)
  }
  const resize = () => {
    if (disposed || lost) return
    const { width, height } = canvas.getBoundingClientRect()
    const ratio = Math.min(
      window.devicePixelRatio || 1,
      1.75,
      Math.sqrt(2_800_000 / Math.max(width * height, 1)),
    )
    canvas.width = Math.max(1, Math.round(width * ratio))
    canvas.height = Math.max(1, Math.round(height * ratio))
    gl.viewport(0, 0, canvas.width, canvas.height)
    gl.uniform1f(uniforms.pixelRatio, ratio)
    draw()
  }
  const resizeObserver = new ResizeObserver(resize)
  const intersectionObserver = new IntersectionObserver(([entry]) => {
    visible = entry?.isIntersecting ?? false
    sync()
  })
  const contextLost = (event: Event) => {
    event.preventDefault()
    lost = true
    cancelAnimationFrame(frame)
    onUnavailable()
  }
  canvas.addEventListener('webglcontextlost', contextLost)
  document.addEventListener('visibilitychange', sync)
  resizeObserver.observe(canvas)
  intersectionObserver.observe(canvas)
  resize()
  sync()

  return {
    setExpanded(value) {
      targetSpread = value ? 1 : 0
      if (paused) sync()
    },
    setPaused(value) {
      paused = value
      sync()
    },
    pointAt(x, y) {
      targetX = x
      targetY = y
    },
    dispose() {
      disposed = true
      cancelAnimationFrame(frame)
      resizeObserver.disconnect()
      intersectionObserver.disconnect()
      document.removeEventListener('visibilitychange', sync)
      canvas.removeEventListener('webglcontextlost', contextLost)
      release()
    },
  }
}
