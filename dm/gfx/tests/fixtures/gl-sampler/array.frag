#version 300 es
precision mediump float;
uniform sampler2D tex[2];
uniform sampler2D extra;
uniform float weight;
out vec4 color;
void main() {
    color = weight * vec4(texture(tex[0], vec2(0.5)).r,
                         texture(tex[1], vec2(0.5)).g,
                         texture(extra, vec2(0.5)).b, 1.0);
}
